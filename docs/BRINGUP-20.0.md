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
bash device/gm/GM8_sprout/tools/build-20.0.sh network-stats
```

Audit records a pinned repo manifest, source revisions and readiness JSON;
checks expected SDK33 paths, snapshots, source XML/JSON and WebView ZIP/LFS
materialization; tests old patch context with git apply --check only; and
runs the portable QSEE, gesture and PowerHAL host regressions. Audit success
means the source inventory completed, not that runtime compatibility passed.
The JSON explicitly keeps boot/OTA readiness false while ports remain open.

Configure applies the separately reviewed SDK33 processgroup port, runs
its native host regression, prepares the isolated VNDK v29 protobuf
libraries, invokes envsetup/lunch and runs only `m nothing`. It is a build
graph checkpoint, not full compilation, signing or image production. The
SDK33 gate for the ELF helper and its real-ELF regression fixture are
adapted; full stock-blob/VNDK validation still runs on the synced source
host. Do not apply the old SDK32 framework scripts on SDK33. None of these stages
runs them, modifies signing keys or accesses a phone. Audit stays read-only;
configure/compile/network-stats apply the separately reviewed SDK33
processgroup and TrafficStats read-side ports before recording the source
audit. The audit records each port's patch hash and staged/applied state
without treating it as hardware acceptance. No SDK32 framework helper runs.

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
signing tool. SDK33 network and radio ports, processgroup runtime acceptance and userdata
policy review remain open before image installation.

## Existing target-files inspection

The build host has completed the full SDK33 target-files compilation and
image packaging. This clears the compilation checkpoint only; the runtime
ports below remain open. Inspect the existing archive without another build:

```sh
python3 device/gm/GM8_sprout/tools/inspect-target-files-20.0.py \
  --top "$PWD" --output /path/to/new-gm8-20.0-preboot.json
