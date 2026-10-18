# GM8 Android 11 rework: build and device validation

Use device branch `lineage-18.1-wpa3-test` with vendor and kernel branches
`lineage-18.1-rework`; run the checked WPA3 helper before building. The product is
`lineage_GM8_sprout`; it inherits the complete LineageOS 18.1 phone
profile (LineageParts, SetupWizard, Updater, themes and mobile applications).
This tree is not an OEM-certified Android 11 release.

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

`BoardConfig.mk` imports `device/qcom/sepolicy-legacy-um/SEPolicy.mk`, from
`LineageOS/android_device_qcom_sepolicy`, branch `lineage-18.1-legacy-um`.
For the `lineage_GM8_sprout` target, `build/core/config.mk` automatically includes
`vendor/lineage/config/BoardConfigLineage.mk` and then the Lineage common SELinux
policy. Do not include either again in the device BoardConfig: duplicate common
policy paths cause duplicate attribute declarations during checkpolicy.
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
python3 device/gm/GM8_sprout/tools/apply-radio-compat.py
python3 device/gm/GM8_sprout/tools/apply-wifi-keystore-compat.py
python3 device/gm/GM8_sprout/tools/apply-wifi-compat.py
python3 device/gm/GM8_sprout/tools/apply-camera-fps-compat.py
python3 device/gm/GM8_sprout/tools/apply-camera-auto-gain-compat.py
python3 device/gm/GM8_sprout/tools/preflight.py
source build/envsetup.sh
lunch lineage_GM8_sprout-userdebug
m nothing
m android.hardware.power@1.3-service.gm-libperfmgr thermal.gm8 -j32
m libcameraservice -j32
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
- [ ] Single-SIM (`ssss`) is the default in `vendor.prop`. An explicitly
      persisted `persist.radio.multisim.config=dsds` must survive reboot.
      No init action or vendor script overwrites the selected mode. Firmware
      identity detection and the old GM8 multisim override remain removed.
- [ ] Both radio/QTI slots are declared, and the Qualcomm main script starts
      the second RIL only when the selected mode requires it. Check `ssss`
      with only the primary RIL and `dsds` with `vendor.qcrild2` (or the legacy
      `vendor.ril-daemon2` provider). Existing tertiary startup support is retained.
- [ ] Test SIM1 calls/SMS/data in single mode. In DSDS mode test both SIMs,
      incoming/outgoing calls with earpiece and speaker in both directions,
      and switching mobile data with Wi-Fi off. Check OEM hook, QtiRadio,
      IMS and UIM registrations for both slots. DSDS selection alone does not
      fix missing IMEI2, modem provisioning, SIM2 audio or mobile-data failures.
- [ ] Apply `python3 device/gm/GM8_sprout/tools/apply-radio-compat.py` after
      framework sync. Preflight requires the GM8 legacy-data-switch hook;
      see `docs/TELEPHONY.md` for the observed error 38 and device tests.
- [ ] A future pair of TWRP builds must explicitly apply a durable mode setting
      that Android consumes. A recovery name, signing key or recovery-only
      property does not itself select the running ROM's SIM mode. Recovery
      packaging, the durable setting and its Android integration are not
      implemented in this change; do not overwrite modem NV/calibration data.

## Lineage appearance and functional checks

Use the standard Lineage boot animation, wallpaper, icon/theme defaults, sounds
and Trebuchet name. Device copies and Settings XML overrides that suppressed
LineageParts and firmware-version entries have been removed. The old AOSP battery
percentage bridge is removed so LineageParts controls its own settings directly.
Existing user-selected wallpapers, sounds and themes can remain after an OTA;
verify the new defaults on a clean install as well.

- [ ] LineageParts opens from Display, Sound, Notifications, Battery and Gestures
      as supported by the hardware. Check status bar/battery percentage, buttons,
      notification and charging LED controls, themes and About phone's Lineage
      version entries. Keep the RGB battery LED capability overlay.
- [ ] Lineage SetupWizard completes with the existing GApps integration. Updater
      is packaged, but downloadable releases require a separately configured OTA
      server. Restoring the app does not create an update feed.
- [ ] Boot animation, Trebuchet, wallpaper, ringtone, theme and accent selection.
- [ ] Screen brightness, rotation, sleep/wake, both supported touch controllers
      and repeated double-tap-to-wake toggles without HAL failures.
- [ ] Front/rear camera, video audio, fingerprint, sensors, Wi-Fi, Bluetooth,
      GNSS cold/warm starts, cellular data and VoLTE where provisioned.
- [ ] Check `vendor.gm8.fingerprint.sensor` and the `GM8Fingerprint` startup
      message. A bound FPC driver with an IRQ node selects `fpc_fps_hal`; a
      Sunwave character device selects `vendor.fps_hal` plus its extension.
      Neither or both markers leave the HALs disabled with an explicit error.
      This follows the kernel's selection; it does not validate or override the
      physical GPIO ID. Check `/proc/fp_info` and kernel probe logs if selection
      disagrees with known stock behavior.
- [ ] The device rc overrides the AOSP `vendor.fps_hal` definition so the
      generic Sunwave module cannot start unconditionally and claim the default
      fingerprint service on an FPC device. Confirm only the selected default
      HAL registers. On FPC, `/data/fpc` must be system:system 0700 with
      `fingerprint_vendor_data_file`, and the existing ueventd rules must give
      system access to the driver's IRQ, reset and wakeup nodes. Test enrollment,
      unlock and template persistence after reboot on both sensor variants.
