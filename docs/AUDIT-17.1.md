# GM8 / LineageOS 17.1 source and performance audit

Date: 2026-11-02. Baseline device commit:
c69d66043a02b5b2acb83b499fa48cebed2bbce6.
Paired vendor: a22c80f76f1bc90d07d627bd43af8e959e3b22bc.
Paired kernel: 79997531c5a3b9cf52d608c09e1c584e379f1ff9.

## Scope and evidence

The baseline inventory has 140 text files (135 production/documentation files
and five tests) plus bootanimation.zip. The text tree was retrieved at the
immutable baseline, with manual review concentrated on build/property/init,
power, memory, SELinux, manifest, display/media and Dolby paths. Bootanimation
rendering and all possible hardware behaviors were not tested. Vendor paths,
the selected post-boot script and configuration providers were compared against
the pinned vendor Git tree. Source path checks cover 2585 literal copy inputs;
they do not establish every proprietary blob's bytes or ABI.

References include the supplied stock Pie bugreport/post-boot script, the two
17.1 runtime captures, and LineageOS Q platform sources. Private captures and
device identifiers are not included in the repository. Full Android compilation
and hardware validation must run in gm8-build/on the phone; no such build or
hardware test was performed on the assistant host.

## Changes in this candidate

| Area | Finding | Change / boundary |
| --- | --- | --- |
| Dolby startup | The custom non-core app lacks activity API discovery; a later window_service grant violates Q's vendor-app neverallow. | Keep app_api_service/audio/DMS access; remove direct window_service find and its invalid positive test. Q ActivityManager supplies the window Binder in its common-services map. No coredomain workaround or policy bypass. |
| ART memory | A 4 GiB phone template differs from the actual 3 GiB GM8 stock heap policy. | Use the captured stock heap values below. Preserve application growth/max limits. This is a GC/free-space policy, not a fixed RAM reservation or a promised RSS reduction. |
| Legacy scheduler | CPUSET/memory/I/O controllers are integrated, but SchedTune/EAS is not wired into this QHMP kernel. | Use Q's vendor task_profiles.json override to make only seven unsupported SchedTune profiles empty. Preserve all system cpuset, memory, I/O and timer profiles. No writes granted to generic device files. |
| Interaction boost | Every interaction adds 650 ms and has a 1400 ms minimum; addition can overflow for large input. | Use a 600 ms trial baseline, honor longer framework durations up to the existing 5650 ms ceiling, and remove the fixed tail. The paired msm8937 XML has a 600 ms animation boost; this is a conservative reference, not proof of optimal interaction timing. |
| Boost teardown | Exit can leave the indefinite INTERACTION hint active. | Release an active hint before shutting down/joining the handler. Read failures return before comparing an uninitialized idle-state buffer. |
| Optional sustained mode | DoHint can fail because SUSTAINED_PERFORMANCE is absent, while the HAL still sets its sustained flag and suppresses ordinary hints. | Set the flag only when the hint succeeds. The framework overlay still advertises sustained mode as unsupported. |
| Sleep accounting | Failure to read RPM statistics returns an empty vector with SUCCESS. | Return the defined FILESYSTEM_ERROR status. This does not add an RPM parser for an unverified format or repair suspend. |
| Shipping metadata | Stock reports first API 26, but the product inherits the API-27 launch template. | Use Q's product_launched_with_o.mk and update preflight's matching dependency. SDK remains 29; no security patch level is raised. |
| Extraction | The Dolby fixup case sits in CLI parsing rather than blob_fixup. | Move it to the Q extraction callback; preserve source/section/no-cleanup flags. No vendor re-extraction was performed. |
| Instructions | The example local manifest and main prebuild guide still refer to 18.1/rho. | Align the example with the canonical pinned Q manifest and replace the obsolete prebuild recipe. Preserve the existing GApps refusal guard. |
| Build checks | Source/property drift can silently restore old settings. | Check GM8 source constraints and installed ART/task profiles; retain native kernel IKCONFIG, service/ELF, policy and certificate gates. Clean generated kernel outputs only after policy checks pass. |

### Stock heap reference

