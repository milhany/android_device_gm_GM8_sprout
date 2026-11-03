# GM8 Android 10 runtime log audit, 2026-11-03

Baseline device: a007714eb6c64f58bdc56338d137457c74426726.
Paired vendor: a22c80f76f1bc90d07d627bd43af8e959e3b22bc.
Paired kernel: 79997531c5a3b9cf52d608c09e1c584e379f1ff9.

## Capture scope

The supplied 18,093-line capture was scanned across all priorities, with
warning/error families and their surrounding lifecycle events reviewed. It has
1,683 error-priority and 3,594 warning-priority lines, including stack frames
and repeated app messages. These are not counts of distinct ROM defects.
There is no FATAL EXCEPTION, fatal native signal or ANR marker in this interval.
This does not establish stability outside the interval. The clock is corrected
during network setup; the wall-clock jump is not several hours of measured
uptime or a multi-hour operation.

No private capture, network name/address, account identifier, enrollment ID,
subscriber ID or key is included here.

## Results of the previous candidate

| Area | Evidence and limit |
| --- | --- |
| CPU frequency writes | No Failed to write to node message appears, including the former CPU0 ENOENT/default-release loop. This is positive evidence for the hotplug fix, not a measurement of every boost's frequency or all workload latency. |
| Scheduler boost | The former unowned sched_boost=0 EINVAL loop is absent. |
| Dolby application | DAP ready reports enabled=true; the prior gpuservice Binder denial is absent. Native processing subsequently transitions from DAP_BYPASSED to PREROLL_ACTIVE. Listening and receiver/call bypass tests are still required. |
| Wi-Fi socket | The former missing /dev/socket/wifihal bind failure is absent. |
| Wi-Fi connectivity | DHCP ACK/confirmed lease, DNS success and HTTP/HTTPS 204 connectivity probes establish working connectivity in this capture. Teardown still has the race described below. |
| Fingerprint | Enrollment reaches remaining=0 and the framework completes the client. The initial enrollment cancellation belongs to the transition between enrollment screens; it is not proof of a failed final enrollment. Unlock/authentication accuracy is not measured. |

## Changes prepared from this capture

### Bounded Wi-Fi teardown waits

Q wifi/1.3/default/wifi_legacy_hal.cpp waits only 100 ms for cleanup/event-loop
termination. The failing cleanup completes about 216 ms after the exit request;
the later shutdown takes about 97 ms and succeeds. This identifies a real
deadline mismatch rather than a failed association or a daemon crash.

Increase the HAL ceiling to 1000 ms. The existing wait predicate, cleanup,
callback, error on true timeout and event-loop state handling remain intact.
There is no forced success or unconditional sleep. The supplicant death
confirmation arrives about 152 ms after termination while its Q deadline is
50 ms; increase that bounded confirmation wait to 500 ms. Its per-stop death
recipient counts the latch down directly, without waiting to acquire mLock.

The guarded patch validates both Q sources before writing either. The regular
build applies it and records hardware/interfaces and frameworks/opt/net/wifi
revisions/local edits alongside system/extras. Preserve these edits across syncs.

### Package-specific stock TimeService client

com.qualcomm.timeservice starts as an ordinary application UID in platform_app
and is denied connection to the time daemon's abstract Unix socket. Assign only
that platform-signed package to gm8_time_app and permit its connection to
time_daemon, plus normal application API discovery. It is a vendor app domain;
do not add coredomain, a Treble exception attribute, or socket access for all
platform applications. Extend the compiled-policy gate to require both vendor
app domains in appdomain, outside coredomain, and the TimeService connection.

The separate AlarmManager RTC ENODEV message still needs the actual RTC device
layout; this policy correction is not a claim to repair a kernel RTC driver.

### Stock audio/video performance client selection

The supplied stock Pie report has
ro.vendor.extension_library=libqti-perfd-client.so. Q's selected CAF audio and
video HALs use that property to load perf_lock_acq/perf_lock_rel. The new log
explicitly reports the property missing in video, alongside audio perf-lock
acquire/release failures. Both matching vendor client paths already exist in
the pinned vendor copy list. Restore the stock property without changing
performance resource arrays, CPU frequencies, hint durations or the selected
client binaries.

