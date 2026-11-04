# GM8 Q: update-time dexopt and the remaining launch investigation

## Evidence

The supplied runtime snapshot was taken about 15 minutes after boot. It does
not capture the entire slow-launch interval:

- top reports 768/800 percent idle (about 96% aggregate CPU idle), zero I/O
  wait, and no running dex2oat. This does not rule out CPU, storage, reclaim or
  thermal bottlenecks during an earlier application launch.
- dumpsys reports 1,541,296 KiB used RAM and 1,554,043 KiB Free RAM, the latter
  including cached process PSS and kernel cache. This is not a measurement of
  MemAvailable and must not be interpreted as all immediately unused memory.
- ZRAM uses 88,588 KiB physical memory for 277,700 KiB swapped data, with a
  1,048,572 KiB logical capacity. This snapshot does not justify enlarging it.
- Snapchat, YouTube, YouTube Music and TikTok's base APK already report
  speed-profile. Their delays cannot all be attributed to missing dexopt.
- TikTok's split_df_a_dex.apk and Instagram report verify with reason boot.
- The preceding log captures Chrome Displayed +9s654ms and 290 skipped frames,
  concurrent post-boot dexopt, Google initialization and EGL context errors.
  Neither the EGL messages nor idle top establishes the launch's critical path.

## Included correction

Set `pm.dexopt.boot=quicken` in the normal system properties. Q's post-boot
update job uses REASON_BOOT without profile merging. The default verify filter
can leave invalidated APKs/splits at verification-only until idle optimization.
Use the same lightweight quickening filter Q normally uses for first boot.
This is a limited bytecode preparation change, not full ahead-of-time compilation
and not a claim that the overall launch problem is solved.

Normal installs and idle optimization remain speed-profile. Existing profiles
and application data are preserved. No per-application privileged worker or
startup compile-all loop is added. The update pass can take longer and write
more storage than verify; measure the completed pass rather than judging its
temporary activity as steady-state performance. Cases where Q intentionally
forces verification (for example embedded dex) still follow the framework.

Source checks require a single override. The target-files check resolves the
effective normal-OS properties and rejects a conflicting packaged policy before
signing. Full Android build and hardware performance validation remain pending.

## Validation on the device

After installing the candidate with the existing keys, check:

```text
adb shell getprop pm.dexopt.boot
adb shell getprop pm.dexopt.install
adb shell getprop pm.dexopt.bg-dexopt
```

Expected: quicken, speed-profile, speed-profile. After the post-boot job has
finished, inspect `adb shell dumpsys package dexopt`. The two previously
verification-only examples are useful checks, but actual reported states take
precedence over assumptions about which packages the job selected.

For remaining launch stalls, capture a bounded atrace while reproducing the
launch, with CPU scheduling/frequencies, graphics, window/activity management,
Binder, disk and memory reclaim categories if supported by `atrace --list_categories`.
Compare the same application, launch type, screen state and thermal conditions.
Do not reset profiles, drop caches, disable thermal protection or simultaneously
alter GPU blobs, CPU voltage and frequency. Those changes confound attribution.

No CPU/GPU overclock, undervolt, LMK threshold, heap limit, ZRAM size, GPU blob,
hardware-composer or UBWC policy changes are part of this candidate. Those need
their own workload evidence; a shared symptom on Android 10 and 12 alone does
not prove a shared kernel fault.

## Primary source references

- [Q runtime defaults](https://github.com/LineageOS/android_build/blob/lineage-17.1/target/product/runtime_libart.mk):
  first-boot=quicken, boot=verify, install/bg-dexopt=speed-profile.
- [Q BackgroundDexOptService](https://github.com/LineageOS/android_frameworks_base/blob/lineage-17.1/services/core/java/com/android/server/pm/BackgroundDexOptService.java):
  postBootUpdate uses REASON_BOOT without profile merging; idleOptimization is
  a separate path.
- [Q PackageDexOptimizer](https://github.com/LineageOS/android_frameworks_base/blob/lineage-17.1/services/core/java/com/android/server/pm/PackageDexOptimizer.java):
  per-APK/split compilation and getRealCompilerFilter exceptions.