| Property | Previous Q 4 GiB template | Captured stock / candidate |
| --- | --- | --- |
| heapstartsize | 8m | 16m |
| heapgrowthlimit | 192m | 192m |
| heapsize | 512m | 512m |
| heaptargetutilization | 0.6 | 0.75 |
| heapminfree | 8m | 4m |
| heapmaxfree | 16m | 8m |

The starting threshold increases while the free-space allowance after GC
decreases. Actual memory and GC pauses depend on workload. Keep Q's
pm.dexopt.install/bg-dexopt=speed-profile, also present in the stock report;
do not force every application/split to full speed compilation. Android Q's
inspected installd does not expose the later background-dex2oat thread property.

### Why empty SchedTune profiles are valid here

Q libprocessgroup loads /etc/task_profiles.json and then replaces named
profiles from /vendor/etc/task_profiles.json. The overrides contain only
HighEnergySaving, NormalPerformance, HighPerformance, MaxPerformance,
RealtimePerformance, CpuPolicySpread and CpuPolicyPack. Those actions target
the unavailable schedtune controller/attributes. They are not a replacement
for actual CPU affinity or nice/real-time scheduling. ProcessCapacity*,
ServiceCapacity*, CameraServiceCapacity, *IoPriority, memory and timer actions
remain inherited from Android. The build still requires working CPUSET,
memory/swap accounting and CFQ group options and keeps SchedTune disabled.
An unmounted /dev/stune directory can remain; it must not be mislabeled as a
functional cgroup or made writable to hide another controller failure.

## Reviewed configuration retained

| Area | Result / remaining evidence |
| --- | --- |
| Kernel/CPU | Keep the 3.18/QHMP pairing, existing clock tables, core-control and thermal protections. Captured cpu0 table is 960000..1401000; cpu4 is 768000..1094400. The prior candidate already replaced impossible frequency requests. No overclock or generic 300 MHz assumption. |
| Stock post-boot | The paired vendor script explicitly selects SoC 313 under msm8937 and configures the legacy interactive path, memory parameters and 1 GiB zRAM. Preserve it rather than applying another SoC's EAS script. Its actual runtime completion/mounts still need collection. |
| zRAM/LMK | Keep the stock 1 GiB target, swappiness 100 and legacy in-kernel LMK for this candidate. Larger swap has CPU/latency tradeoffs. Do not import 19.1 PSI/LMKD experiments or enable low-RAM/Go mode on this 3 GiB device. EINVAL during oom_score_adj can be an exiting task; it is not sufficient evidence to retune kill thresholds. |
| Wi-Fi | The previous candidate adds standard IWifi 1.3, ISupplicant 1.2 and IHostapd 1.1 declarations/init versions, matching Q source. Its build stopped before hardware testing. Association/reconnect/hotspot and driver readiness remain unverified. |
| Display/GPU | Keep the stock-derived V331 stack and existing UBWC policy. The supplied stock report also has framebuffer UBWC enabled, video UBWC disabled and latch_unsignaled=1; Vulkan 1.1 is advertised there. A blanket driver/compression change is not supported by this audit. Persistent flicker needs a reproduction/trace. |
| Camera/media | Preserve the 32-bit camera stack and existing 1080p30 profiles. media.settings.xml points to a vendor-provided file; the Google codec includes also have providers. Do not advertise unsupported Main10/HDR/4K decoding or force FPS/exposure controls to hide poor captures. MOV requires real codec/profile metadata. |
| Dolby ABI/routes | Q and R ABuffer headers inspected for this audit are byte-identical, supporting the existing reviewed accessor patch layout. Call/receiver/unknown-route bypass and listener lifecycle are retained. Native processing and route transitions still require testing. |
| Thermal/charging | The stock thermal HAL pair is selected instead of the generic source HAL with no SoC-313 mapping. thermal-engine.conf remains policy-empty. Kernel/firmware limits are retained; temperatures, units, charging and actual mitigation remain release-critical hardware checks. |
| Battery attribution | power_profile.xml has a legacy seven-frequency single-array model that does not describe the captured two CPU tables. Do not invent current measurements to replace it. A calibrated stock resource/profile is still needed; this affects attribution estimates, not a fix for physical drain. |
| SIM/radio | Retain explicit single-SIM default, dual-modem startup paths and paired radio libraries. The physical-slot overlay currently says one; validate an explicit DSDS configuration before changing this unified tree's physical-slot claim. |
| Generic init | Several generic services have no binary in the pinned vendor files; inherited source modules may provide some. This is an inventory lead, not proof that every candidate is missing. Do not mass-disable modem/charging/security services from this static list. Validate installed paths and live service state. |
| Safety/data | Keep A/B partitions, F2FS policy, keys and existing release identities. Build/signing scripts do not flash the phone or format data. No new Integrity/certification claim is made. |

