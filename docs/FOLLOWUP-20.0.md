# Chrome, performance HAL, WLAN statistics and CPU accounting

## Source changes

### Chrome isolated process groups

The captured failures are system_server trying to create `/acct/uid_90000` and
other isolated UID groups after Chrome's app zygote forks. SDK33 processgroup
inherits mode/UID/GID from the hierarchy root. The legacy cpuacct descriptor
deliberately leaves ownership empty because `/acct` initially belongs to the
read-only system-as-root image. However, the mounted cgroup root was never
assigned to system, leaving system_server unable to create these groups.

The paired system/core patch now sets system:system, mode 0750, only after a
successful v1 cpuacct mount on the explicit GM8 legacy policy. The original
read-only mount point stays untouched. Newly created UID/PID groups inherit this
system ownership, not the isolated application UID. Failed mount/ownership setup
still fails. No world-writable permissions, blanket SELinux allow or process-group
creation bypass is added. A reboot recreates the hierarchy, so no on-device
recursive ownership repair is needed.

### Camera/audio IPerf

The vendor already packages and starts `vendor.qti.hardware.perf@1.0-service`.
The bugreport lists the running process, and its ELF imports confirm the actual
`vendor::qti::hardware::perf::V1_0::IPerf` registerAsService ABI. The missing piece
is the device VINTF declaration. Add the existing hwbinder 1.0 IPerf/default
instance; do not invent an implementation or enable the separate disabled legacy
perfd init service. Existing power/thermal policy is not changed. Real registration
and client lock acquisition remain device acceptance checks.

### WLAN link-layer statistics

The selected wcn6740 HAL requires TS_DUTY_CYCLE, which the older firmware does not
return. Its parser then discards the entire response, including real counters.
Only devices with `ro.vendor.gm8.legacy_wifi_stats=true` now accept absence of this
new field. The compatibility duty-cycle value is 100, the no-time-slicing default;
it is not a measured duty cycle and cannot characterize unreported MCC scheduling.
Other received fields/counters remain intact. Devices without this capability
keep the previous missing-field error. Present duty-cycle values must have exactly
one byte and be within 0..100. Other mandatory fields are still mandatory.

The HAL gets read access to this exact immutable vendor property only. Both WLAN
library variants explicitly link libcutils for property_get_bool. Driver/firmware,
network security, scans, roaming and power-saving settings are unchanged.

## CPU accounting: what the evidence actually establishes

The same bugreport contains a successful read of cpu0's stats/time_in_state:

```
960000 79888
1094400 67397
1209600 1291
1248000 3248
1344000 250
1401000 30868
```

Therefore the frequency residency counter exists; earlier ENOENT lines do not
establish an absent CONFIG_CPU_FREQ_STAT implementation. The kernel includes its
driver and Kconfig defaults it on. The reader already handles a counter reset on
hotplug. Transient policy/core availability is a hypothesis, not proven by the
earlier failed opens. No CPU clock or thermal changes are justified by them.

The separate `/proc/uid_time_in_state` and `/proc/self/time_in_state` interfaces
are not provided by this legacy kernel. Enabling its older global cpufreq stats
driver cannot add these newer UID/TID APIs. They remain an accounting limitation,
not evidence that the CPU governor is broken. No fake proc counters or success
values are added.

The current power profile contains legacy cpu.speeds/cpu.active arrays. SDK33's
PowerProfile expects cluster-specific keys and falls back to one core/one speed
when they are absent. Its seven legacy frequency entries also differ from the
six residency rows above. The publicly available GM8 Android 8.1 factory
framework-res power_profile has the same seven entries and current estimates;
it does not supply a matching modern calibration. Copying it again would not
resolve this. A correct cluster/power profile and any UID/TID accounting backport
remain open; they need verified policy topology and calibration rather than
invented power values. These source changes do not claim improved physical
battery drain or full per-app energy attribution.

Factory input reviewed: TadiT7/gm_gm8_sprout_dump, branch
msm8937_64-user-8.1.0-OPM1.171019.011-411-release-keys,
system/system/framework/framework-res.apk, SHA256
76d6d415942b354c63d528621f0cb5e0204442e1083e6b9763c1d6d019a52382.
The binary XML was decoded for comparison; the APK is not added to this repo.

## Verification and remaining acceptance

Host regressions compile the actual setup and process-group functions against
explicit read-only/mount/DAC shims. They reproduce system_server EACCES before
the repair, create isolated UID/PID groups afterward, and check mount/ownership
failure paths and isolation of the legacy branch. Actual WLAN parser tests cover
legacy absence, modern presence, malformed values and missing mandatory fields.
Both predecessors fail these regressions. The complete runtime stack includes
these tests and preserves pristine/prefix/repeat/conflicting source handling.

The full ARM/Android build, compiled SELinux/VINTF and phone checks remain pending.
Use the same full runtime build and existing-key signing workflow. On the device,
check Chrome group creation, IPerf service discovery and camera/audio requests,
and real WLAN statistics. CPU UID/TID APIs, calibrated power estimates, LCD
ambient-display blanking and the proprietary display-daemon crash are still open.
