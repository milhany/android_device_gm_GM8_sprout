# GM8 Android 11 rework: build and device validation

Use `lineage-18.1-rework` for all three GM8 repositories. The product is
`gm_GM8_sprout`; it uses the LineageOS 18.1 source base with a GM/AOSP-facing
application profile. This tree is not an OEM-certified Android 11 release.

## Source setup

Start from a complete LineageOS 18.1 checkout, including its Qualcomm projects,
Lineage SDK, extract-utils and VNDK 27/28/29 snapshots. Add the projects in
`docs/local_manifest.xml` to your local manifest, avoiding duplicate project
paths if they are already present:

| Repository | Checkout path |
| --- | --- |
| `milhany/android_device_gm_GM8_sprout` | `device/gm/GM8_sprout` |
| `milhany/proprietary_vendor_gm_GM8_sprout` | `vendor/gm/GM8_sprout` |
| `milhany/android_kernel_gm_msm8937` | `kernel/gm/msm8937` |

`BoardConfig.mk` imports `device/lineage/sepolicy/common/sepolicy.mk` and
`device/qcom/sepolicy-legacy-um/SEPolicy.mk`. The latter comes from
`LineageOS/android_device_qcom_sepolicy`, branch `lineage-18.1-legacy-um`.
The kernel expects the aarch64 Android GCC 4.9 prebuilt path in BoardConfig.

The product requires Android 11 ARM64 GApps before lunch. For the first checkout:

```sh
bash device/gm/GM8_sprout/setup-gapps.sh
git -C vendor/gapps rev-parse HEAD
```

Record that full SHA. For a reproducible subsequent checkout, pass the recorded
40-character MindTheGapps commit as the sole argument to `setup-gapps.sh`.
The helper refuses dirty or unexpected checkouts and never resets local work.
Without a SHA it follows `rho` using fast-forward updates; a detached checkout
requires an explicit SHA. Review local commits if your `rho` is ahead of upstream.

Before each build, save `repo manifest -r -o <build-record.xml>` outside the
source repositories. Record the GApps SHA separately if the helper cloned it
outside `repo`, along with any local changes and the signing-key identifiers.
Do not include private signing material in Git or in the build record.

## Build gates

Run from the Android source root:

```sh
python3 device/gm/GM8_sprout/tools/preflight.py
source build/envsetup.sh
lunch gm_GM8_sprout-userdebug
m nothing
m bootimage
m target-files-package otatools
```

Preflight checks files and syntax, not every Make conditional, Soong module,
binary dependency or ABI. `m nothing` validates the selected build graph; the
full target-files build is required to verify compilation, linking and images.

- [ ] All source and GApps revisions recorded; no unexplained local changes.
- [ ] Correct GCC prebuilt is present and runnable on the build host.
- [ ] `hardware/qcom-caf/common/fwk-detect/Android.bp` is present from
      `LineageOS/android_hardware_qcom-caf_common`, branch `lineage-18.1`.
      It provides `libqti_vndfwk_detect` with a vendor variant and both ARM and
      ARM64 builds. Use that source provider instead of defining duplicate
      modules for the unused blobs in the GM8 vendor directory.
- [ ] The VNDK v28 snapshot provides the requested protobuf `vendorcompat`
      libraries. Check both ARM and ARM64 install paths needed by the old blobs.
- [ ] No missing HAL/service modules, ELF dependencies, VINTF incompatibilities,
      or SELinux neverallow failures. Do not suppress these build gates.
- [ ] Final boot/system/vendor image sizes fit BoardConfig partition limits.
      GApps and filesystem overhead must be included; blob file sizes alone
      are not sufficient. Validate A/B slot switching, recovery and OTA.
- [ ] Inspect the generated target-files properties. `device.mk` inherits the
      API 27 launch product while `vendor.prop` currently declares first API 26.
      Resolve this against the original GM8 launch firmware before release,
      then keep one authoritative launch API definition. Do not change it just
      to influence an Integrity result.

Do not regenerate the vendor makefiles blindly with `setup-makefiles.sh`: the
rework vendor tree has manual module and compatibility adjustments. Review the
generated diff and retain those adjustments when re-extracting stock blobs.

## Data, charging and SIM release gates

- [ ] `/data` is currently F2FS-only in the shared Android/recovery fstab.
      Identify the existing filesystem and encryption state first. An ext4
      installation is not converted by this fstab; formatting erases its data.
      Test clean install, encrypted boot, recovery decryption and OTA migration
      on backed-up hardware before choosing a migration procedure.
- [ ] `encryptable=footer` permits unencrypted data. Switching to forced
      encryption requires a tested filesystem/recovery migration plan; it is
      not an Integrity property tweak.
- [ ] The charger mutex fix releases the profile lock when the BMS voltage
      read fails. Recheck unplug/replug and suspend/resume around low battery.
