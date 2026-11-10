# GM8 LineageOS 20 / Android 13 source bring-up

Stage: source checkout, build-graph investigation and unsigned target-files
compilation. No bootable Android 13 ROM, signed OTA or phone validation is
claimed. Do not install bring-up images while runtime ports remain open.

## Bases and inherited work

Device starts from the 19.1 stability candidate
`0a6f97d54de225e0a8acc2e33f9982f2d03bf5c8`; kernel starts from
`4d2e5c2a07135d61ffd64c086b987d4a9fd78a43`; vendor starts from
`0c168fb7a09a150a35e99383bb47b81bc060d4c7`. The 3.18 kernel, QSEE final-close,
FT8006 wake ownership, GNSS init mapping and prior device fixes are inherited.
This is not a 4.19 kernel migration and does not establish that the vendor
blobs work on Android 13.

Official Lineage manifest reviewed: `lineage-20.0`, commit
`0d12a657c699970c9f0a82361eb170aa9ccaeb59`, platform Android 13 / SDK33.
It provides the legacy msm8996 CAF projects, Qualcomm legacy-um policy,
VNDK v29 snapshots and GCC 4.9 kernel toolchains needed for the initial
source investigation. The project still requires platform compatibility
work for the 3.18 kernel.

## Initial checkout

Use the existing Ubuntu 22.04 gm8-build container as builder. The bootstrap
creates a separate `$HOME/android/lineage-20.0` checkout and retains old ROM
trees. Supply the reviewed docs/local_manifest.xml extracted from the same
Git commit as the bootstrap helper. The local manifest selects all three
GM8 lineage-20.0 branches and MindTheGapps `tau` for Android 13. Do not copy
the Android 12.1 `sigma` checkout into vendor/gapps. Repo manages that GApps
project; update it with repo sync rather than the origin-based clone helper.

```sh
bash bootstrap-20.0.sh reviewed-local-manifest.xml
```

Bootstrap checks the manifest/remotes, rejects nonempty unrelated or older
platform destinations, checks working space, initializes official Lineage
20, and syncs at j8 without force-sync or forced checkout. It probes repo
init options before enabling native Git LFS support. With older repo
versions such as 2.17, init omits the unsupported --git-lfs option. In both
native and legacy modes, projects containing LFS files run a local LFS
install, pull from their manifest remote, and fsck after sync. Native LFS
capability alone does not materialize pointers left in an earlier checkout.
A failed transfer stops before the audit. LFS
include/exclude filters are cleared for that pull so required blobs are
not silently omitted. No system-wide repo or Git configuration is replaced.
The initial working-space guard is a conservative 400 GiB source/build
budget; resume uses 150 GiB. It is not a measurement of this specific GM8
build. GM8_ANDROID_PARENT selects another build parent and
GM8_MIN_FREE_GIB can set a deliberate working-space budget, at least 50.
Nothing is automatically deleted to make space.

On a failed/limited fetch, fix the reported dependency or server rate limit
and repeat the same bootstrap. It refuses to overwrite a different gm8.xml.
An init rejected before manifest creation may leave only .repo/repo; that
narrow interrupted-init state is accepted without deleting metadata. Other
unrecognized nonempty destinations still require review.

The current official manifest uses a separate project at
external/chromium-webview/prebuilt/arm64 (the parent chromium-webview
directory is not the WebView APK repository). To repair only this input
after a completed sync, use:

```sh
git -C external/chromium-webview/prebuilt/arm64 lfs install --local
git -C external/chromium-webview/prebuilt/arm64 lfs pull -I "" -X "" github
git -C external/chromium-webview/prebuilt/arm64 lfs fsck
bash device/gm/GM8_sprout/tools/build-20.0.sh configure
```

Preflight distinguishes an unresolved LFS pointer from a non-ZIP APK. It
does not bypass the APK check when a download or checkout is incomplete.

## Available checkpoints

```sh
bash device/gm/GM8_sprout/tools/build-20.0.sh audit
bash device/gm/GM8_sprout/tools/build-20.0.sh configure
bash device/gm/GM8_sprout/tools/build-20.0.sh compile
```

Audit records a pinned repo manifest, source revisions and readiness JSON;
checks expected SDK33 paths, snapshots, source XML/JSON and WebView ZIP/LFS
materialization; tests old patch context with git apply --check only; and
runs the portable QSEE, gesture and PowerHAL host regressions. Audit success
means the source inventory completed, not that runtime compatibility passed.
The JSON explicitly keeps boot/OTA readiness false while ports remain open.

Configure additionally prepares the reviewed isolated VNDK v29 protobuf
libraries, invokes envsetup/lunch and runs only `m nothing`. It is a build
graph checkpoint, not full compilation, signing or image production. The
SDK33 gate for the ELF helper and its real-ELF regression fixture are
adapted; full stock-blob/VNDK validation still runs on the synced source
host. Do not apply the old SDK32 framework scripts on SDK33. None of these stages
runs them, modifies signing keys or accesses a phone.

