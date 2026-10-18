#!/usr/bin/env python3
"""Host-test the actual FPS/automatic-AE patch functions with Android boundaries mocked."""

import argparse
from pathlib import Path
import subprocess
import tempfile


PRELUDE = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <map>
#include <string>
#include <vector>
#include <system/camera_metadata_tags.h>
using status_t = int;
using String16 = std::string;
constexpr status_t OK = 0;
constexpr status_t NO_MEMORY = -12;
static bool enabled = true;
static bool autoGainEnabled = false;
static int logs = 0;
static bool property_get_bool(const char* name, bool fallback) {
    assert(!fallback);
    if (std::string(name) == "persist.vendor.camera.gm8_auto_gain") return autoGainEnabled;
    assert(std::string(name) == "persist.vendor.camera.gm8_fps30");
    return enabled;
}
#define ALOGI(...) (++logs)
struct Value {
    std::vector<int32_t> ints;
    std::vector<uint8_t> bytes;
    std::vector<int64_t> longs;
    Value(std::vector<int32_t> i = {}, std::vector<uint8_t> b = {},
          std::vector<int64_t> l = {}) : ints(i), bytes(b), longs(l) {}
    bool operator==(const Value& v) const {
        return ints == v.ints && bytes == v.bytes && longs == v.longs;
    }
};
struct Entry {
    size_t count;
    union { const int32_t* i32; const uint8_t* u8; const int64_t* i64; } data;
};
class CameraMetadata {
public:
    std::map<uint32_t, Value> values;
    int updateError = 0;
    int writes = 0;
    int erases = 0;
    uint32_t failEraseTag = 0;
    bool copyFailure = false;
    Entry find(uint32_t tag) const {
        auto it = values.find(tag);
        if (it == values.end()) return {0, {nullptr}};
        if (!it->second.ints.empty()) return {it->second.ints.size(), {it->second.ints.data()}};
        if (!it->second.longs.empty()) {
            Entry entry{it->second.longs.size(), {nullptr}};
            entry.data.i64 = it->second.longs.data();
            return entry;
        }
        Entry entry{it->second.bytes.size(), {nullptr}};
        entry.data.u8 = it->second.bytes.data();
        return entry;
    }
    status_t update(uint32_t tag, const int32_t* data, size_t count) {
        assert(tag == ANDROID_CONTROL_AE_TARGET_FPS_RANGE && count == 2);
        if (updateError) return updateError;
        values[tag] = {std::vector<int32_t>(data, data + count), {}};
        ++writes;
        return OK;
    }
    bool isEmpty() const { return copyFailure || values.empty(); }
    status_t erase(uint32_t tag) {
        if (tag == failEraseTag) return NO_MEMORY;
        assert(values.erase(tag) == 1);
        ++erases;
        return OK;
    }
    void swap(CameraMetadata& other) {
        values.swap(other.values);
        std::swap(erases, other.erases);
        std::swap(writes, other.writes);
    }
};
static CameraMetadata base() {
    CameraMetadata m;
    m.values[ANDROID_CONTROL_AE_TARGET_FPS_RANGE].ints = {7, 30};
    m.values[ANDROID_CONTROL_MODE].bytes = {ANDROID_CONTROL_MODE_AUTO};
    m.values[ANDROID_CONTROL_AE_MODE].bytes = {ANDROID_CONTROL_AE_MODE_ON};
    m.values[ANDROID_CONTROL_AE_LOCK].bytes = {ANDROID_CONTROL_AE_LOCK_OFF};
    m.values[ANDROID_CONTROL_CAPTURE_INTENT].bytes = {ANDROID_CONTROL_CAPTURE_INTENT_PREVIEW};
    m.values[ANDROID_CONTROL_AF_MODE].bytes = {ANDROID_CONTROL_AF_MODE_CONTINUOUS_PICTURE};
    m.values[ANDROID_CONTROL_AE_EXPOSURE_COMPENSATION].ints = {0};
    return m;
}
'''

TESTS = r'''
static void testAutoGain() {
    auto request = []() {
        auto req = base();
        req.values[ANDROID_CONTROL_AE_TARGET_FPS_RANGE].ints = {30,30};
        req.values[ANDROID_SENSOR_SENSITIVITY].ints = {100};
        req.values[ANDROID_SENSOR_EXPOSURE_TIME].longs = {10263};
        req.values[ANDROID_CONTROL_POST_RAW_SENSITIVITY_BOOST].ints = {100};
        req.values[ANDROID_SENSOR_FRAME_DURATION].longs = {33000000};
        return req;
    };
    CameraMetadata info;
    info.values[ANDROID_SENSOR_INFO_SENSITIVITY_RANGE].ints = {100,1600};
    info.values[ANDROID_SENSOR_INFO_EXPOSURE_TIME_RANGE].longs = {10263,672085936};
    info.values[ANDROID_CONTROL_POST_RAW_SENSITIVITY_BOOST_RANGE].ints = {100,3199};
    auto run = [&](CameraMetadata req, bool changed, String16 package = "com.snapchat.android",
                   bool repeating = true, bool reprocess = false, size_t count = 1,
                   size_t physical = 1, const CameraMetadata* caps = nullptr) {
        auto before = req.values;
        int previousLogs = logs;
        assert(applyGm8SnapchatAutoGainCompat(&req, caps ? *caps : info, package,
                repeating, reprocess, count, physical) == OK);
        if (changed) {
            before.erase(ANDROID_SENSOR_SENSITIVITY);
            before.erase(ANDROID_SENSOR_EXPOSURE_TIME);
            before.erase(ANDROID_CONTROL_POST_RAW_SENSITIVITY_BOOST);
        }
        assert(req.values == before && req.writes == 0);
        assert(req.erases == (changed ? 3 : 0));
        assert(logs == previousLogs + (changed ? 1 : 0));
        assert(applyGm8SnapchatAutoGainCompat(&req, caps ? *caps : info, package,
                repeating, reprocess, count, physical) == OK);
        assert(req.values == before && req.erases == (changed ? 3 : 0));
    };
    run(request(), false); // New feature defaults off.
    autoGainEnabled = true;
    run(request(), true);
    auto req = request(); req.values.erase(ANDROID_CONTROL_AE_LOCK); run(req, true);
    req = request(); req.values[ANDROID_CONTROL_CAPTURE_INTENT].bytes = {ANDROID_CONTROL_CAPTURE_INTENT_VIDEO_RECORD}; run(req, true);
    for (auto name : {"org.lineageos.snap", "com.snapchat.android.other", ""}) run(request(), false, name);
    run(request(), false, "com.snapchat.android", false);
    run(request(), false, "com.snapchat.android", true, true);
    run(request(), false, "com.snapchat.android", true, false, 2);
    run(request(), false, "com.snapchat.android", true, false, 1, 2);
    for (auto tag : {ANDROID_CONTROL_MODE, ANDROID_CONTROL_AE_MODE,
                    ANDROID_CONTROL_CAPTURE_INTENT, ANDROID_CONTROL_AE_TARGET_FPS_RANGE,
                    ANDROID_SENSOR_SENSITIVITY, ANDROID_SENSOR_EXPOSURE_TIME,
                    ANDROID_CONTROL_POST_RAW_SENSITIVITY_BOOST}) {
        req = request(); req.values.erase(tag); run(req, false);
    }
    req = request(); req.values[ANDROID_CONTROL_AE_MODE].bytes = {ANDROID_CONTROL_AE_MODE_OFF}; run(req, false);
    req = request(); req.values[ANDROID_CONTROL_MODE].bytes = {ANDROID_CONTROL_MODE_OFF}; run(req, false);
    req = request(); req.values[ANDROID_CONTROL_AE_LOCK].bytes = {ANDROID_CONTROL_AE_LOCK_ON}; run(req, false);
    req = request(); req.values[ANDROID_CONTROL_CAPTURE_INTENT].bytes = {ANDROID_CONTROL_CAPTURE_INTENT_STILL_CAPTURE}; run(req, false);
    req = request(); req.values[ANDROID_CONTROL_AE_TARGET_FPS_RANGE].ints = {7,30}; run(req, false);
    req = request(); req.values[ANDROID_SENSOR_SENSITIVITY].ints = {200}; run(req, false);
    req = request(); req.values[ANDROID_SENSOR_EXPOSURE_TIME].longs = {33000000}; run(req, false);
    req = request(); req.values[ANDROID_CONTROL_POST_RAW_SENSITIVITY_BOOST].ints = {200}; run(req, false);
    req = request(); req.values[ANDROID_CONTROL_POST_RAW_SENSITIVITY_BOOST].ints = {100,100}; run(req, false);
    for (auto tag : {ANDROID_SENSOR_INFO_SENSITIVITY_RANGE,
                    ANDROID_SENSOR_INFO_EXPOSURE_TIME_RANGE,
                    ANDROID_CONTROL_POST_RAW_SENSITIVITY_BOOST_RANGE}) {
        auto unsupported = info; unsupported.values.erase(tag);
        run(request(), false, "com.snapchat.android", true, false, 1, 1, &unsupported);
    }
    auto unsupported = info;
    unsupported.values[ANDROID_CONTROL_POST_RAW_SENSITIVITY_BOOST_RANGE].ints = {100,100};
    run(request(), false, "com.snapchat.android", true, false, 1, 1, &unsupported);
    req = request(); auto before = req.values; req.failEraseTag = ANDROID_SENSOR_SENSITIVITY;
    assert(applyGm8SnapchatAutoGainCompat(&req, info, "com.snapchat.android", true, false, 1, 1) == NO_MEMORY);
    assert(req.values == before && req.erases == 0); // Failed second erase is atomic.
    req = request(); before = req.values; req.copyFailure = true;
    assert(applyGm8SnapchatAutoGainCompat(&req, info, "com.snapchat.android", true, false, 1, 1) == NO_MEMORY);
    assert(req.values == before && req.erases == 0);
    autoGainEnabled = false;
    puts("Automatic-AE opt-in/default/manual/capability guards and transactional erases passed");
}
int main() {
    CameraMetadata info;
    info.values[ANDROID_CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES].ints = {7,15,15,15,7,30,30,30};
    auto run = [&](CameraMetadata req, bool changed, String16 package = "com.snapchat.android",
                   bool repeating = true, bool reprocess = false, size_t count = 1,
                   size_t physical = 1, const CameraMetadata* caps = nullptr) {
        auto before = req.values;
        int previousLogs = logs;
        assert(applyGm8SnapchatFpsCompat(&req, caps ? *caps : info, package,
                repeating, reprocess, count, physical) == OK);
        assert(req.writes == (changed ? 1 : 0));
        assert(logs == previousLogs + (changed ? 1 : 0));
        if (changed) before[ANDROID_CONTROL_AE_TARGET_FPS_RANGE].ints = {30,30};
        assert(req.values == before); // No AF/intent/other metadata writes.
        assert(applyGm8SnapchatFpsCompat(&req, caps ? *caps : info, package,
                repeating, reprocess, count, physical) == OK);
        assert(req.writes == (changed ? 1 : 0)); // Already-fixed repeating request.
    };
    run(base(), true);
    auto req = base();
    req.values[ANDROID_CONTROL_CAPTURE_INTENT].bytes = {ANDROID_CONTROL_CAPTURE_INTENT_VIDEO_RECORD};
    run(req, true);
    req = base(); req.values.erase(ANDROID_CONTROL_AE_LOCK); run(req, true);
    enabled = false; run(base(), false); enabled = true;
    for (auto name : {"org.lineageos.snap", "com.snapchat.android.other", ""}) run(base(), false, name);
    run(base(), false, "com.snapchat.android", false);
    run(base(), false, "com.snapchat.android", true, true);
    run(base(), false, "com.snapchat.android", true, false, 2);
    run(base(), false, "com.snapchat.android", true, false, 1, 2);
    for (auto pair : {std::vector<int32_t>{30,30}, {15,30}, {7,24}, {7}, {}}) {
        req = base(); req.values[ANDROID_CONTROL_AE_TARGET_FPS_RANGE].ints = pair; run(req, false);
    }
    for (auto tag : {ANDROID_CONTROL_AE_TARGET_FPS_RANGE, ANDROID_CONTROL_MODE,
                    ANDROID_CONTROL_AE_MODE, ANDROID_CONTROL_CAPTURE_INTENT}) {
        req = base(); req.values.erase(tag); run(req, false);
    }
    req = base(); req.values[ANDROID_CONTROL_AE_MODE].bytes = {ANDROID_CONTROL_AE_MODE_OFF}; run(req, false);
    req = base(); req.values[ANDROID_CONTROL_MODE].bytes = {ANDROID_CONTROL_MODE_USE_SCENE_MODE}; run(req, false);
    req = base(); req.values[ANDROID_CONTROL_CAPTURE_INTENT].bytes = {ANDROID_CONTROL_CAPTURE_INTENT_STILL_CAPTURE}; run(req, false);
    req = base(); req.values[ANDROID_CONTROL_AE_LOCK].bytes = {ANDROID_CONTROL_AE_LOCK_ON}; run(req, false);
    req = base(); req.values[ANDROID_CONTROL_AE_LOCK].bytes = {0,0}; run(req, false);
    for (auto pairs : {std::vector<int32_t>{7,30}, {30,30,7}, {}}) {
        CameraMetadata unsupported;
        unsupported.values[ANDROID_CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES].ints = pairs;
        run(base(), false, "com.snapchat.android", true, false, 1, 1, &unsupported);
    }
    req = base(); auto original = req.values; req.updateError = -12;
    assert(applyGm8SnapchatFpsCompat(&req, info, "com.snapchat.android", true, false, 1, 1) == -12);
    assert(req.values == original && req.writes == 0);
    puts("Camera FPS guards, exact supported pair, unchanged metadata and update errors passed");
    testAutoGain();
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-tags", type=Path,
                        default=Path(__file__).resolve().parents[5] /
                        "system/media/camera/include/system/camera_metadata_tags.h")
    args = parser.parse_args()
    device = Path(__file__).resolve().parents[2]
    patch = (device / "patches/frameworks_av/0001-gm8-snapchat-fixed-fps-test.patch").read_text()
    additions = "\n".join(line[1:] for line in patch.splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
    start = additions.index("static status_t applyGm8SnapchatFpsCompat(")
    end = additions.index("\n}\n", start) + 3
    function = additions[start:end]
    gain_patch = (device / "patches/frameworks_av/0002-gm8-snapchat-auto-gain-test.patch").read_text()
    gain_additions = "\n".join(line[1:] for line in gain_patch.splitlines()
                               if line.startswith("+") and not line.startswith("+++"))
    start = gain_additions.index("static status_t applyGm8SnapchatAutoGainCompat(")
    end = gain_additions.index("\n}\n", start) + 3
    function += gain_additions[start:end]
    with tempfile.TemporaryDirectory(prefix="gm8-camera-fps-") as temp:
        root = Path(temp)
        header = root / "system/camera_metadata_tags.h"
        header.parent.mkdir()
        header.write_bytes(args.metadata_tags.read_bytes())
        source = root / "test.cpp"
        source.write_text(PRELUDE + function + TESTS)
        binary = root / "test"
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-I", str(root), str(source), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
