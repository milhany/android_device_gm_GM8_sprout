#!/usr/bin/env python3
"""Compile actual Q FileNode/Node/RequestGroup with filesystem/Android boundaries."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--libperfmgr', type=Path,
                    default=ROOT.parents[2] / 'system/extras/libperfmgr')
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('patch', ROOT / 'tools/apply-power-diagnostics-17.1.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
source = (args.libperfmgr / 'FileNode.cc').read_text()
patched = patch.transform(source)
assert patch.transform(patched) == patched
# Also accept the old errno-only stage; reject changed open logic atomically.
vanilla = source.replace(patch.NEW, patch.OLD)
if patch.HELPER not in vanilla:
    assert patch.transform(vanilla) == patched
    assert patch.transform(vanilla.replace(patch.OLD, patch.NEW)) == patched
    try:
        patch.transform(vanilla.replace(patch.OPEN_OLD, '        fd_.reset(-1);'))
    except ValueError:
        pass
    else:
        raise AssertionError('Unknown FileNode open logic was accepted')

with tempfile.TemporaryDirectory(prefix='gm8-q-cpufreq-') as temporary:
    top = Path(temporary)
    top.chmod(0o755)
    base = top / 'android-base'
    base.mkdir()
    headers = top / 'perfmgr'
    headers.mkdir()
    fixture = top / 'cpu-fixture'
    fixture.mkdir(mode=0o777)
    for name in ('FileNode.h', 'Node.h', 'RequestGroup.h'):
        (headers / name).write_text((args.libperfmgr / 'include/perfmgr' / name).read_text())
    for name in ('Node.cc', 'RequestGroup.cc'):
        (top / name).write_text((args.libperfmgr / name).read_text())
    # Replace only the fixed sysfs root; resolver and actual FileNode logic stay intact.
    native_source = patched.replace(
        '"/sys/devices/system/cpu/cpu"', '"' + str(fixture / 'cpu') + '"')
    # Inject EACCES at the open syscall boundary, including on root test hosts
    # where mode bits would not deny access or changing UID is unavailable.
    native_source = native_source.replace('namespace android {',
        'extern int Gm8TestOpen(const char*, int);\n#define open Gm8TestOpen\n\nnamespace android {', 1)
    (top / 'FileNode.cc').write_text(native_source)
    (base / 'unique_fd.h').write_text(r'''#pragma once
#include <fcntl.h>
#include <unistd.h>
namespace android { namespace base {
class unique_fd {
 int fd_ = -1;
 public:
 ~unique_fd() { reset(); }
 void reset(int value = -1) { if (fd_ >= 0) close(fd_); fd_ = value; }
 operator int() const { return fd_; }
};
}}
''')
    (base / 'file.h').write_text(r'''#pragma once
#include <algorithm>
#include <cerrno>
#include <fstream>
#include <iterator>
#include <string>
#include <unistd.h>
namespace android { namespace base {
inline bool ReadFileToString(const std::string& path, std::string* out) {
 std::ifstream input(path); if (!input) return false;
 *out = std::string(std::istreambuf_iterator<char>(input), {}); return !input.bad();
}
inline bool WriteStringToFd(const std::string& value, int fd) {
 return write(fd, value.data(), value.size()) == static_cast<ssize_t>(value.size());
}
}}
''')
    (base / 'logging.h').write_text('#pragma once\n#include <sstream>\n#define LOG(x) std::ostringstream()\n#define PLOG(x) std::ostringstream()\n')
    (base / 'stringprintf.h').write_text(r'''#pragma once
#include <cstdarg>
#include <cstdio>
#include <string>
namespace android { namespace base {
inline std::string StringPrintf(const char* format, ...) {
 char out[4096]; va_list args; va_start(args, format);
 vsnprintf(out, sizeof(out), format, args); va_end(args); return out;
}
}}
''')
    (base / 'strings.h').write_text('#pragma once\n#include <string>\nnamespace android { namespace base { inline std::string Trim(const std::string& s) { return s; } }}\n')
    (top / 'test.cc').write_text(r'''
#include <cassert>
#include <cerrno>
#include <chrono>
#include <fstream>
#include <iterator>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include "perfmgr/FileNode.h"
using namespace android::perfmgr;
using namespace std::chrono;
static std::string deny_write_path;
int Gm8TestOpen(const char* path, int flags) {
 if (deny_write_path == path) { errno = EACCES; return -1; }
 return open(path, flags);
}
static void put(const std::string& path, const std::string& value) {
 std::ofstream out(path); out << value; out.close(); assert(!out.fail());
}
static std::string get(const std::string& path) {
 std::ifstream in(path); return std::string(std::istreambuf_iterator<char>(in), {});
}
static std::string policy(const std::string& root, int cpu, const char* related) {
 std::string dir = root + "/cpu" + std::to_string(cpu);
 assert(mkdir(dir.c_str(), 0755) == 0); dir += "/cpufreq";
 assert(mkdir(dir.c_str(), 0755) == 0);
 put(dir + "/related_cpus", related);
 put(dir + "/scaling_min_freq", "960000");
 put(dir + "/scaling_max_freq", "1401000");
 return dir;
}
static std::vector<RequestGroup> values() { return {RequestGroup("1401000"), RequestGroup("960000")}; }
int main(int argc, char** argv) {
 assert(argc == 2); std::string root = argv[1];
 auto d1 = policy(root, 1, "0 1 2 3\n");
 FileNode min("min", root + "/cpu0/cpufreq/scaling_min_freq", values(), 1, true);
 assert(min.AddRequest(0, "LAUNCH", ReqTime::max())); min.Update(true);
 assert(get(d1 + "/scaling_min_freq") == "1401000");
 // Policy migrates while boosted: restore on cpu3, not a stale cpu1 alias.
 assert(mkdir((root + "/cpu3").c_str(), 0755) == 0);
 auto d3 = root + "/cpu3/cpufreq";
 assert(rename(d1.c_str(), d3.c_str()) == 0);
 assert(min.RemoveRequest("LAUNCH")); min.Update(true);
 assert(get(d3 + "/scaling_min_freq") == "960000");
 // Maximum limit and the other cluster use the same resolver independently.
 FileNode max("max", root + "/cpu0/cpufreq/scaling_max_freq",
              {RequestGroup("1401000"), RequestGroup("1248000")}, 0, true);
 assert(max.AddRequest(1, "LIMIT", ReqTime::max())); max.Update(true);
 assert(get(d3 + "/scaling_max_freq") == "1248000");
 max.RemoveRequest("LIMIT"); max.Update(true);
 assert(get(d3 + "/scaling_max_freq") == "1401000");
 auto d5 = policy(root, 5, "4 5 6 7\n");
 FileNode little("little", root + "/cpu4/cpufreq/scaling_min_freq",
                 {RequestGroup("1094400"), RequestGroup("768000")}, 1, true);
 assert(little.AddRequest(0, "LAUNCH", ReqTime::max())); little.Update(true);
 assert(get(d5 + "/scaling_min_freq") == "1094400");
 assert(get(d3 + "/scaling_min_freq") == "960000");
 // Refuse wrong/malformed related_cpus; retain the actual 500 ms retry.
 put(d3 + "/related_cpus", "4 5 6 7\n");
 assert(min.AddRequest(0, "LAUNCH", ReqTime::max()));
 assert(min.Update(true) == milliseconds(500));
 assert(get(d3 + "/scaling_min_freq") == "960000");
 put(d3 + "/related_cpus", "0 3 invalid\n");
 assert(min.Update(true) == milliseconds(500));
 put(d3 + "/related_cpus", "0 3 999999999999999999999999\n");
 assert(min.Update(true) == milliseconds(500));
 put(d3 + "/related_cpus", "0 1 2 3 4\n");
 assert(min.Update(true) == milliseconds(500));
 put(d3 + "/related_cpus", "0 1 2 3\n"); min.Update(true);
 assert(get(d3 + "/scaling_min_freq") == "1401000");
 // Only cpu0/cpu4 min/max are eligible. No fallback for another endpoint.
 FileNode unconfigured("cpu2", root + "/cpu2/cpufreq/scaling_min_freq", values(), 1, true);
 assert(unconfigured.Update(true) == milliseconds(500));
 // Existing original path remains preferred over the fallback.
 auto d0 = policy(root, 0, "0 1 2 3\n");
 FileNode direct("direct", root + "/cpu0/cpufreq/scaling_min_freq", values(), 1, false);
 assert(direct.AddRequest(0, "LAUNCH", ReqTime::max())); direct.Update(true);
 assert(get(d0 + "/scaling_min_freq") == "1401000");
 put(d3 + "/scaling_min_freq", "sibling-unchanged");
 // EACCES must not redirect a write to a different CPU.
 deny_write_path = d0 + "/scaling_min_freq";
 assert(direct.RemoveRequest("LAUNCH"));
 assert(direct.Update(true) == milliseconds(500));
 assert(get(d3 + "/scaling_min_freq") == "sibling-unchanged");
 deny_write_path.clear();
 direct.Update(true); assert(get(d0 + "/scaling_min_freq") == "960000");
 // QHMP initialization does not release; the first hint and end write 1 then 0.
 auto boost = root + "/sched_boost"; put(boost, "untouched");
 FileNode sched("boost", boost, {RequestGroup("1"), RequestGroup("0")}, 1, false);
 sched.Update(true); assert(get(boost) == "untouched");
 sched.AddRequest(0, "LAUNCH", ReqTime::max()); sched.Update(true); assert(get(boost) == "1");
 sched.RemoveRequest("LAUNCH"); sched.Update(true); assert(get(boost) == "0");
}
''')
    binary = top / 'native-test'
    subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=undefined', '-fno-sanitize-recover=all',
                    '-I', str(top), str(top / 'FileNode.cc'), str(top / 'Node.cc'),
                    str(top / 'RequestGroup.cc'), str(top / 'test.cc'), '-o', str(binary)], check=True)
    subprocess.run([str(binary), str(fixture)], check=True)

print('PASS: actual Q FileNode hotplug boost/restore, cluster isolation, retry, EACCES and balanced initialization')
print('Android boundaries/sysfs are fixtures; full Android build and hardware tests remain required.')
