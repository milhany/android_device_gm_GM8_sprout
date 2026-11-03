#!/usr/bin/env python3
"""Run actual Q stop/event-loop methods with delayed legacy driver callbacks."""
import argparse
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--top', type=Path, default=ROOT.parents[2])
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('wifi_patch', ROOT / 'tools/apply-wifi-stop-compat-17.1.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
sources = []
for name, old, new, anchor in patch.CHANGES:
    text = (args.top / name).read_text()
    applied = patch.transform(text, old, new, anchor)
    assert patch.transform(applied, old, new, anchor) == applied
    try:
        patch.transform(text.replace(anchor, 'unknown_wait_implementation'), old, new, anchor)
    except ValueError:
        pass
    else:
        raise AssertionError('Changed wait implementation was accepted')
    sources.append(applied)


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
    raise AssertionError('Unterminated actual Q method')


constant = re.search(r'static constexpr uint32_t kMaxStopCompleteWaitMs = \d+;', sources[0]).group()
actual = '\n'.join(method(sources[0], name) for name in (
    'wifi_error WifiLegacyHal::stop(', 'void WifiLegacyHal::runEventLoop()'))
with tempfile.TemporaryDirectory(prefix='gm8-q-wifi-stop-') as name:
    root = Path(name)
    source = root / 'test.cc'
    source.write_text(r'''
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <sstream>
#include <thread>
#define LOG(x) std::ostringstream()
#define CHECK_EQ(a,b) (assert((a)==(b)), std::ostringstream())
using wifi_error = int;
using wifi_handle = void*;
constexpr int WIFI_SUCCESS = 0, WIFI_ERROR_UNKNOWN = -1;
std::recursive_mutex mutex;
namespace hidl_sync_util {
std::unique_lock<std::recursive_mutex> acquireGlobalLock() {
 return std::unique_lock<std::recursive_mutex>(mutex);
}
}
std::function<void(wifi_handle)> on_stop_complete_internal_callback;
void onAsyncStopComplete(wifi_handle handle) { on_stop_complete_internal_callback(handle); }
struct InterfaceTool { void SetWifiUpState(bool) {} };
class WifiLegacyHal {
public:
 std::shared_ptr<InterfaceTool> owner{std::make_shared<InterfaceTool>()};
 std::weak_ptr<InterfaceTool> iface_tool_{owner};
 wifi_handle global_handle_ = reinterpret_cast<void*>(1);
 bool is_started_ = true, awaiting_event_loop_termination_ = false;
 std::condition_variable_any stop_wait_cv_;
 struct Functions {
  std::function<void(wifi_handle, void(*)(wifi_handle))> wifi_cleanup;
  std::function<void(wifi_handle)> wifi_event_loop;
 } global_func_table_;
 void invalidate() { global_handle_ = nullptr; }
 wifi_error stop(std::unique_lock<std::recursive_mutex>*, const std::function<void()>&);
 void runEventLoop();
};
''' + constant + '\n' + actual + r'''
using namespace std::chrono;
static void exercise(int cleanup_ms, bool expect_success) {
 WifiLegacyHal node;
 std::thread worker;
 std::atomic<int> callbacks{0};
 node.global_func_table_.wifi_event_loop = [](wifi_handle) {};
 node.global_func_table_.wifi_cleanup = [&](wifi_handle handle, void(*complete)(wifi_handle)) {
  worker = std::thread([&, handle, complete] {
   std::this_thread::sleep_for(milliseconds(cleanup_ms));
   {
    auto lock = hidl_sync_util::acquireGlobalLock();
    complete(handle);
   }
   node.runEventLoop();
  });
 };
 {
  auto lock = hidl_sync_util::acquireGlobalLock();
  auto start = steady_clock::now();
  int result = node.stop(&lock, [&] { ++callbacks; });
  auto elapsed = duration_cast<milliseconds>(steady_clock::now()-start).count();
  if (expect_success) {
   assert(result == WIFI_SUCCESS && callbacks == 1);
   assert(!node.is_started_ && !node.awaiting_event_loop_termination_);
   assert(elapsed >= cleanup_ms - 10);
  } else {
   // A genuine timeout must retain the error and pending state.
   assert(result == WIFI_ERROR_UNKNOWN && callbacks == 0);
   assert(node.is_started_ && node.awaiting_event_loop_termination_);
   assert(elapsed >= kMaxStopCompleteWaitMs - 10);
  }
 }
 worker.join();
 assert(!node.is_started_ && callbacks == 1);
 {
  auto lock = hidl_sync_util::acquireGlobalLock();
  assert(node.stop(&lock, [&] { ++callbacks; }) == WIFI_SUCCESS);
  assert(callbacks == 2);
 }
}
int main() {
 exercise(15, true);
 exercise(220, true);  // Observed GM8 cleanup exceeds Q's original 100 ms.
 exercise(1200, false);
}
''')
    binary = root / 'native-test'
    subprocess.run(['g++', '-std=c++14', '-pthread', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=undefined', '-fno-sanitize-recover=all',
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

print('PASS: actual Q stop/event-loop: fast and delayed success, bounded real timeout, already stopped')
print('Both source patches are idempotent and reject drift; HIDL/driver boundaries are fixtures.')
