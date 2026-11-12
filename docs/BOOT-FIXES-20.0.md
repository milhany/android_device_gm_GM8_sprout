# SDK33 first-boot compatibility batch

This batch follows the first successful GM8 Android 13 boot recorded on
2026-11-12. It addresses the actionable source/configuration findings from
`FIRSTBOOT-LOG-20261112.md` in one candidate, retaining the existing signing keys,
3.18 kernel branch, firmware, SELinux enforcement and unencrypted F2FS policy.
Hardware acceptance of this new candidate is pending.

## Changes and evidence

| Finding | Change | Remaining acceptance |
| --- | --- | --- |
| AIDL supplicant wait and Wi-Fi timeouts | Install upstream AIDL init RC and remove the old same-name HIDL service from init.qcom.rc. Package gates require exactly one matching RC, executable and VINTF instance. | Scan, association, DHCP/DNS, reconnect, WPA3 and hotspot. |
| Failed blkio/memcg/cgroup-v2 mounts and recurring task-profile writes | Explicit read-only `ro.vendor.gm8.legacy_cgroups=true` selects a complete paired vendor policy. Mount only CPU, cpuset and cpuacct; retain all 40 named profiles and 15 aggregate profiles, with the prior HMP CPU placement. | Verify mounted controllers, process cleanup and task placement on device. |
| Unsupported I/O-group, memory-group and uclamp policy | Remove their actions/attributes from the complete legacy profile database. Unsupported profile names remain valid no-ops, rather than attempting absent control files. This does not implement blkio QoS, memcg limits, cached-app freezing or uclamp on 3.18. | Measure actual memory pressure and application switching; this change is not a RAM/benchmark guarantee. |
| GPU memory collector waits for eBPF readiness | GpuMem skips initialization and detach when the existing eBPF capability is explicitly false. Default/modern behavior remains unchanged and readiness is not fabricated. | GPU service stays responsive; memory eBPF statistics are unavailable on this kernel. |
| IMS video codec cannot load camera callback library | Install the existing source-built `vendor.qti.hardware.camera.device@1.0` system_ext interface. Preflight requires its source; packaged checks require ARM and ARM64 copies in system_ext. | Actual IMS registration and voice/video calls; no VoLTE certification claim. |
| Audio/video performance-client selection absent | Set `ro.vendor.extension_library=libqti-perfd-client.so`, already installed for both ABIs. The Qualcomm audio HAL and video decoder read this property. | Verify client loading and successful performance locks; do not assume every DSP/codec message is fixed. |
| Dolby optional parameter property denied | Give the exact `dolby.dap.param.tee` name a system/vendor-config label and audio/Dolby HAL readers. | Speaker, headset, earpiece and Dolby effect operation. |
| Optional FPC extension lookups use default hwservice label | Give navigation/test extension names a dedicated protected type; restrict registration to the fingerprint HAL and lookup to system_server. No absent implementation is advertised. | Ordinary enrollment/authentication; optional extension behavior. |
| QTI sensor bootstrap attempts an absent SSC binary | Preserve sensors.qti and calibration handling; start sscrpcd only if installed. | Rotation/proximity/accelerometer tests. |
| Standalone qmuxd is absent in the QCRIL package | Gate its startup by executable presence, preserving radio and DSDS selection. | SIM, calls and mobile data on both slots. |
| Duplicate modern and stock service definitions | Remove the old embedded cnd, dpmQmiMgr, ipacm and duplicate time_daemon entries so installed service RCs own their definitions. Remove stock bugreport in favor of Lineage's platform service. | Service state and functional radio/network regression tests. |
| Missing optional/factory executables | Remove their stale service declarations and start/stop hooks. Preserve QSEE, thermal-engine, IMS daemons, RMT storage, WLAN and fingerprint selection. | No mandatory hardware service may be lost; source tests check the critical names. |
| Legacy crash counter cannot transition domains | Remove this unused factory counter service. Android crash handling, bootstat and kernel pstore remain; no extra persistent crash-counter writes are introduced. | Crash capture and reboot investigation remain available. |
| ppd_sun lacks an execution label | Use the already established Qualcomm display post-processing domain for this existing stock executable. | Display/color/sunlight behavior and suspend/power testing. |
| Rejected platform-property triggers in vendor init | Move the remaining live actions to system_ext init. Remove obsolete dhcpcd, crypto-module, absent-service and duplicate TCP-tuning hooks. | No rejected triggers; charging-disable and shutdown behavior where used. |
| Vendor property-loader denials | Retain the existing QTI FM type and add its vendor_init setter; define exact DPM labels/setters; move backup NTP to system. Label the three SDK33 recovery USB IDs with the existing exported recovery_config_prop type and its permitted vendor_init setter. | Property load and recovery USB/ADB. The recovery-mode bootloader request itself needs a separate device test. |
| Runtime writes to a read-only root | Build firmware, Bluetooth-firmware, DSP and vendor-tombstone aliases into the root image; precreate persist. Use vendor-owned tombstone directories, remove obsolete platform-data-directory creation and mismatched modular-driver loads. | Firmware/calibration visibility and crash storage. |
| Obsolete system fstab verify flag | Remove the rejected legacy `verify` option to match the existing non-AVB/non-verity layout. Firmware, partitions and keys are not modified by the helper. | Mounts and clean reboot. |

