# GM8 application-compilation experiment

The 2026-10-18 bugreport records TikTok compiler times of 88023 ms for base.apk
and 153292 ms for split_df_a_dex.apk (about four minutes combined). Its shared
compiler UID also accumulated about eleven minutes of **CPU time** in dex2oat32;
CPU time across threads is not elapsed installation time. The earlier complete
ten-minute installation window is not present in the retained log buffers.
The package reports arm64 speed-profile / install-dm output. Data is 80% free,
and this recording contains no explicit eMMC timeout/filesystem corruption.
That is not a storage-health certification.

Android 11 installd recognizes `dalvik.vm.dex2oat64.enabled`. The experimental
ROM enables the ARM64 compiler process on this ARM64 device. A 64-bit compiler
can produce both target instruction sets; this does not force all apps to 64-bit.
It may improve large compilation workloads, but can also increase peak memory
use on the 3 GB GM8. **No speedup or lower consumption is claimed before a
controlled phone comparison.**

Install/background compiler filters, cloud profiles, verification and heap/thread
limits remain unchanged. In particular, speed-profile is retained: skipping
installation optimization globally can move work into first launch/JIT and
increase runtime CPU load. Existing artifacts are not cleared or force-rebuilt.

## Phone comparison

After the matching ROM boots, verify:

```sh
adb shell getprop dalvik.vm.dex2oat64.enabled
adb shell ls -l /apex/com.android.art/bin/dex2oat64
```

For an optional forced **compilation benchmark of the already installed app**
(not a download or an uninstall; it may take several minutes):

```sh
adb shell "time cmd package compile -f -m speed-profile com.zhiliaoapp.musically"
```

Capture logcat and dumpsys package before/after, and inspect the compiler process
while it runs. Use the same APK/profile, charging state, temperature and other
workload for a 32/64-bit comparison. Warm caches and prior runs affect results.
Watch for low-memory kills, more swapping or longer elapsed time.

On a userdebug build with root debugging enabled, a reversible runtime comparison
can select the old compiler for subsequent operations:

```sh
adb root
adb shell setprop dalvik.vm.dex2oat64.enabled false
adb shell getprop dalvik.vm.dex2oat64.enabled
```

Set it to true to restore the experiment; a reboot restores the ROM's configured
default. If setprop is denied, keep the denial log rather than weakening SELinux.
To permanently revert, remove that one property from system.prop and build the
matching ROM. Do not clear all app data/dalvik caches or disable Play Protect.
