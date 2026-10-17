# GM8 power hint compatibility

`log(9).txt` shows repeated CPU0 cpufreq ENOENT errors and initial
`sched_boost=0` EINVAL errors, plus an absent `/d/system_stats` interface.

## CPU hotplug

This GM8 kernel's `drivers/cpufreq/cpufreq.c` stores the policy kobject below
the current policy CPU. `update_policy_cpu()` moves it when that CPU goes
offline; this is not the newer `/sys/devices/system/cpu/cpufreq/policy0` layout.
A fixed CPU0 path can disappear while the policy is still available on CPU1.

Each CPU frequency node now declares `FallbackPaths` for the other CPUs in its
same cluster: CPU0..3 or CPU4..7. FileNode resolves those explicit aliases on
each update and dump, only after ENOENT/ENOTDIR. It never falls back across
clusters or masks access/I/O errors. The existing retry remains for a fully
offline cluster. No frequency values, thermal limits or core hotplug limits
are changed. A slow-write warning indicates a measured syscall duration and
is retained.

## Reference-counted scheduler boost

`kernel/sched/fair.c:sched_set_boost()` increments a vote for value 1 and
decrements it for 0; releasing when the counter is already zero returns
EINVAL. This is not an idempotent reset-to-zero control. `SchedBoost` now has
`ResetOnInit=false`, with default index explicitly pointing to 0. Launch still
adds/removes its boost vote on state transitions. Startup no longer releases
an unowned vote. Other processes' votes are not cleared.

## Optional RPM statistics

The kernel exports `rpm_stats`, not the combined `system_stats` format expected
by this HAL helper. Those formats must not be interchanged just by changing
the filename. Missing system_stats now returns an empty result with the power
1.0 HAL's `FILESYSTEM_ERROR` status, rather than `SUCCESS` and invented zero
statistics. Expected missing-file opens do not emit an error each time; other
filesystem failures still do.

## MDSS display idle input

GM8's `mdss_fb.c` exports `/sys/class/graphics/fb0/idle_notify`, returning
`yes` when idle and `no` while idle work is pending. It does not expose the
`idle_state` interface used by newer display drivers. The interaction handler
now accepts this third path and its actual value format, with read-only
SELinux access to that exact attribute. Missing optional paths use the
existing timed hint fallback; access errors remain visible. All powerhint
file nodes explicitly declare `Type=File` to avoid the parser's misleading
missing-Type error messages. No frequency or boost-duration values changed.

## Checks and deployment

Host-test the actual fallback opener with:

```sh
cd device/gm/GM8_sprout
g++ -std=c++17 -Wall -Wextra -Werror -Ipower-libperfmgr/libperfmgr/include \
  tools/tests/power_node_paths_test.cpp -o /tmp/gm8-node-paths
/tmp/gm8-node-paths
```

This covers the primary alias, two successive hotplug aliases, a real open
error that must not fall back, and the all-missing retry case. Power config
actions must still reference a declared node and one of its Values.

The power changes require the new `libperfmgr`, power service and
`/vendor/etc/powerhint.json` together. An updated Dolby APK does not apply them.
Before building the next full ROM, compile
`m android.hardware.power@1.3-service.gm-libperfmgr libperfmgr_test -j32` and run
the target tests on hardware. Check CPU aliases during hotplug, launch and
interaction boosts, boost vote release, ordinary app use, and suspend/resume.
Host filesystem tests cannot verify the physical phone's sysfs/SELinux policy.