After configure passes on the build host, compile repeats the source/host
checks and protobuf preparation, selects the same userdebug target, then
runs m target-files-package -j32. It does not repeat m nothing separately.
The purpose is to expose real kernel, native, Java and packaging failures
that build-graph generation cannot detect. The pipeline uses
pipefail: a failed ninja/m invocation stops the helper, with output retained
in the timestamped compile.log beside the source manifest and audit.

The target-files archive normally appears under
out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates. It can
contain boot/vendor/system images; it is not an installation/update ZIP.
A successful compile does not clear runtime blockers or make the artifacts
ready for flashing. No keys are generated, no release signing/OTA is run
and no device is accessed. The 19.1 release helper is not an Android 13
signing tool. SDK33 network, radio, cgroups and userdata policy still need
their separate ports and acceptance before image installation.

## HIDL compatibility libraries

LineageOS 20 already provides android.hidl.base@1.0 and
android.hidl.manager@1.0 through hardware/lineage/compat, including vendor
variants backed by libhidlbase. The inherited device-local
libhidl/Android.mk aliases are removed on this branch to avoid duplicate
module definitions. Product package requests remain so legacy userspace
still receives the compatibility libraries from the platform provider.
This resolves duplicate ownership at build-graph generation; vendor ABI
and hardware operation still require the later build/runtime checks.

## SDK33 product package alignment

The first Android 13 build-graph pass exposed inherited requests that are
not provided under those names. Missing-module checks remain enabled;
none of these entries is hidden with a build-broken allowlist.

| Inherited request | SDK33 selection and source evidence |
| --- | --- |
| Snap | Aperture, provided by packages/apps/Aperture/app/Android.bp. Camera hardware acceptance is pending. |
| android.hardware.gnss@1.2.vendor; android.hardware.gnss@3.0.vendor | Remove nonexistent standard HIDL versions. hardware/interfaces/gnss provides 1.0, 1.1, 2.0 and 2.1; Qualcomm vendor.qti.gnss versions are separate. Keep the existing GNSS 2.1 request and vendor stack. |
| android.hardware.graphics.composer@2.1-impl | The 2.1 service in hardware/interfaces loads HwcLoader directly. Keep that service and the CAF HWC2 module. |
| android.hardware.soundtrigger@2.2-service | The common android.hardware.audio.service tries SoundTrigger 2.3/2.2/2.1/2.0 in order. Keep the 2.2 implementation and common audio service. |
| audiod | Enable AUDIO_FEATURE_ENABLED_SND_MONITOR in the selected CAF HAL and remove the obsolete separate init service. The HAL monitors the same /proc/asound card/CPE state and notifies its stream listeners. Existing audio policy grants proc_asound/proc_audiod access; runtime DSP restart behavior is still untested. |
| libqdMetaData.vendor | Use libqdMetaData; the selected CAF display Android.bp declares it vendor: true. |
| liboverlay | The selected SDM HWC2 uses libqdutils/libqdMetaData, not the removed HWC1 overlay module. |
| libOmxSwVencHevc | Not provided by the selected msm8937 media build. The device codec XML advertises AVC encoding and HEVC decoding; retain both. No HEVC encoder is advertised by this change. |
| dhcpcd.conf; libQWiFiSoftApCfg | Remove legacy package requests absent from SDK33. Keep the NetworkStack/Wi-Fi, hostapd and supplicant stack. Reconciliation of inherited legacy DHCP init declarations remains part of the network port. |
| rcs_service_aidl; rcs_service_aidl.xml; rcs_service_api; rcs_service_api.xml | These are old Suntek client API jars, not the Qualcomm IMS service. Remove the obsolete requests; the vendor Qualcomm IMS/RCS files are unchanged. RCS, VoLTE and VoWiFi registration still require testing. |
| vendor.qti.hardware.cryptfshw@1.0-service-qti.qsee | The selected SDK33 interface manifest/source no longer provides this FDE service. Remove its request, obsolete TARGET_LEGACY_HW_DISK_ENCRYPTION flag and unsatisfied VINTF declaration. Do not claim userdata encryption support as a result. |

Android 13 removed full-disk encryption. The selected vold cryptfs.cpp now
implements deprecated external/adoptable-volume metadata handling, not the
old userdata FDE service. The inherited encryptable=footer fstab is left
unchanged in this build-graph change; its SDK33 parsing, the supported FBE
policy and any migration procedure remain explicit runtime blockers.
This source update performs no formatting, key deletion or data migration.

Reviewed upstream sources:

- https://github.com/LineageOS/android_hardware_interfaces/blob/lineage-20.0/graphics/composer/2.1/default/service.cpp
- https://github.com/LineageOS/android_hardware_interfaces/blob/lineage-20.0/audio/common/all-versions/default/service/service.cpp
- https://github.com/LineageOS/android_hardware_qcom_audio/blob/lineage-20.0-caf-msm8996/hal/audio_extn/sndmonitor.c
- https://github.com/LineageOS/android_hardware_qcom_display/blob/lineage-20.0-caf-msm8996/libqdutils/Android.bp
- https://github.com/LineageOS/android_system_vold/blob/lineage-20.0/cryptfs.cpp
- https://source.android.com/docs/security/features/encryption/full-disk

## Bluetooth audio APEX boundary

