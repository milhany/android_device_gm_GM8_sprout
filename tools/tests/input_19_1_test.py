#!/usr/bin/env python3
"""Host regression for GM8's private resume quirk versus Android input properties."""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[5])
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--eventhub", type=Path)
    args = parser.parse_args()
    kernel = (args.kernel or args.top / "kernel/gm/msm8937").resolve()
    eventhub = (args.eventhub or args.top /
                "frameworks/native/services/inputflinger/reader/EventHub.cpp").read_text()

    # Compile the actual input_reset_device implementation with host lock stubs.
    core = (kernel / "drivers/input/input.c").read_text()
    reset = re.search(r"void input_reset_device\(struct input_dev \*dev\)\n\{.*?\n\}",
                      core, re.S).group()
    header = (kernel / "include/linux/input.h").read_text()
    field = re.search(r"\bbool\s+no_dummy_release\s*;", header).group()
    assignments = []
    for path in ("drivers/platform/msm/qpnp-power-on.c",
                 "sound/soc/codecs/wcd-mbhc-v2.c", "sound/soc/codecs/wcd9xxx-mbhc.c"):
        text = (kernel / path).read_text()
        assignment = re.search(r"([\w>.-]+)->no_dummy_release\s*=\s*true;", text)
        assert assignment, f"Missing private quirk assignment in {path}"
        assignments.append(assignment.group().replace(assignment[1], "dev"))

    # Use Android's real property classification and clock choice, not an
    # independently reimplemented condition. The ioctl acceptance condition
    # likewise comes from this kernel's evdev handler.
    classify = re.search(r"if \(device->propBitmask.test\(INPUT_PROP_ACCELEROMETER\)\) \{.*?\n    \}",
                         eventhub, re.S).group()
    clocks = re.search(r"int clockId = CLOCK_MONOTONIC;.*?(?=    bool usingClockIoctl)",
                      eventhub, re.S).group()
    evdev = (kernel / "drivers/input/evdev.c").read_text()
    accept = re.search(r"if \(i != CLOCK_MONOTONIC && i != CLOCK_REALTIME\)\n\s*return -EINVAL;",
                       evdev).group()

    source = r'''
#include <cassert>
#include <cerrno>
#include <ctime>
#include "input-event-codes.h"
struct input_dev {
    FIELD
    unsigned long propbit = 0;
    int mutex = 0, event_lock = 0, toggles = 0, releases = 0;
};
void mutex_lock(int*) {} void mutex_unlock(int*) {}
#define spin_lock_irqsave(lock, flags) ((void)(lock), (flags) = 0)
#define spin_unlock_irqrestore(lock, flags) ((void)(lock), (void)(flags))
void input_dev_toggle(input_dev* d, bool) { ++d->toggles; }
void input_dev_release_keys(input_dev* d) { ++d->releases; }
RESET
enum class InputDeviceClass { SENSOR = 1 };
struct Classes {
    unsigned bits = 0;
    void operator|=(InputDeviceClass c) { bits |= (unsigned)c; }
    bool test(InputDeviceClass c) const { return bits & (unsigned)c; }
};
struct PropertyBits {
    unsigned long bits;
    bool test(unsigned bit) const { return bits & (1UL << bit); }
};
struct Device { PropertyBits propBitmask; Classes classes; };
int selected_clock(unsigned long properties) {
    Device storage{{properties}, {}}, *device = &storage;
    CLASSIFY
    auto classes = device->classes;
    CLOCKS
    return clockId;
}
int accept_clock(int i) {
    {
        ACCEPT
    }
    return 0;
}
int main() {
    // The submitted log is reproduced by the old private bit 0x06: Android
    // chooses BOOTTIME, the old evdev rejects it and retains REALTIME.
    assert(selected_clock(1UL << 6) == CLOCK_BOOTTIME);
    assert(accept_clock(CLOCK_BOOTTIME) == -EINVAL);
    for (unsigned driver = 0; driver != 3; ++driver) {
        input_dev value{}, *dev = &value;
        switch (driver) { ASSIGNMENTS }
        assert(value.no_dummy_release);
        assert(value.propbit == 0);
        assert(selected_clock(value.propbit) == CLOCK_MONOTONIC);
        assert(accept_clock(selected_clock(value.propbit)) == 0);
        input_reset_device(dev);
        assert(value.releases == 0 && value.toggles == 0);
    }
    input_dev normal{};
    input_reset_device(&normal);
    assert(normal.releases == 1 && normal.toggles == 1);
    // Public sensor identification stays available for actual accelerometers.
    assert(INPUT_PROP_ACCELEROMETER == 6);
    assert(selected_clock(1UL << INPUT_PROP_ACCELEROMETER) == CLOCK_BOOTTIME);
}
'''
    for marker, value in {"FIELD": field, "RESET": reset, "CLASSIFY": classify,
                          "CLOCKS": clocks, "ACCEPT": accept,
                          "ASSIGNMENTS": "\n".join(f"case {i}: {a} break;"
                                                    for i, a in enumerate(assignments))}.items():
        source = source.replace(marker, value)
    with tempfile.TemporaryDirectory(prefix="gm8-input-") as temp:
        path = Path(temp)
        (path / "test.cpp").write_text(source)
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-iquote", str(kernel / "include/uapi/linux"), str(path / "test.cpp"),
                        "-o", str(path / "test")], check=True)
        subprocess.run([str(path / "test")], check=True)
    print("PASS: old clock-selection failure reproduced; all three private quirk users "
          "keep MONOTONIC and preserve resume behavior; normal reset remains intact.")


if __name__ == "__main__":
    main()