Before signing, require the effective property, ARM32/AArch64 shared client
headers, and the 64-bit client's exported acquisition/release entry points.
This verifies selection and packaged dependencies; it does not establish
successful live perf requests. Unsupported cluster/scheduler requests and the
perfd default-values file error below remain separate issues.

### Explicit libperfmgr node types

Sixteen file nodes omit the optional Type field. Q emits an error-priority
message and uses File anyway. Set Type=File explicitly for these nodes,
preserving the two Property nodes and every value, default, duration and flag.
This corrects configuration clarity; it is not a performance improvement claim.

## Remaining families and disposition

| Family | Finding / next evidence |
| --- | --- |
| Audio routing/backend | Sixteen speaker transitions report missing BE DAI Name Table, backend index -14, and invalid snd_device/backend checks. Compare the actual ALSA control interface and the selected CAF machine code before changing mixer IDs or forcing a backend index. No made-up routing/calibration values are introduced. |
| Dolby format negotiation | A first format-5 SET_CONFIG fails; a second SET_CONFIG configures buffers and the effect later enables. Treat this as recovered negotiation in this interval, not evidence to rewrite the native effect or claim every format works. |
| Audio fast/mic interfaces | One FAST-track request falls back to a larger buffer and mic-mute calls report not implemented. Exercise real playback/calls/mic mute before altering the legacy HAL. |
| Legacy perf service | Invalid cluster id 2, unsupported scheduler-frequency aggregation and inability to open/create the default-values file occur. Need actual service/config/directory state and requested resources; do not add a third cluster or expose unimplemented scheduler controls. |
| FPC kernel/HAL interface | Forty-four fingerdown_wait ENOENT messages occur, yet enrollment completes through the available IRQ path. Compare the exact driver/HAL contract before adding an attribute with invented semantics. Do not add a dummy successful sysfs write. |
| FPC optional extensions | Two framework finds for navigation/sensor-test interfaces hit default_android_hwservice. Do not grant access to that generic type, expose test/calibration services or claim gesture support without a real provider. |
| Display startup helper | ppd_sun is executed under generic vendor_file and is rejected. Establish its proper executable domain and hardware role before enabling it; do not allow init to execute all vendor_file binaries. |
| GPU/display | The old EGL driver advertises a missing 1.5 API; one GL 0x0501 and a PCC/color-transform restore failure also occur. No SurfaceFlinger native crash is captured. Need reproduction and capability/mixer evidence; do not replace the driver or silently change hardware-composer/UBWC policy. |
| Wi-Fi TCP tuning | Five proc_net write AVCs affect tcp_limit_output_bytes, tcp_use_userconfig and tcp_adv_win_scale. Connectivity succeeds despite them. Inspect exact labels/DAC and tuning values; no generic proc_net write grant or DAC override is added. |
| Wi-Fi RPS/driver extras | Missing RX queue rps_cpus files, unavailable cld80211/offload/fate/ring-buffer features, scan IE error -524 and missing multicast-filter sysctls remain legacy feature mismatches. RPS messages may include nonexistent queues/interfaces. Do not create fake capabilities or globally disable scans. |
| Bluetooth codecs | aptX/aptX-HD encoder libraries and the LDAC decoder are absent. This does not show failure of SBC/AAC or of the LDAC encoder. Do not advertise or fabricate missing codec binaries. |
| Bluetooth scheduling/SoC | The stack falls back to pronto and one SCHED_FIFO request is refused. Validate actual adapter/pairing/audio behavior before adding realtime scheduling permissions or assuming a different controller. |
| Modem/SIM | No-UICC/invalid-subId/not-yet-loaded SIM messages dominate telephony. This interval does not establish baseband loss. No automatic SIM-mode changes are made. |
| GNSS/location | Older firmware rejects several newer control/configuration requests; XTRA/SNTP initially lack DNS, and apps report no cached location. Need a real satellite fix/test; no fake constellation support or location is added. |
| GSF/direct boot | All 170 missing gservices-provider messages precede the observed USER_UNLOCKED event; GSF is installed, and GMS later reports disabling an old GSF version. The direct-boot timing explains why missing-package conclusions are unwarranted. Inspect the exact GApps provider/version lifecycle before changing it. |
| Google Search native dependency | Velvet cannot load libcronet.72.0.3626.14.so. This is an actual packaged application/native-library mismatch; the warning alone does not prove the whole APK is the wrong bitness. Correct the matching GApps APK/library set separately, not the kernel or every app's compiler filter. |
| Google network/account/module noise | Check-in, GCM authentication, Nearby, providerinstaller/Chimera, hotword models, language packs, anonymous account lists, wake-lock bookkeeping and sync fail during initial/no-network or module setup. Connectivity later validates. Do not reset accounts/data or bypass background/security restrictions based solely on these messages. |
| Permission/config XML versions | Unknown permissions such as READ_MEDIA_IMAGES/AUDIO and unknown component-override tags indicate configuration from newer API contracts or optional packages. Inventory the actual provider before editing; do not add fake permission definitions to Android 10. |
| Activity/process management | Thirty-nine recorded kills are empty-process cleanup; one is remove-task cleanup. None is a recorded foreground LMK kill. Boot/unlock has slow dispatches, contention and an early 84 s delivery message, without an ANR. This is not a steady-state app-switch benchmark or proof of a particular memory limit. |
| LMK/accounting | Twenty-nine oom_score_adj EINVAL messages and absent uid_time_in_state/RPM stats need task-lifetime/accounting evidence. Do not infer memory exhaustion or tune thresholds from these alone. Frequency/battery attribution accounting is separate from actual energy consumption. |
| Storage/vold | 1280 Skipping due to root namespace warnings are namespace traversal messages. Proc-fd entries disappearing, first-user CE paths, bootstat/backups/widget/recents files absent during initialization, and fallocate falling back are not filesystem-corruption evidence. No format/ownership recursion is proposed. |
| UI/framework resources | App resource IDs, incomplete settings metadata, input-channel safeguards, first-run notification sound URI failures, notification-assistant caught NPEs and retired windows are recorded without a matching fatal exception. Identify a visible reproduction before changing framework security/resource behavior. |
| Optional platform services | Missing wifirtt, context hub, some geocoding/activity-recognition providers, weaver/keystore optional records and unsupported vibrator/light effects are capability/provisioning probes. No fake service or feature is added. |

