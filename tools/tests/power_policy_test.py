#!/usr/bin/env python3
"""Host-build real Power/InteractionHandler sources with HIDL/sysprop fixtures."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2] / "power-libperfmgr"

HIDL = r'''
#pragma once
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
namespace android::hardware {
struct Void {};
template<class T> struct Return {};
template<> struct Return<void> { Return(Void = {}) {} };
template<class T> using hidl_vec=std::vector<T>;
namespace power {
namespace V1_0 {
enum class Feature { POWER_FEATURE_DOUBLE_TAP_TO_WAKE };
enum class PowerHint { INTERACTION=2, LOW_POWER=5, SUSTAINED_PERFORMANCE=6, LAUNCH=8 };
inline std::string toString(PowerHint) { return "hint"; }
enum class Status {SUCCESS,FILESYSTEM_ERROR};
struct Voter {std::string name;uint64_t totalTimeInMsecVotedForSinceBoot=0,totalNumberOfTimesVotedSinceBoot=0;};
struct PowerStatePlatformSleepState {std::string name;uint64_t residencyInMsecSinceBoot=0,totalTransitions=0;bool supportedOnlyInSuspend=false;std::vector<Voter> voters;};
}
namespace V1_1 {struct PowerStateSubsystem {};struct PowerStateSubsystemSleepState {};}
namespace V1_2 {
enum class PowerHint {AUDIO_STREAMING=10,AUDIO_LOW_LATENCY=11};
inline std::string toString(PowerHint) {return "hint";}
}
namespace V1_3 {
enum class PowerHint {EXPENSIVE_RENDERING=12};
class IPower {
public:
using getPlatformLowPowerStats_cb=std::function<void(const hidl_vec<V1_0::PowerStatePlatformSleepState>&,V1_0::Status)>;
using getSubsystemLowPowerStats_cb=std::function<void(const hidl_vec<V1_1::PowerStateSubsystem>&,V1_0::Status)>;
virtual ~IPower()=default;
virtual Return<void> setInteractive(bool)=0;
virtual Return<void> powerHint(V1_0::PowerHint,int32_t)=0;
virtual Return<void> setFeature(V1_0::Feature,bool)=0;
virtual Return<void> getPlatformLowPowerStats(getPlatformLowPowerStats_cb)=0;
virtual Return<void> getSubsystemLowPowerStats(getSubsystemLowPowerStats_cb)=0;
virtual Return<void> powerHintAsync(V1_0::PowerHint,int32_t)=0;
virtual Return<void> powerHintAsync_1_2(V1_2::PowerHint,int32_t)=0;
virtual Return<void> powerHintAsync_1_3(PowerHint,int32_t)=0;
};
}}}
'''

HINTS = r'''
#pragma once
#include <atomic>
#include <map>
#include <memory>
#include <mutex>
#include <string>
namespace android::perfmgr {
class HintManager {
 std::mutex lock; std::map<std::string,bool> active;
public:
 inline static std::atomic<HintManager*> last=nullptr;
 static std::unique_ptr<HintManager> GetFromJSON(const std::string&) {
  auto p=std::make_unique<HintManager>();last.store(p.get());return p;
 }
 bool DoHint(const std::string& name) {std::lock_guard<std::mutex> l(lock);active[name]=true;return true;}
 bool EndHint(const std::string& name) {std::lock_guard<std::mutex> l(lock);active[name]=false;return true;}
 bool IsActive(const std::string& name) {std::lock_guard<std::mutex> l(lock);return active[name];}
};
}
'''

PROPS = r'''
#pragma once
#include <atomic>
#include <chrono>
#include <string>
#include <thread>
namespace android::base {
inline std::atomic<bool> init_block=true;
inline bool WaitForProperty(const std::string&,const std::string&) {
 while(init_block.load()) { std::this_thread::sleep_for(std::chrono::milliseconds(1)); }
 return true;
}
inline std::string GetProperty(const std::string&,const std::string& fallback) {return fallback;}
}
'''

TEST = r'''
#include "Power.h"
#include "power-helper.h"
#include <android-base/properties.h>
#include <cassert>
#include <chrono>
#include <climits>
#include <thread>
struct stat_pair rpm_stat_map[MAX_PLATFORM_STATS]={};
extern "C" int extract_platform_stats(uint64_t*) {return -1;}
using android::hardware::power::V1_3::implementation::Power;
using H=android::hardware::power::V1_0::PowerHint;
using R=android::hardware::power::V1_3::PowerHint;
using A=android::hardware::power::V1_2::PowerHint;
using namespace std::chrono_literals;
int main() {
 Power p;
 p.setInteractive(false);p.powerHint(H::LOW_POWER,1);
 auto manager=[](){return android::perfmgr::HintManager::last.load();};
 for(int n=0;n<1000 && (!manager() || !manager()->IsActive("LOW_POWER"));++n) {
  android::base::init_block=false;std::this_thread::sleep_for(1ms);
 }
 assert(manager() && manager()->IsActive("LOW_POWER"));
 auto on=[&](const std::string& h){return manager()->IsActive(h);};
 p.powerHint(H::LAUNCH,1);p.powerHint(H::INTERACTION,0);
 assert(!on("LAUNCH") && !on("INTERACTION"));
 p.powerHint(H::LOW_POWER,0);assert(!on("LOW_POWER"));
 p.powerHint(H::INTERACTION,0);assert(!on("INTERACTION"));
 p.setInteractive(true);
 p.powerHint(H::INTERACTION,0);assert(on("INTERACTION"));
 std::this_thread::sleep_for(550ms);assert(!on("INTERACTION"));
 p.powerHint(H::INTERACTION,INT_MAX);assert(on("INTERACTION"));
 p.powerHint(H::LAUNCH,1);assert(on("LAUNCH"));
 p.powerHintAsync_1_3(R::EXPENSIVE_RENDERING,1);assert(on("EXPENSIVE_RENDERING"));
 p.powerHintAsync_1_2(A::AUDIO_LOW_LATENCY,1);assert(on("AUDIO_LOW_LATENCY"));
 p.powerHint(H::LOW_POWER,1);
 assert(on("LOW_POWER") && !on("LAUNCH") && !on("INTERACTION") && !on("EXPENSIVE_RENDERING"));
 assert(on("AUDIO_LOW_LATENCY"));
 p.powerHint(H::LAUNCH,1);p.powerHint(H::INTERACTION,1);
 assert(!on("LAUNCH") && !on("INTERACTION"));
 p.powerHint(H::LOW_POWER,1);p.powerHint(H::LOW_POWER,0);
 assert(!on("LOW_POWER") && on("EXPENSIVE_RENDERING"));
 p.setInteractive(false);assert(!on("EXPENSIVE_RENDERING"));
 p.powerHintAsync_1_3(R::EXPENSIVE_RENDERING,0);
 p.setInteractive(true);assert(!on("EXPENSIVE_RENDERING"));
 for(int n=0;n<50;++n) {
  p.powerHint(H::INTERACTION,0);p.setInteractive(false);assert(!on("INTERACTION"));
  p.setInteractive(true);p.powerHint(H::INTERACTION,0);assert(on("INTERACTION"));
 }
 std::this_thread::sleep_for(550ms);assert(!on("INTERACTION"));
 p.powerHint(H::INTERACTION,INT_MAX);
 std::this_thread::sleep_for(1750ms);assert(!on("INTERACTION"));
 p.powerHint(H::LAUNCH,0);p.powerHintAsync_1_2(A::AUDIO_LOW_LATENCY,0);
 assert(!on("AUDIO_LOW_LATENCY"));
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="gm8-power-policy-") as tmp:
        root = Path(tmp)
        files = {
            "android/hardware/power/1.3/IPower.h": HIDL,
            "perfmgr/HintManager.h": HINTS,
            "android-base/properties.h": PROPS,
            "android-base/logging.h": '#pragma once\n#include <iostream>\n#define LOG(x) std::cerr\n#define PLOG(x) std::cerr\n',
            "android-base/file.h": '#pragma once\n#include <unistd.h>\nnamespace android::base {inline bool WriteFully(int fd,const void*p,size_t n){return write(fd,p,n)==static_cast<ssize_t>(n);}}\n',
            "android-base/unique_fd.h": '#pragma once\n#include <unistd.h>\nnamespace android::base {struct unique_fd {int fd;unique_fd(int f):fd(f){}~unique_fd(){if(fd>=0)close(fd);}int get(){return fd;}void reset(int f){if(fd>=0)close(fd);fd=f;}};}\n',
            "android-base/strings.h": "#pragma once\n",
            "utils/Trace.h": "#pragma once\n",
            "hidl/MQDescriptor.h": "#pragma once\n",
            "hidl/Status.h": "#pragma once\n",
            "test.cpp": TEST,
        }
        logs = '#pragma once\ntemplate<class...T> void gm8_log(T...){ }\n'
        for name in ("ALOGV", "ALOGW", "ALOGE", "ALOGI", "ALOGD"):
            logs += f'#define {name}(...) gm8_log(__VA_ARGS__)\n'
        for name in ("ALOGD_IF", "ALOGW_IF"):
            logs += f'#define {name}(condition,...) do{{if(condition)gm8_log(__VA_ARGS__);}}while(0)\n'
        files["utils/Log.h"] = logs
        for path, text in files.items():
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        output = root / "power-test"
        subprocess.run(["g++", "-std=c++17", "-pthread", "-Wall", "-Wextra", "-Werror",
                        "-Wno-sign-compare", "-I" + str(root), "-I" + str(ROOT),
                        "-I" + str(ROOT / "hidl"), str(ROOT / "hidl/Power.cpp"),
                        str(ROOT / "disp-power/InteractionHandler.cpp"), str(root / "test.cpp"),
                        "-o", str(output)], check=True)
        subprocess.run([str(output)], check=True, timeout=15)
    print("Power: real-source early events, saver caps, screen-off cancellation, rendering, audio and bounded/repeated interaction tests passed.")


if __name__ == "__main__":
    main()