## Open runtime items

- Runtime now confirms cpu0/scaling_min_freq returns ENOENT while CPU0 is
  offline and the same policy is hosted under CPU1. The hotplug resolver below
  addresses the path; boost application/release still needs hardware retesting.
- RPM/debugfs accounting and the CPU time_in_state reader: verify actual
  available nodes. The status fix does not establish valid residency data.
- Verify the running kernel's controllers, rather than assuming a successful
  source config means the phone has that boot. The packaged IKCONFIG guard
  protects the generated update, not an already installed different slot.
- Retest Wi-Fi, Dolby and fingerprint, then repeat cold/warm launches and a
  fixed app-switch/video workload. Compare pauses/reloads, real battery drop,
  screen-off sleep and temperature. Free RAM alone is not an acceptance test.

### Runtime follow-up, 2026-11-03

The supplied capture contains no FATAL EXCEPTION, fatal native signal or ANR
marker. This is limited to the captured interval, not proof of overall stability.
Private log contents and network/device identifiers are not committed.

- Dolby reaches DAP ready with enabled=true. A remaining gm8_dolby_app to
  gpuservice Binder call denial is addressed with the same targeted binder_call
  used by Q's platform_app graphics initialization. The compiled policy gate
  now requires GPU discovery and this call. Audio/call-route behavior still
  needs listening tests; no vendor-app window_service exception is added.
- QHMP sched_set_boost(0) releases a reference and returns EINVAL when no
  reference is held. ResetOnInit previously attempted that release before a
  LAUNCH acquisition. Disable only this node's initialization reset; retain
  LAUNCH acquisition, expiry and default release. Q FileNode tracks the default
  index without writing when ResetOnInit is false. Other nodes keep their resets.
- Wi-Fi HAL starts and scanning is present. SetupWizard explicitly disables
  Wi-Fi, the legacy HAL reports a stop failure, then SetupWizard enables it
  again. This is not evidence of a spontaneous supplicant crash or a successful
  network association. Later control-socket binds fail because the
  /dev/socket/wifihal parent is missing. Create that directory as wifi:wifi 0770
  before HAL startup, using the existing common QCOM wifihal_socket label and
  permissions. This fixes the missing parent, not a claimed HAL timeout cure.
- TCP tuning writes from hal_wifi_default to proc_net remain denied. No generic
  proc_net write permission is added. Optional packet-fate/ring-buffer features
  being unsupported do not by themselves explain an association failure.
- Repeated missing com.google.android.gsf.gservices provider messages require
  checking the installed Google Services Framework package/provider. They do
  not establish a kernel or heap defect. No GApps replacement is bundled here.
- AppComponentFactory class-not-found messages occur on application-info
  updates with empty dex paths; no matching fatal app exception is captured.
  Keep them separate from a proven broken installed APK. Wallpaper permission,
  optional fingerprint extensions, generic ppd_sun labeling and missing RPM
  statistics remain separate items needing provider/runtime evidence.

Follow-up host checks cover configuration constraints, existing native power
logic and source syntax. A full Android build, compiled policy checks and
hardware retesting are still required for these follow-up changes.

### CPU policy migration confirmed, 2026-11-03

The next read-only capture shows CPU0 and CPU2 offline, CPU1/CPU3 online with
related_cpus 0 1 2 3, and CPU3's cpufreq link resolving to CPU1. The other policy
reports related_cpus 4 5 6 7 and remains accessible through CPU4. There are no
policy* directories under the global cpufreq path. This matches the paired
3.18 cpufreq.c moving its policy kobject to an online sibling; a fixed CPU1
replacement would fail again if CPU1 went offline.

