// The Python runner inserts actual SDK33 function bodies at GM8_FUNCTIONS.
// Controller metadata and kernel process operations are fixtures. No mounts or signals occur.
#include <cassert>
#include <cerrno>
#include <chrono>
#include <dirent.h>
#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

using namespace std::chrono_literals;
namespace fs = std::filesystem;
#define LOG(level) std::ostringstream()
#define PLOG(level) std::ostringstream()
#define PROCESSGROUP_CGROUP_PROCS_FILE "/cgroup.procs"
#define CGROUPV2_CONTROLLER_NAME "cgroup2"

struct Controller {
    bool usable = false;
    unsigned ver = 0;
    std::string root;
    bool IsUsable() { return usable; }
    unsigned version() const { return ver; }
    const char* path() const { return root.c_str(); }
};
struct CgroupMap {
    Controller unified, legacy;
    static CgroupMap& GetInstance() { static CgroupMap map; return map; }
    Controller FindController(const std::string& name) {
        return name == CGROUPV2_CONTROLLER_NAME ? unified : legacy;
    }
};
struct Creation { uid_t uid; int pid; std::string path; bool activate; };
static std::vector<Creation> creations;
static std::vector<std::string> kills, removals, cleanups;
static bool memory_supported = false, per_app = false;
static int create_result = 0, kill_result = 0, remove_result = 0;
static std::string memory_path;
static bool isMemoryCgroupSupported() { return memory_supported; }
static bool UsePerAppMemcg() { return per_app; }
static bool CgroupGetMemcgAppsPath(std::string* path) {
    if (memory_path.empty()) return false;
    *path = memory_path;
    return true;
}
static int createProcessGroupInternal(uid_t uid, int pid, std::string path, bool activate) {
    creations.push_back({uid, pid, path, activate});
    return create_result;
}
static int DoKillProcessGroupOnce(const char* path, uid_t, int, int) {
    kills.emplace_back(path);
    return kill_result;
}
static int RemoveProcessGroup(const char* path, uid_t, int, unsigned) {
    removals.emplace_back(path);
    return remove_result;
}
static bool StartsWith(const char* str, const char* prefix) {
    return std::string(str).rfind(prefix, 0) == 0;
}
static std::string StringPrintf(const char*, const char* a, const char* b) {
    return std::string(a) + "/" + b;
}
static bool RemoveUidProcessGroups(const std::string& path, bool) {
    cleanups.push_back(path);
    return true;
}

// GM8_FUNCTIONS

static void reset() {
    creations.clear(); kills.clear(); removals.clear(); cleanups.clear();
    memory_supported = per_app = false;
    create_result = kill_result = remove_result = 0;
    memory_path.clear();
}

int main(int argc, char** argv) {
    assert(argc == 2);
    const fs::path temp(argv[1]), legacy = temp / "legacy", unified = temp / "unified";
    fs::create_directories(legacy);
    fs::create_directories(unified);
    std::ofstream(legacy / "cgroup.procs") << "";
    auto& map = CgroupMap::GetInstance();
    map.legacy = {true, 1, legacy.string()};
    map.unified = {false, 2, unified.string()};
    assert(createProcessGroup(10001, 123, false) == 0);
    assert(creations.size() == 1 && creations[0].path == legacy && !creations[0].activate);
    assert(creations[0].uid == 10001 && creations[0].pid == 123);

    reset();
    map.unified.usable = true; // Reproduce SDK33's misleading mounted flag after a failed mount.
    assert(createProcessGroup(10001, 123, false) == 0);
    assert(creations[0].path == legacy && !creations[0].activate);

    reset();
    std::ofstream(unified / "cgroup.procs") << "";
    assert(createProcessGroup(10001, 123, false) == 0);
    assert(creations[0].path == unified && creations[0].activate);

    reset();
    map.unified.ver = 1; // A controller under the wrong name/version is not a unified hierarchy.
    assert(createProcessGroup(10001, 123, false) == 0);
    assert(creations[0].path == legacy && !creations[0].activate);
    map.unified.ver = 2;
    map.unified.usable = false;

    reset();
    map.legacy.usable = false;
    int max_processes = 99;
    assert(createProcessGroup(10001, 123, false) == -ENODEV);
    assert(KillProcessGroup(10001, 123, 9, 0, &max_processes) == -ENODEV);
    assert(max_processes == 0 && creations.empty() && kills.empty() && removals.empty());
    map.legacy.usable = true;

    reset();
    create_result = -EACCES;
    assert(createProcessGroup(10001, 123, false) == -EACCES);

    reset();
    assert(createProcessGroup(10001, 123, true) == -EINVAL);
    assert(creations.empty());

    reset();
    memory_supported = per_app = true;
    memory_path = (temp / "memory/apps").string();
    assert(createProcessGroup(10001, 123, true) == 0);
    assert(creations.size() == 2 && creations[0].path == memory_path && !creations[0].activate);
    assert(creations[1].path == legacy && !creations[1].activate);
    creations.clear(); create_result = -ENOSPC;
    assert(createProcessGroup(10001, 123, true) == -ENOSPC);
    assert(creations.size() == 1 && creations[0].path == memory_path);

    reset();
    assert(KillProcessGroup(10001, 123, 9, 0, &max_processes) == 0);
    assert(kills == std::vector<std::string>{legacy.string()});
    assert(removals == std::vector<std::string>{legacy.string()});
    reset(); kill_result = -1;
    assert(KillProcessGroup(10001, 123, 9, 0, &max_processes) == -1);
    assert(removals.empty());
    reset(); remove_result = -7;
    assert(KillProcessGroup(10001, 123, 9, 0, &max_processes) == -7);

    reset();
    fs::create_directories(legacy / "uid_10001");
    fs::create_directories(unified / "uid_10001");
    removeAllProcessGroupsInternal(true);
    assert(cleanups == std::vector<std::string>{(legacy / "uid_10001").string()});
    assert(fs::exists(unified / "uid_10001"));
    reset(); map.unified.usable = true;
    removeAllProcessGroupsInternal(false);
    assert(cleanups == std::vector<std::string>{(unified / "uid_10001").string()});
    return 0;
}