- [ ] Charger DTS limits are still TA input 2000 mA / charge 1980 mA. The vendor
      `thermal-engine.conf` has no explicit policy. Verify actual thermal-engine
      behavior, JEITA, hot/cold stops, every mitigation level and USB SDP/CDP/DCP
      current limits using the original adapter and representative USB hosts.
      Do not raise these limits further without measurements. The final thermal
      mitigation level must stop charging. Factory BatteryTestStatus must remain
      zero during normal operation; it bypasses the thermal level setter.
- [ ] Test both GM8 single-SIM and GM8_d dual-SIM hardware. Check detected
      `vendor.gm8.multisim.config`, persisted `persist.radio.multisim.config`,
      modem startup, calls/SMS/data and IMS on each supported SIM.
- [ ] The framework's configured physical slot count is 1, but Android 11's
      UiccController raises it to at least the active phone count. Therefore this
      overlay alone does not establish a SIM2 failure. Confirm early detection
      and real HAL registrations before changing slot/IMS declarations.
- [ ] The two `vendor.gm8` variant properties use `vendor_radio_prop`, which the
      matching Qualcomm init policy permits. Check enforcing-mode AVCs and
      access to the firmware/persist identity sources on actual hardware.

## Stock appearance and functional checks

The framework overlay now selects round icon assets and a circular adaptive
icon mask. Verify after first boot and after an OTA: a previously selected
launcher/theme overlay may override the default. Check the effective mask
before clearing launcher data, which would erase the home-screen layout.

The stock wallpaper asset is not supplied in these sources. Add an authorized
stock image as `wallpaper/default_wallpaper.jpg` when available; the build also
accepts the historical root-level filenames. The wallpaper property is emitted
only when an asset is actually copied, otherwise Android uses its fallback.

The stock GeneralMobile ringtone and boot animation are already supplied.
Several applications remain AOSP/Lineage implementations; changing their names
does not make them the OEM applications. Preserve the Lineage SDK and settings
runtime required by this source base when removing visible branding.

- [ ] Circular launcher icons, wallpaper, ringtone and setup flow.
- [ ] Screen brightness, rotation, sleep/wake, both supported touch controllers
      and repeated double-tap-to-wake toggles without HAL failures.
- [ ] Front/rear camera, video audio, fingerprint, sensors, Wi-Fi, Bluetooth,
      GNSS cold/warm starts, cellular data and VoLTE where provisioned.
- [ ] Charging at rest/load, deep sleep, battery saver and thermal behavior.
- [ ] Charging LED with the screen off, at low/medium/full charge and after
      unplugging. The Lineage SDK overlay advertises RGB notification and
      battery support (67); timed pulsing is not implemented by this light HAL.
      An active notification/attention request takes priority over the battery
      state. Dismissing it must restore the charging color, and subsequent
      battery updates must not erase an active notification.
- [ ] USB charging, file transfer and user-enabled ADB. On a clean `user` build,
      the vendor script defaults to `none` instead of a diagnostic/ADB
      composition. An existing explicit persistent USB selection is preserved.

## Release signing and Play Integrity

After debugging, build the actual `gm_GM8_sprout-user` target and sign its
target-files/OTA with your own protected release keys using the Android 11
release tools. Keep platform/shared/media/networkstack/APK and OTA key mappings
consistent, and preserve the signing requirements of PRESIGNED GApps. Plan key
rotation and upgrades from earlier test-key installations before distribution.
Changing `ro.build.tags` to `release-keys` does not sign an image. A stock public
certificate does not provide the OEM private key.

Test a clean release environment with enforcing SELinux, working GMS and the
stock-compatible Keymaster/QSEE stack. The active Keymaster HAL is 3.0; the
presence of unused 4.0 blobs is not a reason to enable a second service. Retain
the genuine boot state exposed by the bootloader and `/proc/cmdline`.

Collect a concise read-only report from a connected, authorized device:

```sh
bash device/gm/GM8_sprout/tools/collect-device-state.sh > gm8-device-state.txt
```

Run the Integrity checker separately and save its raw verdict or API error,
checker name/version, test time and whether BASIC was requested. For diagnosis,
inspect Keymaster/QSEE/GMS and SELinux logs locally; redact personal data before
sharing logs. Keep the attestation certificate-chain error distinct from a
Play Integrity API failure.

`MEETS_BASIC_INTEGRITY` is an optional verdict and can allow an unlocked
bootloader. Source changes and release signing do not guarantee Google's
server-side verdict. Do not relock this custom ROM without a verified supported
boot/signing chain. If the original attestation provisioning is damaged, these
tree fixes do not recreate its hardware-backed identity.

References:

- [Android release signing](https://source.android.com/docs/core/ota/sign_builds)
- [Play Integrity verdict meanings](https://developer.android.com/google/play/integrity/verdicts)
- [Android 11 UiccController](https://github.com/LineageOS/android_frameworks_opt_telephony/blob/lineage-18.1/src/java/com/android/internal/telephony/uicc/UiccController.java)
- [Qualcomm framework detection library](https://github.com/LineageOS/android_hardware_qcom-caf_common/blob/lineage-18.1/fwk-detect/Android.bp)
