#!/usr/bin/env python3
"""Host-test the actual FPS function in the patch; Android metadata/property boundaries are mocked."""

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
static bool enabled = true;
static int logs = 0;
static bool property_get_bool(const char* name, bool fallback) {
    assert(std::string(name) == "persist.vendor.camera.gm8_fps30");
    assert(!fallback);
    return enabled;
}
#define ALOGI(...) (++logs)
struct Value {
    std::vector<int32_t> ints;
    std::vector<uint8_t> bytes;
    bool operator==(const Value& v) const { return ints == v.ints && bytes == v.bytes; }
};
struct Entry {
    size_t count;
    union { const int32_t* i32; const uint8_t* u8; } data;
};
class CameraMetadata {
public:
    std::map<uint32_t, Value> values;
    int updateError = 0;
    int writes = 0;
    Entry find(uint32_t tag) const {
        auto it = values.find(tag);
        if (it == values.end()) return {0, {nullptr}};
        if (!it->second.ints.empty()) return {it->second.ints.size(), {it->second.ints.data()}};
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
