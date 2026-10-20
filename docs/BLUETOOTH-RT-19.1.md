# Bluetooth and display RT scheduling on the legacy HMP kernel

The live gm8-bt-canli.txt contains 12 instances of this immediate sequence:

```
libc: pthread_create sched_setscheduler(1, {1}) call failed: Operation not permitted
bt_osi_alarm: timer_create_internal unable to create timer with clock 7: Operation not permitted
alarm.cc(169): Check failed: false.
```

It also contains five SurfaceFlinger failures to set SCHED_FIFO on display-on.
The companion gm8-sensor-rt.txt ends with the inspected zygote in CPU group
/top-app and cpuset /foreground; both requested foreground/top-app RT runtime
values are zero. The earlier missing accounting hierarchy, DeviceConfig
permission and TCP parser errors are absent from this live capture.

## Cause and repair

Lineage 19.1 alarm.cc requests a priority-1 SCHED_FIFO SIGEV_THREAD timer.
Bionic's timer_create creates its callback pthread before issuing the kernel
timer syscall. Thus the logged clock-7 failure here is a callback thread
scheduling failure, not evidence of a missing CLOCK_BOOTTIME implementation.

The GM8 kernel enables CONFIG_RT_GROUP_SCHED. Its alloc_rt_sched_group creates
child groups with zero RT runtime. __sched_setscheduler returns EPERM for a
non-autogroup RT request in such a group; sched_rt_can_attach also rejects an
existing RT task entering it. The root group uses the global RT bandwidth.
The preceding performance-profile change moved zygote and display processes
into these unbudgeted children. This is a regression in that profile mapping.

Override all nine performance leaves to explicitly JoinCgroup cpu with an
empty Path (the root). Android libprocessgroup resolves it to /dev/cpuctl/tasks
for a thread and the root cgroup.procs for a process. The normal init ownership
and permissions already cover both files. This also moves a task out of a
child group, unlike an empty/no-op profile. Preflight rejects a missing leaf or
a child-group mapping so the same failure cannot silently recur.

All CPU performance classes now share the root CPU scheduling group; the
child-group cpu.shares distinctions are consequently not applied. Android's
separate cpuset profiles, framework scheduling priorities, IO priorities and
timer-slack aggregate actions remain. The device's foreground/top-app 0-7,
background/system-background/restricted 4-7 masks, camera cpuset and HMP power
hints are unchanged. This is not a new performance benchmark result.

Do not give every sibling a full RT budget: the kernel constrains the sum of
child bandwidths. Do not disable RT_GROUP_SCHED blindly either: this 3.18
cpu_cgroup_can_attach has an alternative branch that rejects non-fair tasks.
The repair needs no kernel change, unlimited RT budget, capability grant,
clock substitution or Bluetooth assertion removal.

## Sensor dump interpretation

At 09:38:53 the dump reports WakeLock Status: not held. All five active
connections have WakeLockRefCount 0, empty caches and zero pending flush events.
The two accelerometer clients are WindowOrientationListener and FaceDownDetector;
the significant-motion trigger has DeviceIdleController and two GMS clients.
The significant-motion sensor is one-shot/wake-up; its displayed 1 ms request
does not mean a continuous 1000 Hz event stream. This foreground snapshot does
not reproduce or resolve the earlier pending sensors.qti wake source during
screen-off suspend. No sensor daemon or framework listener is disabled.

## Validation

The host regression compiles the actual kernel RT admission branch and
sched_rt_can_attach with task/budget fixtures. Zero-budget children reproduce
EPERM and reject RT attachment; the root-budget fixture permits both. It also
compiles Android's actual cgroup path resolvers, checks every device leaf and
the merged system cpuset/IO/timer-slack aggregate actions.

```
python3 device/gm/GM8_sprout/tools/tests/rt_profiles_19_1_test.py --top .
```

These are source/host tests, not execution of the complete kernel scheduler.
After rebuilding the ROM and rebooting, check zygote's CPU membership is `/`,
enable Bluetooth and exercise pairing/playback, then toggle the screen and
check that the FIFO EPERM/abort sequence and display scheduling error no longer
appear. A full Android build and these phone checks remain pending. No data
format or clean build is required for this profile change. Camera property
labels from the preceding commit are included when updating this branch.

Sources: LineageOS lineage-19.1 system/bt/osi/src/alarm.cc,
bionic/libc/bionic/posix_timers.cpp, system/core/libprocessgroup/cgroup_map.cpp,
system/core/libprocessgroup/profiles/task_profiles.json and rootdir/init.rc;
GM8 lineage-19.1 kernel/sched/core.c and kernel/sched/rt.c.
