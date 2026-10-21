# Android 12 runtime follow-up

The GPU 415 first-boot follow-up and status-bar/optional charging-HAL repairs are
documented in [BOOTLOG-20261021.md](BOOTLOG-20261021.md).

The owner reports working baseband, camera and physical keys. In the submitted
gm8-acilis-log.txt, Settings draws in 2678 ms while Snapchat installation and
verification are running. The log contains no Java fatal exception or native
fatal signal, but one earlier TikTok service ANR during boot/update load.
The measurement does not isolate one cause for all application launch delays.

## Accounting and scheduling

The log contains 225 occurrences of "No mounted process-group cgroup hierarchy",
including Settings process creation. Android 12's actual cgroup setup calls
Mkdir before mounting cpuacct. The old descriptor requests system ownership
for /acct; its existing-directory path calls lchown on /acct/. and fails on
read-only system-as-root before mounting the accounting controller.

Use mode 0000 and empty UID/GID to preserve the pre-existing mount point before
mount. Mount failures remain errors. Keep the prior mounted-v1 process tracking
repair for creation and termination; validate the actual mount/lifecycle on
hardware after rebuilding.

Kernel commit b0555eee97c41a59830d94134b4c882c75027220 enables CPUSETS, missing
from the previous defconfig. The real kernel Kconfig expansion confirms
CPUSETS, CPUACCT and the existing HMP scheduler together. HMP does not supply
the configured schedtune controller, so vendor performance profiles now join
the CPU-controller groups created by Android 12 init. The live Bluetooth
follow-up exposed zero RT budgets in these child groups; the current profiles
instead join the CPU-controller root, as detailed below. Foreground/top-app
cpusets use 0-7; background/system-background/restricted use the existing
little-cluster numbering 4-7. The camera cpuset configuration is retained.
Remove the unsupported schedtune descriptor and colocate write. No scheduler
replacement, overclock or longer boost is added.

## Google DeviceConfig role

Google Play services repeatedly fails WRITE_DEVICE_CONFIG checks. Android 12
defines that permission as signature|verifier|configurator; a privileged XML
allowlist alone cannot grant it. PackageManager uses the system package from
config_deviceConfiguratorPackageName for configurator permissions. The
framework default is empty. The pinned MindTheGapps sigma revision
f75a18fd21f0ceaa73b3c2c01bdb257aff976f2f supplies no override, while its system
GmsCore manifest requests WRITE_DEVICE_CONFIG.

The original device overlay was insufficient: the installed ROM resolved this
resource to org.protonaosp.deviceconfig and GmsCore still reported
WRITE_DEVICE_CONFIG: granted=false. Lineage's common PRODUCT_PACKAGE_OVERLAYS
entry overrides DEVICE_PACKAGE_OVERLAYS, including the original GMS string.

Move only this string into overlay-gms and prepend that directory to
PRODUCT_PACKAGE_OVERLAYS in lineage_GM8_sprout.mk. The first directory has the
highest priority; Soong reverses the directory list for aapt2. Keep the overlay
eligible for auto-RRO, matching the common Lineage overlay, so a generated
product RRO cannot restore the lower-priority Proton value. Other GM8 resources
retain their device-overlay priority. SimpleDeviceConfig and its platform
signature remain unchanged; its boot defaults are not removed.

Existing system-package, permission and SELinux checks remain in force. This
fix addresses the observed permission denial; the obfuscated GmsCore NPE is a
separate device validation item, not a proven consequence of that denial.
Rebuild and sign the complete ROM with the existing release keys, install the
update and reboot, then verify:

```bat
adb shell cmd overlay lookup android android:string/config_deviceConfiguratorPackageName
adb shell dumpsys package com.google.android.gms | findstr /C:"WRITE_DEVICE_CONFIG"
```

The resolved package must be com.google.android.gms and the installed system
GmsCore's WRITE_DEVICE_CONFIG grant must be true. Recheck the persistent GMS
process crashes and permission-denial logs separately. Updating only the
Dolby APK or boot image cannot change this framework/product overlay.

## Legacy TCP_INFO

The NetworkStack reports Bad position 65648/... every polling cycle. The first
decoded netlink message has length 228 with SHUTDOWN length 5, MARK length 8,
and INFO length 124 (120 bytes of tcp_info). Android 12's TcpInfo requires
later packet counters; it returns null without advancing on this older
layout. TcpSocketTracker subsequently treats TCP payload as another attribute.