- [ ] Sunwave's fixed `/data/vendor_de/sunwave` cache and its dump/badpoint
      directories are created as system:system 0700 and labeled
      `fingerprint_vendor_data_file`. Verify `/dev/sunwave_fp`, HAL startup,
      enrollment, unlock and persistence after reboot. Storage setup alone does
      not prove the sensor or TEE initialization succeeds.
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

## Hardware logs from Windows

`tools/collect-hardware-state.sh` runs on Android and keeps stderr in the report.
It records caller identity, installed configuration hashes, selected SIM-mode properties,
radio/audio state, Sunwave paths, CPU nodes, active GNSS requests and network
state. It does not request root or change the device configuration. Permission
errors are useful evidence; a missing stdout line alone is not proof that a
device node is absent.

From a Windows platform-tools directory, copy this script beside `adb.exe`:

```powershell
.\adb.exe push .\collect-hardware-state.sh /data/local/tmp/gm8-hardware-state.sh
.\adb.exe shell sh /data/local/tmp/gm8-hardware-state.sh > gm8-hardware-state.txt
```

Capture early HAL and radio failures immediately after a reboot: start
`adb logcat -b all -v threadtime` as soon as adb reconnects and save it on the
host while exercising the device. A later `logcat -d` can retain early system
messages while the main buffer containing HAL initialization has already wrapped.

For a SIM1 call or mobile-data reproduction, capture the radio log before the
operation and stop with Ctrl+C after the failure:

```powershell
.\adb.exe logcat -b main -b system -b radio -v threadtime > gm8-radio-live.txt
```

Run the hardware collector from another window while the call is active. Note
the audio route and whether Wi-Fi was disabled for the mobile-data test. Do not
clear the log buffers first; startup registration errors may be needed. Logs may
contain phone numbers, subscriber/network details and location; redact them
before public sharing.

Keep a GNSS test app open in the foreground with location permission during the
hardware capture, even if it never gets a fix. Verify an active GPS request,
satellite-status/CN0 reports and satellites used in a fix. A coarse position with
hundreds of kilometres of uncertainty is not a valid satellite fix, even if a
report/TTFF counter increases.
If XTRA or NTP fails, compare with the current default network and DNS state;
an app-wide DNS failure is not proof of a GNSS-specific configuration fault.
Use working SIM1 data or validated Wi-Fi to isolate this from the SIM2 data
failure, then repeat outdoors with a clear sky view. Record per-satellite C/N0,
satellites used, fix accuracy and elapsed time. A different phone's faster fix
does not distinguish GM8 antenna/RF, firmware and aiding failures by itself.
Changing NTP servers or reported accuracy thresholds does not increase receiver
sensitivity; keep RF/antenna diagnosis open if useful satellite signals remain
absent with a working network and an active GNSS request.

A boot-only log does not exercise satellite acquisition. Android trying GNSS
2.1 and then connecting to the installed 2.0 service is normal version fallback.
An old modem can reject optional clock-estimator/blacklist/constellation commands;
those messages alone do not prove that basic positioning has failed. Capture
the actual no-fix attempt: start `adb logcat -b main -b system -v threadtime`
before opening the GNSS app, leave the request active for two minutes, then run
the hardware collector while the app is still open. Record zero satellites or
zero C/N0 too; a successful fix is not a prerequisite for a useful capture.

## Release signing and Play Integrity

After debugging, build the actual `lineage_GM8_sprout-user` target and sign its
target-files/OTA with your own protected release keys using the Android 11
release tools. Keep platform/shared/media/networkstack/APK and OTA key mappings
consistent, and preserve the signing requirements of PRESIGNED GApps. Plan key
rotation and upgrades from earlier test-key installations before distribution.
Changing `ro.build.tags` to `release-keys` does not sign an image. A stock public
certificate does not provide the OEM private key.

Test a clean release environment with enforcing SELinux, working GMS and the
stock-compatible Keymaster/QSEE stack. The active Keymaster HAL is 3.0; the
presence of unused 4.0 blobs is not a reason to enable a second service.

The rework kernel restores the legacy `/proc/cmdline` filter from `e9ad82b`:
`androidboot.verifiedbootstate` is omitted from the userspace-visible copy.
The implementation bounds the copy and safely handles a final or repeated flag,
while retaining unrelated parameters and the kernel's original command line.
This does not lock the bootloader, change AVB enforcement or alter TEE-backed
attestation. Properties and `/proc/cmdline` may therefore be incomplete evidence
of the actual boot state. Record the kernel revision when comparing results;
do not infer a genuine locked bootloader from the filtered view.

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
- [Qualcomm companion HAL instances on LineageOS 18.1](https://github.com/LineageOS/android_device_xiaomi_msm8953-common/blob/lineage-18.1/manifest.xml)
- [GM8 Voice2 kernel mixer controls](https://github.com/milhany/android_kernel_gm_msm8937/blob/lineage-18.1-rework/sound/soc/msm/qdsp6v2/msm-pcm-routing-v2.c)

For the GM8 Wi-Fi KeyStore/ANR workaround, see [WIFI_KEYSTORE.md](WIFI_KEYSTORE.md).