```

The inspector selects a ZIP only when the product target-files directory
contains exactly one candidate; otherwise specify --target-files explicitly.
The output must be a new file. It reads selected packaged build properties,
/data fstab rows, cgroup/task-profile JSON, APEX/BPF inventories and boot
component sizes. It also records the current build-tree kernel config and
inspection-time source HEADs/tracked-dirty state. Those local files and
revisions are not proof that the ZIP was built from those exact inputs.

The ZIP is not extracted or changed. Image/APEX/APK payloads are not
validated by this inspection. No source patches, rebuild, signing, key
generation, phone access, encryption change or data formatting occurs.
Readiness stays false even when the inspection succeeds. The JSON is
intended for reviewing the actual packaged configuration before implementing
and testing the remaining runtime ports.

A concrete userdata issue is now confirmed in the selected SDK33 parser:
fs_mgr/fs_mgr_fstab.cpp rejects encryptable= on non-voldmanaged entries
outside recovery, and rejects forceencrypt=/forcefdeorfbe=. Therefore an
inherited /data encryptable=footer entry cannot simply be assumed to work.
This inspection reports its presence; it does not silently remove encryption
flags or establish a supported FBE policy.

Reviewed parser:
https://github.com/LineageOS/android_system_core/blob/c0500ffe2cc283d61f1e3db1b2c979bfbd9beb8c/fs_mgr/fs_mgr_fstab.cpp

The inspector regression uses synthetic archives to exercise packaged
configuration reporting, legacy FDE detection, ambiguous selection,
duplicate ZIP entries, invalid ZIP/LFS content, bounded text reads, SDK
refusal and preservation of existing output. It does not validate a real
boot image or run Android.

## SDK33 TrafficStats queries on the legacy kernel

The selected Android 13 native TrafficStats entry points unconditionally
read BPF maps. The GM8 build-tree config has BPF_SYSCALL=n and CGROUP_BPF
absent, while xt_qtaguid is enabled. The SDK33 read-side patch restores real
queries from /proc/net/xt_qtaguid/iface_stat_fmt and stats when the existing
ro.kernel.ebpf.supported property is explicitly false.

The property defaults to true and is cached once. BPF-enabled/default
devices retain the BPF reader. A failed BPF read does not silently fall back
to a second accounting source. Legacy read errors remain the TrafficStats
UNKNOWN value (-1), not a fabricated successful zero. Valid empty counters
or an absent UID in a readable valid snapshot are zero, as in the legacy
query API.

The interface reader supports the GM8 kernel's actual ifname /
total_skb_rx_bytes header and 17-column format, plus the older five-column
format. It aggregates interfaces or selects an exact name. TCP packet
queries return UNKNOWN when the selected rows lack TCP counters. The UID
reader aggregates counter sets only from tag-zero rows, avoiding double
counting the tagged rows already included in that aggregate. Per-UID TCP
packet queries remain unsupported.

Rows are bounded to 4096 bytes. Negative, malformed and overflowing fields,
truncated rows, read errors or aggregate overflow do not publish partial
results. The patch adds no writes to procfs, socket tags or permissions.

Important scope: this restores only the three native TrafficStats query
entry points (total/interface/UID). It does **not** implement the persistent
NetworkStatsService map/counter-set path, UID firewall/data-saver backend,
socket tagging, accounting hooks, VPN isolation, CLAT, tethering, or BPF
startup readiness. These remain open before a boot or installation test.
No loader abort suppression or fake bpf.progs_loaded value is introduced.

The kernel source also confirms that xt_qtaguid registers the owner match
itself. The disabled standard NETFILTER_XT_MATCH_OWNER option does not, by
itself, show that this kernel lacks owner matching. No kernel option is
changed by this read-side port.

### Component build

```sh
bash device/gm/GM8_sprout/tools/build-20.0.sh network-stats
```

This stage prepares the reviewed source ports, records the source manifest
and audit, runs the source/host checks, selects the existing userdebug target
and runs only m libservice-connectivity -j32. Output is retained in the
timestamped network-stats.log. A failed native build stops the workflow.
No target-files, boot image, installation ZIP, signing or phone operation is
requested. Android header/API/ABI compilation still needs to pass on the
user's real build host; the local native fixtures are not that build.

The six read-side regressions compile the actual selected kernel's
pp_iface_stat_header/pp_iface_stat_line bodies together with the new reader
and the actual patched JNI query/dispatch bodies. Kernel data structures,
JNI/property access, BPF callbacks and the procfs location are fixtures.
Temporary files contain the real formatter's output. Coverage includes
interface/UID/set/tag aggregation, TCP availability, malformed and oversized
rows, overflow, missing/unreadable files, explicit legacy selection,
unchanged BPF/default selection and no fallback hiding BPF failures.
SDK/context rejection, existing-header protection, idempotence, reverse
application and unrelated-edit preservation also pass. They do not test
a running kernel's packet hooks, permission labels or actual network traffic.

Reviewed sources:

- https://github.com/LineageOS/android_packages_modules_Connectivity/blob/205270f5728b3c1fda246ec413ee39e83a73df03/service-t/jni/com_android_server_net_NetworkStatsService.cpp
- https://github.com/LineageOS/android_packages_modules_Connectivity/blob/205270f5728b3c1fda246ec413ee39e83a73df03/service/Android.bp
- https://github.com/milhany/android_kernel_gm_msm8937/blob/8f533dcdfaf66be77b8e2c5dbeeb29f773952975/net/netfilter/xt_qtaguid.c

## SDK33 cgroup-v1 process tracking

The first compiled package still used Android 13's cgroup2 process-tracking
path while the current kernel provides cgroup v1. The SDK33 source has
additional memory-controller handling and an activate_controllers argument
absent from the inherited SDK32 patch; that old patch is not reused.

The separate patches/sdk33/system_core patch selects a usable v2 root when
available, otherwise a usable v1 cpuacct root such as /acct. It checks both
the controller metadata and the root cgroup.procs file. This matters because
the reviewed SDK33 setup code can log a failed unified mount yet mark that
root mounted after its subsequent directory mode/owner operation succeeds.

Process creation, kill and cleanup use the same selector. v2 controller
activation remains enabled on v2 and is skipped on v1; the patch does not
write cgroup.subtree_control under /acct. No usable root returns ENODEV
rather than creating uid/pid paths below an empty root. Existing memory
control validation and error propagation are retained.

```sh
python3 device/gm/GM8_sprout/tools/apply-processgroup-20.0.py
python3 device/gm/GM8_sprout/tools/apply-processgroup-20.0.py --check
```

The helper refuses non-SDK33 sources or conflicting patch context, applies
without resetting other edits, and accepts an already applied port.
Configure/compile invoke it automatically; audit only inspects patch state.
Preserve this local system/core change across later syncs.

Host regression compiles the actual patched selector and create/kill/cleanup
entry-point bodies with C++17. Filesystem presence checks use temporary
files; controller metadata and process/kernel operations are fixtures.
Coverage includes real-v2 preference, v1 fallback, misleading mounted flags,
missing roots, v1/v2 activation selection, memory-control errors, kill error
propagation and cleanup selection. The helper's SDK/context rejection,
idempotence and unrelated-edit preservation are also tested. These checks
do not mount a cgroup, signal a process, build against all Android headers
or establish behavior on the phone.

Reviewed SDK33 sources:

- https://github.com/LineageOS/android_system_core/blob/c0500ffe2cc283d61f1e3db1b2c979bfbd9beb8c/libprocessgroup/processgroup.cpp
- https://github.com/LineageOS/android_system_core/blob/c0500ffe2cc283d61f1e3db1b2c979bfbd9beb8c/libprocessgroup/setup/cgroup_map_write.cpp
- https://github.com/LineageOS/android_system_core/blob/c0500ffe2cc283d61f1e3db1b2c979bfbd9beb8c/libprocessgroup/cgroup_map.cpp

## Explicit bring-up userdata policy

The initial package contains /data encryptable=footer in both the vendor
fstab and recovery fstab. The normal-boot SDK33 parser rejects it. The
current build-tree config also reports F2FS_FS_ENCRYPTION=n,
FS_ENCRYPTION=n and EXT4_ENCRYPTION=n; adding a fileencryption flag would
therefore claim unsupported functionality.

For this userdebug bring-up branch, /data is explicitly **unencrypted
F2FS**. Remove the rejected userdata encryptable=footer flag and retain the
filesystem, mount flags, check/formattable/quota policy and all other rows.
Removable-media encryptable flags are unchanged: the SDK33 parser accepts
them on voldmanaged volumes. One source supplies the vendor and recovery
fstabs, so both will receive the corrected entry on the next build.

This is not a production encryption solution. It does not decrypt an old
installation, convert ext4, migrate userdata or make Android 10/12 data
compatible with Android 13. Encrypted installations are unsupported here.
A supported FBE implementation needs separate kernel, Keymaster/userspace
and migration validation. The source preflight rejects reintroduced legacy
FDE flags or unsupported FBE claims on /data. No formatting, filesystem
conversion or changes to a phone are performed by the source helpers.

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
old userdata FDE service. The first build-graph change retained the inherited
encryptable=footer flag. The later userdata correction described above
removes it only from /data and declares unencrypted F2FS bring-up explicitly.
Supported FBE and migration remain separate open work. No formatting, key
deletion or data migration is performed.

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

## CAF bootctrl partition-name compatibility

The selected lineage-20.0-caf boot_control.cpp refers to PTN_MULTIIMGOEM
and PTN_MULTIIMGQTI in its UFS exclusion predicate. Add their canonical
multiimgoem / multiimgqti string definitions beside PTN_XBL_CFG in the
device GPT header. This is a header/source compatibility fix.

PTN_SWAP_LIST, AB_PTN_LIST, slot attributes and all GPT read/write functions
are unchanged. The new names are not added to GM8's partition lists.
A native C++17 compile check reproduced the missing identifiers with the
old header and compiled the actual CAF selection loop with the new one.
The eMMC/UFS list checks passed without accessing any disk. Full Android
recovery/vendor bootctrl compilation and slot switching remain subject to
build-host and device validation.

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
4. The SDK33 process-tracking source port is staged with guarded application
   and native host tests. Validate its cgroup-v1 runtime behavior, task
   profiles and LMKD against the actual 3.18 interfaces.
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
completed SDK33 source sync, m nothing and full target-files compilation on
the build host. Hardware acceptance and the runtime compatibility ports
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
