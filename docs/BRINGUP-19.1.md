# 2026-10-19 migration record

The previous 19.1 preparation was device 6ba5ad91, vendor eef8c5fa, kernel
01f9f399. This update merges working 18.1 rework device 0142797d and vendor
9eec7f5f while retaining Android 12.1-specific configuration. Power/sensors
come from reviewed device change 800e937; CPU HEVC exclusion from 51a99d1.
Kernel is brought forward to the same existing 1f198129 as 18.1.

## Source behavior

- Restores the full Lineage phone profile; removes SettingsBridge and old
  whole-screen Settings overlays. Product is lineage_GM8_sprout.
- Retains O launch metadata, flattened APEX, legacy encryption, kernel 3.18,
  Android 12 HAL versions, v29 protobuf copies and legacy cgroup profiles.
- Preserves manual DSDS startup/companion HALs, default ssss and persisted dsds.
- Rebases RadioConfig's opt-in legacy data switch on actual 19.1 sources.
  Uses PhoneSwitcher's ALLOW_DATA path without faking modem success.
- Rebases Wi-Fi on packages/modules/Wifi and getNetworkKey(). Preserves the
  per-network random MAC store and Soft AP fallback, with scoped KeyStore bypass.
- Restores matched stock Dolby, framework-only HwBinder callback, initialization/
  recovery, storage policy and audited inline ABuffer fix. Android 12.1 ABuffer
  retains corrected mData/mRangeOffset/mRangeLength offsets. Dynamic linking and
  physical audio must still be retested on Android 12.1.
- Repairs 13 QTI init/permission files retaining product paths after system_ext
  relocation. Moves DPM vendor properties to vendor.prop, corrects CAF bootctrl
  namespace and removes Android 11-only camera app domains.
- Retains bounded boosts, saver/screen-off handling, hotplug-safe power nodes
  and real thermal sensor reporting.
- Excludes optional CPU HEVC encoding; keeps AVC encoding/HEVC decoding.
  No fixed-FPS or automatic-AE experiment. Snapchat quality is not claimed solved.

## Validation boundary

Device/vendor checks, patch application/idempotence and host regressions do
not replace m nothing, m bootimage, a complete Android build or enforcing-mode
hardware tests. The 18.1 owner confirmed Dolby and SIM2 data there; that does
not establish 19.1 runtime success. WPA3 and the empty thermal-engine policy
remain open. The migration does not format, flash or repartition.

Host checks completed for this update:

- 26 device XML files, 2585 literal device/vendor copy inputs, matched Dolby
  hashes and relocated QTI text paths passed source-only preflight.
- Both patches applied to real upstream 19.1 files, accepted a second apply
  and passed their check mode. A divergent second Wi-Fi file left both files
  unchanged when the helper refused it.
- compat_19_1_test.py compiled/executed the actual patched methods with isolated
  MAC/property/HAL boundaries: mapping reuse/reload/repair, independent networks,
  no KeyStore calls under the opt-in, original default/Soft AP routes and the
  preferred-data capability fallback passed.
- Three stock Dolby instruction/fixup regressions passed for ARM/ARM64.
- Real power-policy, hotplug path and sensor/module regressions passed. The
  thermal module also compiled against actual 19.1 libhardware headers.
- Python/shell syntax and Git whitespace checks passed. The build helper
  rejected an invalid stage and a non-SDK-32 checkout before changing sources.

Run the method regression on a prepared checkout with:

```sh
python3 device/gm/GM8_sprout/tools/tests/compat_19_1_test.py --top .
```

## First server boot-image gate

The first server boot-image build completed successfully on 2026-10-19 with
kernel 3.18.124-perf-g74abe9876717. The earlier Clang offset-marker, DTC symbol
and segmentation-fault messages were absent from that supplied log.
Module installation still reported missing Getopt::Std in bundled Perl 5.26
and missing /sbin/depmod. The subsequent source update makes signing honor
PERL, selects clean native Perl and checks the container's perl/kmod tools.
Its actual sign-file script signed an ELF fixture and the SHA512/RSA signature
was independently verified with OpenSSL. Full ROM compilation, installation
and on-device boot remain unverified.

## Legacy FCM 2 packaging