The complete task-profile database derives from AOSP/Lineage SDK33
`system/core/libprocessgroup/profiles/task_profiles.json` (Apache-2.0), with
unsupported actions removed and the existing GM8 HMP overrides retained.
The loader switch is a dedicated public immutable vendor capability because
libprocessgroup is used in platform, vendor and app processes. Read access is
limited to this one capability property; no property-writing access is granted
to apps and no BPF readiness property is changed.

## Messages that are not proven functional defects

The three SetupWizard ANRs occur while Wi-Fi is blocked and initial GApps work
is busy. Their main-thread ANR trace is not included, so this batch does not
claim a separate proven SetupWizard root cause. Retest after the service fix.

The kernel/SDK mismatch also produces optional binderfs, synthetic tracing,
metadata/DSU, incfs and absent-statistics probes. Legacy binder nodes and the
existing userdata implementation remain in use. Do not create fake mountpoints,
fake support flags or blanket permissions to make these messages disappear.
First-run missing history/entropy/recovery files, offline Google requests and
flattened-APEX backing-file warnings must be reassessed after setup/networking.

ION heap-query and DSP callback/visualizer warnings need an actual failing
playback/capture path before changing kernel or firmware ABI. Register dumps
logged at error priority are not automatically I2C transfer failures. These
items remain explicitly unverified rather than being called fixed by hiding logs.

## Validation and use

The SDK33 stack installer prepares every source patch in isolation, including
the two narrowly scoped vendor shell patches. Other vendor edits (for example
protobuf ABI fixups) are retained. Re-running the installer is idempotent;
conflicts stop before source mutation. No vendor reset or new vendor checkout
is required.

Host validation covers the actual cgroup/profile selection methods under legacy,
default and missing-file cases, the real GPU initialization/destructor branches,
the sensor shell's installed/absent SSC cases, complete task-profile references,
critical init service preservation, transactional patch application, signing,
trust stores and packaged Wi-Fi/IMS/kernel-policy checks. The Android build must
still pass Soong, SELinux/neverallow, ABI and target-files/image checks.

The first batch compiled on the owner's build host but target-files image
generation stopped because the new root `/bt_firmware` symlink lacked a
file-context label. The generic disk/inode suggestion was not the cause: the
reported tree was about 2257 MiB within a 3072 MiB image budget. All four root
symlinks now have explicit inode-specific labels using the established Qualcomm
target types, and the precreated `/persist` directory uses `mnt_vendor_file`.
A real libselinux regression enumerates the BoardConfig aliases and resolves
every symlink/directory label, also rejecting unintended regular-file matches.
It does not substitute for running e2fsdroid and the Android policy checks.

Run `tools/build-runtime-20.0.sh`, then `tools/make-firstboot-20.0.sh` against the
new target-files archive. The latter rejects stale/incomplete packaged policy
before signing. Changes affect system, system_ext, vendor and root-image
content, so updating only boot.img is insufficient. Continue with the same
persistent keys; no userdata format is required solely for this batch.

After exercising Wi-Fi, setup, audio, camera and fingerprint, the Windows helper
`tools/collect-runtime-20.0.cmd` collects service/controller state and ANR traces
alongside one logcat snapshot into a new ZIP. It can use the userdebug adbd root
capability; denied commands are captured as evidence. Keep these device reports
private rather than committing raw logs to GitHub.
