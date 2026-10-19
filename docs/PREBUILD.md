# GM8 LineageOS 19.1 bring-up

Use `lineage-19.1` for all three GM8 repositories and a complete LineageOS 19.1 /
Android 12.1 source tree (SDK 32). Lunch: `lineage_GM8_sprout-userdebug`.
The full Lineage phone profile, LineageParts, SetupWizard, Updater and themes are
restored. The old `gm_GM8_sprout` product and SettingsBridge are removed.
AudioFX is excluded because stock Dolby owns the global audio mix.

This prepares sources for bring-up. Android 12.1 build/boot/hardware validation
is still required. See [the migration record](BRINGUP-19.1.md).

## Separate source checkout

Run inside the existing Ubuntu 22.04 build container as builder, in tmux.
Keep the working 18.1 source/output available.

```sh
mkdir -p ~/android/lineage-19.1
cd ~/android/lineage-19.1
set -o pipefail
repo init -u https://github.com/LineageOS/android.git -b lineage-19.1 --no-clone-bundle
mkdir -p .repo/local_manifests
curl -fL https://raw.githubusercontent.com/milhany/android_device_gm_GM8_sprout/lineage-19.1/docs/local_manifest.xml -o .repo/local_manifests/gm8.xml
repo sync -c -j16 --no-clone-bundle --fail-fast 2>&1 | tee ~/android/gm8-19.1-sync.log
```

The local manifest adds only the three GM8 repos. Upstream supplies Qualcomm
CAF, sepolicy-legacy-um (lineage-19.1-legacy-um), Lineage SDK, extract-utils,
GCC 4.9 and VNDK snapshots. Do not replace a failed public project with an
arbitrary newer branch: mixed Soong/LLVM revisions caused earlier build failures.
Diagnose the specific failed repository URL.

Check disk space before sync and the full build: both the second source and
its output need space. Use the container's existing bind-mounted Android
directory, not its ephemeral writable image layer.

## Build gates and logs

The helper prepares pinned ARM64 Android 12.1 GApps, applies the Android 12.1
radio/Wi-Fi patches, runs full preflight, records revisions/local framework
patches and selects lunch. It stops at the first failure and never resets
existing changes.

```sh
cd ~/android/lineage-19.1
set -o pipefail
bash device/gm/GM8_sprout/tools/build-19.1.sh boot 2>&1 | tee ~/android/gm8-19.1-boot.log
```

This runs `m nothing`, then `m bootimage -j32`. After both pass:

```sh
bash device/gm/GM8_sprout/tools/build-19.1.sh rom 2>&1 | tee ~/android/gm8-19.1-build.log
```

`rom` runs the graph gate then `m bacon -j32`; `check` runs only the graph.
The default is `boot`. Timestamped records are in the sibling
`gm8-19.1-records` directory. GApps sigma is pinned to
`f75a18fd21f0ceaa73b3c2c01bdb257aff976f2f`; use an explicit reviewed SHA when
updating it. Do not reuse Android 11 rho GApps here.

Manual preparation after each framework sync:

```sh
bash device/gm/GM8_sprout/setup-gapps.sh f75a18fd21f0ceaa73b3c2c01bdb257aff976f2f
python3 device/gm/GM8_sprout/tools/apply-radio-compat.py
python3 device/gm/GM8_sprout/tools/apply-wifi-keystore-compat.py
python3 device/gm/GM8_sprout/tools/preflight.py
source build/envsetup.sh
lunch lineage_GM8_sprout-userdebug
m nothing
m bootimage -j32
```

Preflight checks inputs, XML/JSON, Dolby hashes, SDK, compatibility patches and
stale QTI relocation paths. It does not prove modules, ELF ABI, linking, VINTF
or SELinux correctness. `--source-only` reviews an isolated device/vendor pair
and does not satisfy the build gate. Keep neverallows/compatibility checks.

Both ARM and ARM64 v29 full/lite protobuf copies are required. The bootctrl
namespace is hardware/qcom-caf/bootctrl. The build system includes Lineage
BoardConfig/common policy itself: do not duplicate these includes. Android 12.1
platform policy covers camera-property readers; Android 11-only snap_app and
gallery_app policy is not used.

## Installation and hardware gates

- Check generated boot/system/vendor sizes against A/B partition limits,
  including GApps and filesystem overhead. Keep the partition layout.
- A boot image is not a complete Android 12.1 installation. Prepare matching
  ROM/recovery before flashing. The helper never flashes or formats.
- /data remains F2FS with encryptable=footer. Identify the current filesystem,
  encryption and recovery decryption support before an installation plan.
  Back up phone data before the major-version transition; dirty-flash support
  has not been validated.
- First boot: check setup/SystemUI, enforcing SELinux and service restart loops.
  Then test WPA2 with mobile data off, Bluetooth, calls/SMS and data.
- Single SIM defaults to ssss; persisted dsds is respected. Test both SIMs,
  voice in both directions, data switching and reboots. Automatic detection
  and a TWRP selection mechanism are not added.
- Test Dolby initialization/profiles/playback, calls, headphones and reboots.
  See [Dolby](DOLBY.md).
- Test front/rear photos/video/audio, Snapchat, GNSS and fingerprint variants.
  CPU HEVC encoding is excluded; AVC encoding and HEVC decoding remain.
  HEVC-only recording apps may need separate handling.
- Initial bring-up excludes experimental WPA3 kernel/supplicant and Snapchat
  FPS/AE request rewriting. WPA3 support is not claimed here.
- Test screen-off suspend, saver and CPU temperatures. thermal.gm8 reports
  sensors; the empty thermal-engine policy remains an open warning. Kernel/
  firmware protection, JEITA and charger limits are retained and need testing.
- Android O launch API 26 remains authoritative. A cmdline display filter does
  not lock the bootloader or guarantee an Integrity verdict.

Use tools/collect-hardware-state.sh, [telephony](TELEPHONY.md),
[Wi-Fi KeyStore](WIFI_KEYSTORE.md), [power](POWER.md) and [thermal](THERMAL.md).
Capture live logcat while reproducing a failure. Boot-only logs do not exercise
camera recording, satellite acquisition or SIM2 data switching.

Do not regenerate vendor makefiles blindly: manual module/compatibility
adjustments must survive re-extraction. Review paths and Dolby fixups.

After hardware validation, use lineage_GM8_sprout-user and Android 12.1 release
tools with protected keys. Preserve PRESIGNED GApps requirements and plan
upgrades from test-key builds. Build tags and reported boot-state filtering
do not provide release signatures, OEM provisioning or guaranteed Integrity.