The SDK33 audio.a2dp.default module declares only com.android.bluetooth
in apex_available, so it cannot be directly requested as a platform
PRODUCT_PACKAGES entry (including its automatically selected 32-bit
variant). Remove that request rather than extending the platform's APEX
availability.

Keep audio.bluetooth.default, android.hardware.bluetooth.audio@2.0-impl,
the common audio service and bluetooth_audio_policy_configuration.xml.
The selected audio.bluetooth.default is a vendor/proprietary HAL with
HIDL session support; the common audio service registers the Bluetooth
Audio 2.0 provider. The policy defines A2DP headphone/speaker output routes.

Remove the separate legacy a2dp_in include/copy as well: it advertises an
A2DP sink/receive module backed by the removed legacy platform HAL. This
change does not provide that optional sink role through another backend.
Primary audio, SCO call routes and Bluetooth playback policy are retained.
Bluetooth playback, microphone/call behavior and reconnect remain pending
hardware acceptance.

Reviewed sources:

- https://github.com/LineageOS/android_packages_modules_Bluetooth/blob/lineage-20.0/system/audio_a2dp_hw/Android.bp
- https://github.com/LineageOS/android_packages_modules_Bluetooth/blob/lineage-20.0/system/audio_bluetooth_hw/Android.bp
- https://github.com/LineageOS/android_hardware_interfaces/blob/lineage-20.0/audio/common/all-versions/default/service/service.cpp
- https://github.com/LineageOS/android_frameworks_av/blob/lineage-20.0/services/audiopolicy/config/bluetooth_audio_policy_configuration.xml

## Legacy kernel host linker flags

The SDK33 build invokes the prebuilt host Clang with HOSTLDFLAGS including
-fuse-ld=lld. The 3.18 single-C host rule (used by scripts/basic/fixdep)
previously omitted HOSTLDFLAGS, although the multi-object C and C++ host
link rules already honored it. That lost the selected linker and produced
the reported missing ld failure under the restricted build PATH.

The lineage-20.0 kernel branch now passes HOSTLDFLAGS to the single-C link.
The kernel's ARM64 GCC 4.9 configuration and runtime source are unchanged.
Select the updated kernel branch as well as the device branch before
retrying compile. The build helper runs kernel_host_link_test.py against
that kernel source before compilation.

The host regression executes the actual Makefile.host rules and real
fixdep.c with native C/C++ tools. An isolated library search path reproduces
the old flag-loss failure; the patched rule and existing multi-object links
produce working ELF host executables with the expected linker-defined
symbol. This tests linker-flag propagation with the available native GCC,
not the Android Clang 14 distribution or a complete kernel compilation.
The latter must be validated on the build host.

## Known SDK33 ports

1. Legacy network/accounting: Android 13 moved key BPF paths into
   packages/modules/Connectivity. `system/netd/server/TrafficController.cpp`
   from the old patch is absent. Current paths include netd/BpfHandler.cpp,
   service/native/TrafficController.cpp and service/src/com/android/server/
   BpfNetMaps.java in Connectivity. Silencing the loader does not implement
   data accounting, UID firewall, DNS policy or tethering compatibility.
2. RadioConfig must be reviewed with the Android 13 radio AIDL/HIDL changes
   and telephony/data/PhoneSwitcher.java. Retain real modem errors and the
   explicit single/dual-SIM policy; do not fake preferred-data success.
3. Revisit Wi-Fi MAC/KeyStore behavior after the QSEE candidate; do not copy
   the Android 12 patch by changing a version check.
4. Review processgroup, cgroup-v1 task profiles and LMKD behavior against
   the actual 3.18 interfaces.
5. Review SystemUI, recents and optional charging-HAL fixes in the new
   framework sources before applying old lifecycle patches.
6. Resolve Soong/package/API, SELinux/VINTF and vendor ABI differences;
   validate Android 13 GApps and release signing; only then test boot and
   peripherals.

The power/thermal limits are retained. Android 13 is not assumed to improve
battery use or performance automatically. Those claims require comparable
device measurements after a complete working build.

## Validation boundary

Host fixtures exercise the actual read-only audit and bootstrap guards for
SDK selection, manifest remotes, older/nonempty destination preservation,
disk-space refusal, LFS pointer rejection and nonmutation of patches.
Shell/Python syntax and local-manifest XML checks passed. The user has
completed SDK33 source sync and m nothing on the build host. That is not
hardware validation. Full Android compilation and all hardware acceptance
remain pending. The compile helper is checked with local workflow fixtures
for stage selection, failed preflight/compile propagation and SDK refusal;
these fixtures do not compile Android or validate vendor runtime ABI.

References:

- https://github.com/LineageOS/android/tree/lineage-20.0
- https://github.com/LineageOS/android_build/blob/lineage-20.0/core/version_defaults.mk
- https://github.com/LineageOS/android_packages_modules_Connectivity/tree/lineage-20.0
- https://gitlab.com/MindTheGapps/vendor_gapps/-/tree/tau
- https://source.android.com/docs/setup/start/requirements
- https://gerrit.googlesource.com/git-repo/+/refs/heads/main/man/repo-init.1
