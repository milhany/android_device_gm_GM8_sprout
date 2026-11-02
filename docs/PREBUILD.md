# GM8 / LineageOS 17.1 prebuild and update

This branch builds Android 10 / SDK 29 for GM8_sprout and GM8_d_sprout.
Use the Ubuntu 22.04 gm8-build container as builder and the separate
/home/builder/android/lineage-17.1 checkout. See AUDIT-17.1.md for reviewed
settings, evidence, limitations and the current test results.

## Paired sources

Use configs/gm8-17.1.xml. docs/local_manifest.xml is the same Q example.
Install only one GM8 local manifest; replace the existing corresponding
entries instead of adding duplicate projects. Do not combine 18.1/19.1 source
or output directories with this checkout. The example pins the vendor and
kernel while following the device lineage-17.1 branch.

- Vendor: a22c80f76f1bc90d07d627bd43af8e959e3b22bc.
- Kernel: 79997531c5a3b9cf52d608c09e1c584e379f1ff9 (3.18.124).
- Policy: LineageOS/android_device_qcom_sepolicy, lineage-17.1-legacy-um,
  installed at device/qcom/sepolicy-legacy-um; its entry is sepolicy.mk.
- Q extraction helper: vendor/lineage/build/tools/extract_utils.sh.
- VNDK snapshots 27/28 remain required for the paired legacy blobs.
- Stock launch metadata is API 26; current Android SDK is 29. These differ
  intentionally and do not change the actual security patch level.

Initial source bring-up is vanilla. setup-gapps.sh intentionally refuses the
Android 11 rho installer. Existing Google apps require an independently
verified Android 10 ARM64 package; do not import a newer vendor/gapps tree.

## Tool interpreters

The kernel GCC wrapper needs Python 2.7. build-17.1.sh selects the runnable
synced launcher without changing system Python. Release signing requires the
complete system Python 2.7 standard library including zlib; release-17.1.py
probes it before the build. Python 3 runs GM8 checks and signing orchestration.
Kernel module signing uses system Perl with PERL5LIB cleared and probes
FileHandle, IPC::Open2 and Getopt::Std. Install missing packages as container
root from the host; builder has no sudo.

## Build

Run inside gm8-build in the 17.1 checkout:

```bash
bash device/gm/GM8_sprout/tools/build-17.1.sh check
GM8_INSTALL_MODE=update bash device/gm/GM8_sprout/tools/build-release-17.1.sh
```

The first command checks source and compiles policy/host search tools.
The second performs the normal build and signs with existing keys. Do not
resume an old signing plan to include new source changes.

The normal workflow:

1. Probe interpreters, apply the bounded libperfmgr errno-log patch and
   validate Q source/blob inputs. Preserve that system/extras edit across syncs.
2. Run m nothing, neverallows, recovery policy and file-label tests.
3. Check compiled Dolby app API/audio/DMS permissions. Direct window_service
   find is forbidden for this non-core app domain; Q supplies its Binder cache.
4. After policy checks pass, clear only obj/KERNEL_OBJ, product kernel and
   boot.img, then rebuild kernel/modules and inspect the resolved config.
5. Build target-files/otatools. Check native Wi-Fi/perf registration and
   dependencies, installed ART/task profiles and packaged kernel IKCONFIG.
6. Sign and verify APK/OTA identities, declared recovery extras and output
   metadata. Publish latest only after success; preserve the old latest on failure.

Private keys remain in ~/android/gm8-signing/keys. Back them up separately;
never commit or publish them. The signed userdebug ZIP is:

```text
~/android/gm8-17.1-release/latest/gm8-17.1-userdebug-release.zip
```

Update mode is for an already installed 17.1 ROM using these same keys.
It requests no Format Data. A move from another Android version or signing
identity needs a separate backed-up installation/key-migration plan.

## Filesystem and hardware validation

/data currently requires F2FS. The fstab does not convert ext4 automatically;
encryptable=footer permits unencrypted data and does not force encryption.
Keep the complete A/B layout and calibration/modem/persist partitions.

The paired stock thermal HALs and kernel thermal controls remain in use.
thermal-engine.conf has no mitigation policy; this warning remains open until
hardware protection, reported units, temperatures and charging behavior are
verified. Do not disable thermal/BCL protection to obtain benchmark scores.

After a successful build, test boot/unlock, Wi-Fi association/reconnect and
hotspot, SIM calls/data, fingerprint enrollment/unlock, camera/video and media,
Dolby speaker/headphone/receiver/call transitions, charging and screen-off
deep sleep. Retain single-SIM default and explicit DSDS switching.

Use tools/collect-runtime-17.1.sh and a fresh logcat for failures. Compare a
fixed cold/warm launch and app-switch workload; free RAM alone is not a
performance measure. Source/host checks are not hardware acceptance.

## Focused host tests

```bash
python3 device/gm/GM8_sprout/tools/tests/device_config_17_1_test.py
python3 device/gm/GM8_sprout/tools/tests/power_runtime_17_1_test.py
```

The power test compiles actual C++ bodies with Android boundary stubs using
g++/UBSan. It does not replace the Android build or on-device measurements.