Validate unsigned attribute lengths and message boundaries. Check whether
packet fields exist before parsing a bounded view, and advance the original
buffer to the aligned attribute end in every case. Preserve marks and modern
statistics. Unsupported old counters remain unavailable, not fabricated.
Malformed messages still fail validation. The network helper now validates all
three projects before edits, preserves local work, supports check/repeat and
rolls back partial application errors. Build records include NetworkStack.

## Validation and remaining work

The host setup regression compiles the actual Android directory functions
with read-only ownership syscall fixtures, reproduces the old failure and
accepts the new descriptor. The Java regression compiles real TcpInfo and
extracted real TcpSocketTracker methods: it reproduces the original failure,
checks short/modern layouts, marks, padding, message boundaries, malformed and
unsigned lengths. Synthetic packets contain no captured addresses or IDs.
Three-project apply/check/repeat tests include drift in the last project with
no earlier partial edits. Existing C++ BPF-loader/netd accounting tests pass.
Python/shell/XML/JSON checks pass. Full Android/kernel compilation and phone
tests remain necessary.

```sh
python3 device/gm/GM8_sprout/tools/tests/cgroup_setup_19_1_test.py --top .
python3 device/gm/GM8_sprout/tools/tests/tcp_info_19_1_test.py --top .
python3 device/gm/GM8_sprout/tools/tests/legacy_network_19_1_test.py --top .
```

After rebuilding both device and kernel, verify /acct is cpuacct-mounted,
cpuset tasks files exist, process creation/termination works, GmsCore receives
its DeviceConfig permission, and NetworkStack parsing remains aligned. Compare
cold/warm launches after app installation finishes; check Wi-Fi/mobile data,
background notifications and temperature/power consumption.

Audio DSP payload warnings need focused playback/recording evidence. The
60 Hz display-mode warning, fingerprint provider availability and camera reads
of unidentified default properties remain separate follow-ups. Isolated-app
file ownership denials and app ADB/serial/proc probes are not granted broad
policy access. Missing gralloc 3/4 and newer binder ioctl probes accompany
working legacy fallback. CPU_FREQ_STAT is already enabled; hotplug-related
missing CPU0 statistics are not repaired by pinning all CPUs online.

References: AOSP android-12.1.0_r22 NetworkStack; LineageOS lineage-19.1
libprocessgroup setup/default profiles, framework resource/permission
declarations and PackageManager configurator handling; GM8 kernel source and
the pinned MindTheGapps manifest/overlay.

The next capture confirms the preceding errors are absent in that recording
and exposes named camera property lookups, Bluetooth alarm initialization
aborts and sensor wakeups. See [BOOTLOG-20261020.md](BOOTLOG-20261020.md).

The live capture subsequently identifies Bluetooth's FIFO thread permission
failure and confirms zero child-group RT budgets. The repair and sensor dump
interpretation are in [BLUETOOTH-RT-19.1.md](BLUETOOTH-RT-19.1.md).

## Android 12 fingerprint provider registration

The owner reports fingerprint is unavailable. The current runtime capture
repeatedly reports FingerprintService: No providers found. The device has the
fingerprint feature XML and HAL packages, but its framework overlay does not
declare config_biometric_sensors. Lineage 19.1 AuthService.onStart consumes this
array, whose platform default is empty; registerAuthenticators passes an empty
HIDL fingerprint list to FingerprintService. Its addHidlProviders therefore
creates no Fingerprint21 provider, even if the native HAL is running.

Declare one sensor as 0:2:15 (ID 0, fingerprint modality, strong), using the
platform SensorConfig format. With the existing empty UDFPS configuration and
false power-button configuration, AuthService describes it as a rear sensor.
FPC and Sunwave are alternative native backends for that one physical sensor,
not two simultaneously registered sensors. Retain the initialized-driver
selector, mutually exclusive HAL startup, enrollment data and SELinux policy.
Preflight rejects an absent, duplicated or changed sensor declaration.

XML/resource checks and the actual Android SensorConfig parser pass on the
host. This repairs the missing framework registration; it does not establish
that driver probing, HAL/TEE startup, enrollment or authentication now work on
the phone. The supplied runtime ring contains no native fingerprint startup
sequence to validate those layers. Build framework resources with the ROM and
reboot, then verify a provider in dumpsys fingerprint, enroll a finger, and
test lock-screen and application authentication. If registration is present
but hardware is still unavailable, collect the initialized-driver property,
HAL service states and the native startup error before changing those layers.
No format, template deletion or clean build is required for this overlay.