The first OTA packaging attempt reached checkvintf, then failed because the
vendor manifest targets FCM 2 while Android 12.1 installs only FCM 3 through 6.
GM8 now installs compatibility_matrix.2.xml using the standard
vintf_compatibility_matrix module. The HAL matrix is unchanged from LineageOS
18.1 hardware/interfaces (blob d4f9809b7eb7c3c55c78587a968644d9f161cb88).
The required and optional HAL declarations are preserved; newer platform
matrices continue to provide higher-version replacements during merging.

The accompanying ARM64 kernel_config module retains the frozen O MR1 3.18
base/ARM64 requirements and minlts metadata from AOSP kernel/configs,
android-11.0.0_r46, commit e4102999005f8f3c8db1fdacfba80a2c581a72f1.
It is scoped to GM8's 3.18 kernel. This does not alter the manifest target-level,
launch API, HAL declarations or OTA VINTF enforcement. Full merged-target-files
validation and on-device testing must still pass on the build server/device.

## Primary sources reviewed

- [Manifest](https://github.com/LineageOS/android/tree/lineage-19.1)
- [RadioConfig](https://github.com/LineageOS/android_frameworks_opt_telephony/blob/lineage-19.1/src/java/com/android/internal/telephony/RadioConfig.java)
- [WifiConfigManager](https://github.com/LineageOS/android_packages_modules_Wifi/blob/lineage-19.1/service/java/com/android/server/wifi/WifiConfigManager.java)
- [MacAddressUtil](https://github.com/LineageOS/android_packages_modules_Wifi/blob/lineage-19.1/service/java/com/android/server/wifi/MacAddressUtil.java)
- [ABuffer](https://github.com/LineageOS/android_frameworks_av/blob/lineage-19.1/media/libstagefright/foundation/include/media/stagefright/foundation/ABuffer.h)
- [Codec2 discovery](https://github.com/LineageOS/android_frameworks_av/blob/lineage-19.1/media/codec2/sfplugin/Codec2InfoBuilder.cpp)
- [Platform property policy](https://github.com/LineageOS/android_system_sepolicy/blob/lineage-19.1/private/domain.te)
- [Build imports](https://github.com/LineageOS/android_build/blob/lineage-19.1/core/config.mk)

## Recovery ADB diagnostic image

If the recovery menu cannot clear an unauthorized ADB connection, run
`tools/make-recovery-adb-debug.py` on the already-built pstore boot image.
The opt-in helper creates a separate image with ro.adb.secure=0,
ro.adb.secure.recovery=0 and service.adb.root=1 in recovery prop.default.
It requires a GM8 userdebug
image and built-in pstore, preserves the kernel/DTBs/load addresses/command
line and other CPIO metadata, and recomputes the v0 boot ID. It refuses signed
trailers or mismatched input checksums and leaves the original image intact.
GM8's normal system-as-root boot uses properties from system/vendor; the helper
does not modify those images. This image is for collecting bring-up logs only.

## Captured bpfloader boot failure

The pstore capture on 2026-10-19 confirms that /data mounted as F2FS and
init reached load_bpf_programs. bpfloader could not create tether_error_map
(ENOSYS / Function not implemented), exited with status 2 and triggered
reboot,bpfloader-failed. This is a userspace-requested reboot, not evidence
of a kernel panic or an unformatted data partition.

The paired system/bpf and system/netd patches restore the legacy qtaguid/
iptables implementation. The GM8 property, explicit system_ext SELinux label
and tethering RRO select the supported path. The build helper applies both
patches and preflight refuses a missing half or kernel accounting option.
See patches/LEGACY-NETWORK.md for exact provenance and feature limitations.

Build a new ROM (system, system_ext and product change); boot.img alone cannot
carry this fix. Keep the pstore-enabled kernel for further diagnosis. The ROM
boot image has normal recovery authentication: tools/make-recovery-adb-debug.py
can create a separate diagnostic image again after the build if necessary.
Do not format userdata or change slots to address this captured failure.

Local checks verify real upstream patch application, repeat/check modes and
refusal of a divergent second project without changing the first. The actual
patched accounting command generator is compiled on the host against the
restored upstream test expectations for both modes. Android compilation,
SELinux policy validation and on-device boot/network tests remain pending.

On a prepared source tree, repeat the host regressions with:

```sh
python3 device/gm/GM8_sprout/tools/tests/legacy_network_19_1_test.py --top .
```
