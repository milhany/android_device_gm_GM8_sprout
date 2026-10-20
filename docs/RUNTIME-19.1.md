# Android 12 runtime follow-up

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
the CPU-controller groups created by Android 12 init. Foreground/top-app
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

Designate com.google.android.gms through the framework overlay for this
GApps-required product. Existing system-package, permission and SELinux checks
remain in force. Verify the resolved resource and permission after rebuilding
framework resources and rebooting.

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
