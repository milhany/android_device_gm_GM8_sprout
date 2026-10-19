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

## Primary sources reviewed

- [Manifest](https://github.com/LineageOS/android/tree/lineage-19.1)
- [RadioConfig](https://github.com/LineageOS/android_frameworks_opt_telephony/blob/lineage-19.1/src/java/com/android/internal/telephony/RadioConfig.java)
- [WifiConfigManager](https://github.com/LineageOS/android_packages_modules_Wifi/blob/lineage-19.1/service/java/com/android/server/wifi/WifiConfigManager.java)
- [MacAddressUtil](https://github.com/LineageOS/android_packages_modules_Wifi/blob/lineage-19.1/service/java/com/android/server/wifi/MacAddressUtil.java)
- [ABuffer](https://github.com/LineageOS/android_frameworks_av/blob/lineage-19.1/media/libstagefright/foundation/include/media/stagefright/foundation/ABuffer.h)
- [Codec2 discovery](https://github.com/LineageOS/android_frameworks_av/blob/lineage-19.1/media/codec2/sfplugin/Codec2InfoBuilder.cpp)
- [Platform property policy](https://github.com/LineageOS/android_system_sepolicy/blob/lineage-19.1/private/domain.te)
- [Build imports](https://github.com/LineageOS/android_build/blob/lineage-19.1/core/config.mk)
