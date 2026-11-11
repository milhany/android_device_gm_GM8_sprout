// Compile the actual native backend, fwmark case bodies and Binder body with fixtures.
#include "LegacySocketTagger.h"
#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <fcntl.h>
#include <fstream>
#include <netinet/in.h>
#include <string>
#include <sys/socket.h>
#include <unistd.h>

using android::net::LegacySocketTagger;
static std::string controlPath, devicePath;
static int controlFd = -1, deviceFd = -1, deviceOpens = 0, deviceCloses = 0;
static int writeMode = 0, writeCalls = 0, modernTags = 0, modernUntags = 0;
static std::vector<std::string> commands;
static bool unsupportedFamily = false, unsupportedProtocol = false;
extern "C" int __real_getsockopt(int, int, int, void*, socklen_t*);
extern "C" int __wrap_getsockopt(int fd, int level, int option, void* value, socklen_t* length) {
    if ((unsupportedFamily && option == SO_DOMAIN) || (unsupportedProtocol && option == SO_PROTOCOL)) {
        assert(*length == sizeof(int));
        *static_cast<int*>(value) = option == SO_DOMAIN ? AF_UNIX : IPPROTO_ICMP;
        return 0;
    }
    return __real_getsockopt(fd, level, option, value, length);
}
extern "C" int __real_open(const char*, int, ...);
extern "C" int __real_close(int);
extern "C" ssize_t __real_write(int, const void*, size_t);
extern "C" int __wrap_open(const char* path, int flags, ...) {
    int mode = 0;
    if (flags & O_CREAT) { va_list args; va_start(args, flags); mode = va_arg(args, int); va_end(args); }
    int fd = __real_open(path, flags, mode);
    if (fd >= 0 && path == devicePath) {
        deviceFd = fd; deviceOpens++;
        assert((fcntl(fd, F_GETFD) & FD_CLOEXEC) != 0);
    }
    if (fd >= 0 && path == controlPath) {
        controlFd = fd;
        assert(deviceFd >= 0 && fcntl(deviceFd, F_GETFD) >= 0);
        assert((fcntl(fd, F_GETFD) & FD_CLOEXEC) != 0);
    }
    return fd;
}
extern "C" int __wrap_close(int fd) {
    if (fd == controlFd) controlFd = -1;
    if (fd == deviceFd) { deviceFd = -1; deviceCloses++; }
    return __real_close(fd);
}
extern "C" ssize_t __wrap_write(int fd, const void* data, size_t size) {
    if (fd != controlFd) return __real_write(fd, data, size);
    writeCalls++;
    if (writeMode == 1) { errno = EPERM; return -1; }
    if (writeMode == 2) return size - 1;
    if (writeMode == 3) { writeMode = 0; errno = EINTR; return -1; }
    commands.emplace_back(static_cast<const char*>(data), size);
    return size;
}
namespace binder {
class Status {
  public:
    static constexpr int EX_UNSUPPORTED_OPERATION = -7;
    int error;
    explicit Status(int value = 0) : error(value) {}
    static Status fromExceptionCode(int code) { return Status(code); }
};
}
struct INetd {
    static constexpr int PERMISSION_INTERNET = 4, PERMISSION_UPDATE_DEVICE_STATS = 8,
                         PERMISSION_UNINSTALLED = -1;
};
struct FirewallController { static bool legacy; static bool isLegacyMode() { return legacy; } };
bool FirewallController::legacy = true;
struct Controllers { LegacySocketTagger& legacySocketTagger; };
static Controllers* gCtls;
static bool binderAllowed = true;
static binder::Status statusFromErrcode(int error) { return binder::Status(error); }
#define ENFORCE_NETWORK_STACK_PERMISSIONS() do { if (!binderAllowed) return binder::Status(-EPERM); } while (0)
struct NetdNativeService {
    binder::Status trafficSetNetPermForUids(int32_t permissions, const std::vector<int32_t>& appIds);
};
// BINDER_BODY
struct Command { uid_t uid; uint32_t trafficCtrlInfo; };
struct Client { uid_t uid; uid_t getUid() { return uid; } };
static int libnetd_updatable_tagSocket(int, uint32_t, uid_t, uid_t) { modernTags++; return 73; }
static int libnetd_updatable_untagSocket(int) { modernUntags++; return 74; }
static int dispatchTag(Command command, Client* client, int* socketFd) {
// FWMARK_TAG_BODY
}
static int dispatchUntag(int* socketFd) {
// FWMARK_UNTAG_BODY
}
static void put(const std::string& path, const std::string& data) { std::ofstream out(path); out << data; }
int main(int argc, char** argv) {
    assert(argc == 2);
    std::string root = argv[1], passive = root + "/passive", tracking = root + "/tracking";
    controlPath = root + "/ctrl"; devicePath = root + "/device";
    put(controlPath, ""); put(devicePath, ""); put(passive, "N\n"); put(tracking, "N\n");
    int tcp = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, IPPROTO_TCP);
    int udp6 = socket(AF_INET6, SOCK_DGRAM | SOCK_CLOEXEC, IPPROTO_UDP);
    assert(tcp >= 0 && udp6 >= 0);
    {
        LegacySocketTagger tagger({controlPath.c_str(), devicePath.c_str(), passive.c_str(), tracking.c_str()});
        Controllers controllers{tagger}; gCtls = &controllers;
        NetdNativeService binder;
        Client app{10001};
        assert(dispatchTag({static_cast<uid_t>(-1), 1}, &app, &tcp) == 0);
        assert(commands.back() == "t " + std::to_string(tcp) + " 4294967296 10001");
        assert(deviceOpens == 1 && deviceCloses == 0);
        size_t before = commands.size();
        assert(tagger.tagSocket(tcp, 0, 10002, 10001) == -EPERM);
        assert(commands.size() == before);
        binderAllowed = false;
        assert(binder.trafficSetNetPermForUids(8, {10001}).error == -EPERM);
        assert(tagger.tagSocket(tcp, 0, 10002, 10001) == -EPERM);
        binderAllowed = true;
        assert(binder.trafficSetNetPermForUids(12, {10001}).error == 0);
        assert(tagger.tagSocket(udp6, UINT32_MAX, 10002, 110001) == 0);
        assert(commands.back() == "t " + std::to_string(udp6) + " 18446744069414584320 10002");
        assert(binder.trafficSetNetPermForUids(0, {10001, 100000}).error == -EINVAL);
        assert(tagger.tagSocket(tcp, 0, 10002, 10001) == 0); // invalid batch changed nothing
        assert(binder.trafficSetNetPermForUids(16, {10001}).error == -EINVAL);
        assert(binder.trafficSetNetPermForUids(8, {-1}).error == -EINVAL);
        assert(binder.trafficSetNetPermForUids(4, {10001}).error == 0);
        assert(tagger.tagSocket(tcp, 0, 10002, 10001) == -EPERM);
        assert(binder.trafficSetNetPermForUids(8, {10001, 10001}).error == 0);
        assert(binder.trafficSetNetPermForUids(-1, {10001}).error == 0);
        assert(tagger.tagSocket(tcp, 0, 10002, 10001) == -EPERM);
        for (uid_t uid : {0U, 1000U, 1051U, 101000U}) assert(tagger.tagSocket(tcp, 0, 10002, uid) == 0);
        assert(tagger.tagSocket(tcp, 0, 1029, 0) == -EPERM);
        assert(tagger.tagSocket(tcp, 0, UINT32_MAX, 0) == -EINVAL);
        assert(tagger.tagSocket(tcp, 0, 0, UINT32_MAX) == -EINVAL);
        assert(tagger.tagSocket(-1, 0, 10001, 10001) == -EBADF);
        unsupportedFamily = true;
        assert(tagger.tagSocket(tcp, 0, 10001, 10001) == -EAFNOSUPPORT);
        unsupportedFamily = false; unsupportedProtocol = true;
        assert(tagger.tagSocket(tcp, 0, 10001, 10001) == -EPROTONOSUPPORT);
        unsupportedProtocol = false;
        assert(dispatchUntag(&tcp) == 0);
        assert(commands.back() == "u " + std::to_string(tcp));
        writeMode = 1; assert(tagger.untagSocket(tcp) == -EPERM);
        writeMode = 2; int previousWrites = writeCalls;
        assert(tagger.untagSocket(tcp) == -EIO && writeCalls == previousWrites + 1);
        writeMode = 3; previousWrites = writeCalls;
        assert(tagger.untagSocket(tcp) == 0 && writeCalls == previousWrites + 2);
        for (auto data : {"Y\n", "", "Ngarbage"}) {
            put(passive, data); before = commands.size();
            assert(tagger.untagSocket(tcp) == -EOPNOTSUPP && commands.size() == before);
        }
        put(passive, "N\n"); put(tracking, "Y\n");
        assert(tagger.untagSocket(tcp) == -EOPNOTSUPP);
        put(tracking, "N\n"); unlink(passive.c_str());
        assert(tagger.untagSocket(tcp) == -ENOENT);
        put(passive, "N\n"); unlink(controlPath.c_str());
        assert(tagger.untagSocket(tcp) == -ENOENT);
        put(controlPath, ""); assert(tagger.untagSocket(tcp) == 0);
        assert(deviceOpens == 1 && deviceCloses == 0);
        gCtls = nullptr;
        assert(dispatchTag({10001, 0}, &app, &tcp) == -ENODEV);
        assert(dispatchUntag(&tcp) == -ENODEV);
        FirewallController::legacy = false;
        assert(dispatchTag({10001, 0}, &app, &tcp) == 73);
        assert(dispatchUntag(&tcp) == 74);
        assert(binder.trafficSetNetPermForUids(8, {10001}).error == binder::Status::EX_UNSUPPORTED_OPERATION);
        assert(modernTags == 1 && modernUntags == 1);
    }
    assert(deviceOpens == 1 && deviceCloses == 1);
    unlink(devicePath.c_str());
    LegacySocketTagger failed({controlPath.c_str(), devicePath.c_str(), passive.c_str(), tracking.c_str()});
    assert(failed.tagSocket(tcp, 0, 10001, 10001) == -ENOENT);
    close(tcp); close(udp6);
}