The Q libperfmgr patch now retries a missing CPU0/CPU4 scaling_min_freq or
scaling_max_freq endpoint through an accessible sibling. It rechecks
related_cpus at each open and accepts only the original four-CPU policy. An
existing original endpoint remains preferred. Other endpoints and non-ENOENT
failures, including EACCES, retain their behavior. Failed resolutions preserve
the existing 500 ms retry; current-value tracking changes only after a successful
write. This lets a boost release follow a policy move without forcing cores
online, changing clock values, caching another unstable CPU number or adding
permissions. The minimum was 1209600 during capture while writes restoring
960000 repeatedly failed; this is a real failed release path, not proof that
it explains every pause or battery complaint.

The same capture confirms the intended kernel/controller config, captured-stock
heap values and speed-profile installation policy are running. MemAvailable
is about 1.25 GiB, swap total is 1 GiB and swap usage about 325 MiB at this one
snapshot. It does not show memory exhaustion at that moment or establish
worst-case app-switch performance. Google Services Framework is installed, so
the earlier missing-provider messages require provider/initialization evidence,
not simply installing an assumed missing package. The Wi-Fi HAL socket parent
is still absent on this older installed build; retest the prior init fix with
the new full update.

cpufreq_hotplug_17_1_test.py compiles the actual Q FileNode, Node and RequestGroup
with g++/UBSan and Android boundary fixtures. It exercises boost/release across
a representative move, min/max endpoints and both clusters, wrong/malformed
policy rejection, failed-write retry/recovery, injected EACCES without fallback,
unchanged unrelated-node behavior and balanced boost initialization. Patch
application accepts vanilla/errno-only Q sources, is idempotent and rejects
unexpected source drift. This is not a real sysfs or Android hardware test.

## Validation

- All device XML/JSON and Python sources parsed; shell entry points passed
  syntax checks. Literal copy paths were checked against device files and the
  pinned vendor inventory, without claiming all proprietary bytes were hashed.
- device_config_17_1_test.py rejects the old heap/launch template, forbidden
  window lookup, invalid HIDL/frequency requests, accidental override of working
  profiles and forced full-AOT install policy.
- power_runtime_17_1_test.py compiles actual C++ with g++/UBSan and boundary
  stubs: minimum/explicit/huge hints, release timing, teardown, unsupported and
  supported sustained mode, and failed/successful stats status all pass.
- extract_hook_17_1_test.py runs the real shell entry with an isolated helper
  fixture, preserving flags and invoking all four Dolby callbacks. No blobs
  or vendor tree are extracted/modified by that test.
- Packaged ART/profile fixtures reject stale values, honor Q's later vendor
  property overrides and ignore recovery-only properties. Existing signed-wrapper
  fixtures retain original keys/latest on failure and support update/resume.
- Full Android compile, compiled policy, native linker behavior, actual memory
  savings, battery drain and hardware operation are still required on the
  builder/phone. Host checks do not prove those outcomes.

## Primary source references

- Q vendor-app restrictions: system/sepolicy/public/domain.te (lineage-17.1).
- Q Binder cache: frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java,
  getCommonServicesLocked.
- Q graphics app access: system/sepolicy/private/platform_app.te and
  public/service.te (gpu_service is an app_api_service).
- Q power node initialization: system/extras/libperfmgr/Node.cc and FileNode.cc;
  paired kernel kernel/sched/qhmp_fair.c, sched_set_boost.
- Paired 3.18 CPU hotplug: drivers/cpufreq/cpufreq.c,
  update_policy_cpu/kobject_move; include/linux/cpufreq.h,
  related_cpus includes online and offline CPUs.
- QCOM Wi-Fi socket: hardware/qcom/wlan/qcwcn/wifi_hal/wifi_hal.cpp and
  device/qcom/sepolicy-legacy-um/vendor/common/{file.te,file_contexts,hal_wifi.te}.
- Q vendor profile replacement: system/core/libprocessgroup/task_profiles.cpp
  and sched_policy.cpp; unrelated capacity/I/O/timer profiles stay active.
- Q heap template and ART defaults: frameworks/native/build/phone-xhdpi-4096-dalvik-heap.mk
  and build/make/target/product/runtime_libart.mk.
- Q launch API: build/make/target/product/product_launched_with_o.mk.
- Q boot property precedence: system/core/init/property_service.cpp,
  property_load_boot_defaults.
- Q/R ABuffer: frameworks/av/media/libstagefright/foundation/include/media/stagefright/foundation/ABuffer.h.
