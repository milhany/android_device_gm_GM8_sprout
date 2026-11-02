#!/usr/bin/env python3
"""Host-test actual power code with Android logging/HintManager boundary stubs."""
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
CPP = ROOT / 'power-libperfmgr/disp-power/InteractionHandler.cpp'
HEADER = CPP.with_suffix('.h')
POWER = ROOT / 'power-libperfmgr/hidl/Power.cpp'


def method(source, signature):
    start = source.index(signature)
    begin = source.index('{', start)
    depth = 0
    for i in range(begin, len(source)):
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError('Unterminated method: ' + signature)


with tempfile.TemporaryDirectory(prefix='gm8-q-power-') as temporary:
    root = Path(temporary)
    (root / 'utils').mkdir()
    (root / 'perfmgr').mkdir()
    (root / 'utils/Log.h').write_text('''#pragma once
#include <cstdio>
#define ALOGE(...) do { if (false) std::fprintf(stderr, __VA_ARGS__); } while (0)
#define ALOGW(...) ALOGE(__VA_ARGS__)
#define ALOGV(...) ALOGE(__VA_ARGS__)
#define ALOGW_IF(c, ...) do { if (c) ALOGW(__VA_ARGS__); } while (0)
''')
    (root / 'utils/Trace.h').write_text('#pragma once\n')
    (root / 'perfmgr/HintManager.h').write_text('''#pragma once
#include <atomic>
#include <string>
namespace android { namespace perfmgr {
class HintManager {
 public:
  std::atomic<int> acquired{0}, released{0};
  bool DoHint(const std::string&) { ++acquired; return true; }
  bool EndHint(const std::string&) { ++released; return true; }
};
}}
''')
    # Expose state for assertions without changing the production .cpp body.
    (root / HEADER.name).write_text(HEADER.read_text().replace('  private:', '  public:'))
    shutil.copyfile(CPP, root / CPP.name)
    (root / 'interaction_test.cpp').write_text(r'''
#include <cassert>
#include <chrono>
#include <climits>
#include <thread>
#include "InteractionHandler.h"
using namespace std::chrono;
static void duration_case(int32_t input, int32_t expected) {
 auto hints = std::make_shared<HintManager>();
 InteractionHandler handler(hints);
 assert(handler.Init());
 handler.Acquire(input);
 {
  std::lock_guard<std::mutex> lock(handler.mLock);
  assert(handler.mDurationMs == expected);
 }
 handler.Exit();
 assert(hints->acquired == 1 && hints->released == 1);
 handler.Exit();
 assert(hints->released == 1);
}
int main() {
 duration_case(-1, 600);
 duration_case(0, 600);
 duration_case(900, 900);
 duration_case(INT_MAX, 5650);
 auto hints = std::make_shared<HintManager>();
 InteractionHandler handler(hints);
 assert(handler.Init());
 handler.Acquire(0);
 const auto deadline = steady_clock::now() + seconds(2);
 while (!hints->released && steady_clock::now() < deadline)
  std::this_thread::sleep_for(milliseconds(10));
 assert(hints->released == 1);
 handler.Exit();
 assert(hints->released == 1);
}
''')
    compiler = shutil.which('g++') or 'g++'
    flags = [compiler, '-std=c++14', '-pthread', '-fsanitize=undefined',
             '-fno-sanitize-recover=all', '-I', str(root)]
    subprocess.run(flags + [str(root / CPP.name), str(root / 'interaction_test.cpp'),
                            '-o', str(root / 'interaction_test')], check=True)
    subprocess.run([str(root / 'interaction_test')], check=True, timeout=10)

    source = POWER.read_text()
    hint = method(source, 'Return<void> Power::powerHint(')
    stats = method(source, 'Return<void> Power::getPlatformLowPowerStats(')
    (root / 'power_test.cpp').write_text(r'''
#include <cassert>
#include <atomic>
#include <functional>
#include <memory>
#include <string>
#include <vector>
#include <cstdint>
#include <cerrno>
#include "utils/Log.h"
#define ALOGD_IF(c, ...) do { if (c) ALOGE(__VA_ARGS__); } while (0)
enum class PowerHint_1_0 { INTERACTION, SUSTAINED_PERFORMANCE, LAUNCH, LOW_POWER };
namespace android { namespace hardware { namespace power { namespace V1_0 {
inline std::string toString(PowerHint_1_0) { return "hint"; }
}}}}
template <typename T> using Return = int;
static int Void() { return 0; }
struct Hints {
 bool sustained_supported = false;
 int launches = 0, ends = 0;
 bool DoHint(const std::string& name) {
  if (name == "SUSTAINED_PERFORMANCE") return sustained_supported;
  if (name == "LAUNCH") ++launches;
  return true;
 }
 bool EndHint(const std::string&) { ++ends; return true; }
};
struct Interaction { int calls = 0; void Acquire(int) { ++calls; } };
enum class Status { SUCCESS, FILESYSTEM_ERROR };
enum { RPM_MODE_XO, RPM_MODE_VMIN, RPM_MODE_MAX, XO_VOTERS_START = RPM_MODE_MAX,
       VOTER_APSS = XO_VOTERS_START, VOTER_MPSS, VOTER_ADSP, VOTER_SLPI, MAX_PLATFORM_STATS };
constexpr int MAX_RPM_PARAMS = 2, PLATFORM_SLEEP_MODES_COUNT = 2,
              XO_VOTERS = 4, VMIN_VOTERS = 0, RPM_CLK = 19200;
struct Pair { const char* label; };
Pair rpm_stat_map[] = {{"XO"}, {"VMIN"}, {"APSS"}, {"MPSS"}, {"ADSP"}, {"SLPI"}};
int stats_error = 0;
int extract_platform_stats(uint64_t*) { return stats_error; }
template <typename T> using hidl_vec = std::vector<T>;
struct Voter { std::string name; uint64_t totalTimeInMsecVotedForSinceBoot;
               uint64_t totalNumberOfTimesVotedSinceBoot; };
struct PowerStatePlatformSleepState { std::string name; uint64_t residencyInMsecSinceBoot;
 uint64_t totalTransitions; bool supportedOnlyInSuspend; std::vector<Voter> voters; };
using getPlatformLowPowerStats_cb = std::function<void(hidl_vec<PowerStatePlatformSleepState>, Status)>;
class Power {
 public:
  std::atomic<bool> mReady{true}, mSustainedPerfModeOn{false};
  std::shared_ptr<Hints> mHintManager = std::make_shared<Hints>();
  std::shared_ptr<Interaction> mInteractionHandler = std::make_shared<Interaction>();
  Return<void> powerHint(PowerHint_1_0 hint, int32_t data);
  Return<void> getPlatformLowPowerStats(getPlatformLowPowerStats_cb);
};
''' + hint + '\n' + stats + r'''
int main() {
 Power p;
 p.powerHint(PowerHint_1_0::SUSTAINED_PERFORMANCE, 1);
 assert(!p.mSustainedPerfModeOn);
 p.powerHint(PowerHint_1_0::INTERACTION, 0);
 p.powerHint(PowerHint_1_0::LAUNCH, 1);
 assert(p.mInteractionHandler->calls == 1 && p.mHintManager->launches == 1);
 p.mHintManager->sustained_supported = true;
 p.powerHint(PowerHint_1_0::SUSTAINED_PERFORMANCE, 1);
 assert(p.mSustainedPerfModeOn);
 p.powerHint(PowerHint_1_0::INTERACTION, 0);
 assert(p.mInteractionHandler->calls == 1);
 p.powerHint(PowerHint_1_0::SUSTAINED_PERFORMANCE, 0);
 assert(!p.mSustainedPerfModeOn);
 p.powerHint(PowerHint_1_0::INTERACTION, 0);
 assert(p.mInteractionHandler->calls == 2);
 stats_error = -ENOENT;
 p.getPlatformLowPowerStats([](hidl_vec<PowerStatePlatformSleepState> states, Status status) {
  assert(states.empty() && status == Status::FILESYSTEM_ERROR);
 });
 stats_error = 0;
 p.getPlatformLowPowerStats([](hidl_vec<PowerStatePlatformSleepState> states, Status status) {
  assert(states.size() == 2 && status == Status::SUCCESS);
 });
}
''')
    subprocess.run(flags + [str(root / 'power_test.cpp'), '-o', str(root / 'power_test')], check=True)
    subprocess.run([str(root / 'power_test')], check=True, timeout=10)

print('PASS: actual interaction timing/overflow/expiry/teardown and Power hint/status behavior')
print('Android boundaries are stubbed; this does not validate HAL ABI, sysfs, thermal behavior or hardware.')