## Validation and limits

- wifi_stop_17_1_test.py compiles the actual Q stop and event-loop methods with
  Android/HIDL/driver boundaries as fixtures. Fast and 220 ms cleanup succeed;
  a genuinely late cleanup retains the timeout error/pending state; an already
  stopped HAL remains successful. Source patch idempotence/drift rejection and
  preservation of both files on a changed second source were checked.
- Existing actual-C++ CPU hotplug/boost-release and interaction/power tests,
  configuration checks, wrapper regression checks and changed-source syntax
  checks are rerun for this candidate.
- Packaged perf dependency fixtures accept the stock property/client headers
  and required 64-bit symbols, and reject a missing property/library/export.
  These are format fixtures, not executable hardware libraries.
- Full Android/Java compilation, neverallows and compiled policy checks run
  on the builder. Actual Wi-Fi reconnect/hotspot, native audio/calls, clock
  persistence and app-switch/battery tests remain required on the phone.
  No full ROM build or hardware test was performed on the assistant host.

## Primary source cross-checks

- Q hardware/interfaces/wifi/1.3/default/wifi_legacy_hal.cpp, stop/runEventLoop.
- Q frameworks/opt/net/wifi/service/java/com/android/server/wifi/SupplicantStaIfaceHal.java,
  terminate and its direct latch-counting death recipient.
- Q system/sepolicy/public/domain.te core/vendor socket separation;
  device/qcom/sepolicy-legacy-um/vendor/common/time_daemon.te.
- Selected Q CAF audio hal/audio_extn/audio_extn.c and media
  mm-video-v4l2/vidc/vdec/src/omx_vdec_msm8974.cpp performance-library loaders.
- Supplied stock Pie SDK-28 report's performance property and pinned vendor
  32/64-bit client copy inputs. The original report remains private.
