# GM8 Q runtime follow-up, 2026-11-04

Reviewed source baseline: 4af41f7bb3699ab2a9f0101c50550b95d51c9231.
The supplied capture has 34,356 lines, including 5,119 error-priority and
10,532 warning-priority lines. Repeated stack frames and telemetry dominate
these counts; they are not distinct defect counts. No FATAL EXCEPTION, fatal
native signal or ANR marker is captured. This is not a stability or battery
benchmark outside the captured interval. Private logs, network/account/device
identifiers and DRM material are excluded from the repository.

## Results of previous changes

- Qualcomm QImsService is now running and exchanging configuration/service
  status messages with ImsRadio. This supports the dynamic binding correction.
  SIM state is still ABSENT; no carrier IMS registration or VoLTE/VoWiFi call
  success is established. Failed optional provisioning items with no active
  subscription are not evidence to invent carrier provisioning values.
- Wi-Fi associates, receives a DHCP lease and passes connectivity validation.
  The former stop deadline and missing control-socket failures are absent.
- No former libperfmgr frequency/default-release write failure, unowned scheduler
  boost reset, missing power-node Type error or missing media extension-library
  error appears. The previous audio perf-lock acquire/release error is absent.
  Absence of a message alone does not measure every hardware operation.
- The earlier TimeService client socket AVC is absent, but native time daemon
  accept/receive failures remain; do not claim clock persistence is repaired.

## Proposed corrections requiring explicit user authorization

These two source corrections were prepared locally but have not been published
or installed. Automatic approval review rejected the repository write because
it changes persistent DeviceConfig authority and a SELinux process permission
beyond the user's general log-review request. The published follow-up is limited
to this report and the read-only collector; the existing ROM policy is unchanged.

### Factory GMS DeviceConfig owner

PackageManager explicitly ungrants WRITE_DEVICE_CONFIG from GMS. Later GMS
PlatformConfigurator repeatedly fails to write DeviceConfig: 182 server-side
permission exceptions, 2,002 DatabaseUtils error lines including their stacks,
and 4,451 PlatformConfigurator warning lines.

Q's base config_deviceConfiguratorPackageName is empty, and the device had no
override. PermissionManagerService grants permissions carrying the configurator
protection flag to the known configurator package. PackageManagerService obtains
that package from this resource through ensureSystemPackageName, which requires
an actual factory/system package; a data-only install is not accepted.

Proposed: select com.google.android.gms in the existing framework overlay. This uses Q's
normal package/permission mechanism, not a manual pm grant, privilege XML entry,
SELinux exception or framework permission bypass. With no factory GMS in a
vanilla installation, PackageManager resolves no owner. Verify the resulting
grant and absence of repeated exceptions on the installed update; other GMS
download/snapshot/API errors are independent and can remain.

### Legacy process-group cleanup for app zygotes

The log has 38 system_server to app_zygote process getpgid AVCs and 39
libprocessgroup getpgid permission failures around Chrome app-zygote cleanup.
Q policy already permits system_server to kill app_zygote, but its getpgid rule
targets appdomain; app_zygote is a separate public domain, not an appdomain.

Proposed: permit only system_server app_zygote:process getpgid. This allows the existing
authorized cleanup to query that process group; it is not a grant to all apps,
an isolated-app file permission, a controller change or a new kill policy.
The prepared compiled-policy check would require this exact relation before a full build.
Actual cleanup behavior and lack of AVCs still require device retesting.

## Remaining findings

| Area | Evidence / boundary |
| --- | --- |
| Widevine | Ten attempts cannot read firmware_mnt/image/widevine.mdt with EACCES, then cannot find alternate paths. Each reports failure to initialize L1 and fallback to L3; this is not proof that all DRM playback fails. The mount is root:system with restrictive masks, while both candidate DRM init definitions omit system from their supplementary groups. The log does not identify which service binary owns the failing PID. Collect process identities/groups and actual path labels/modes before changing a service; do not world-read firmware, disable SELinux, modify provisioning or claim L1 certification. |
| Time daemon | Thirty accept failures and 29 failed receives remain. No TimeService connection AVC is shown. Need actual daemon/protocol/RTC state; do not add socket policy for a non-policy error. |
| CPU accounting | Eleven cpu0/cpufreq/stats/time_in_state reads fail and uid_time_in_state is missing. These are battery/CPU attribution readers, distinct from the power hint writes whose former errors are absent. No invented residency statistics or clock changes are introduced. |
| Isolated Chrome services | Forty-one isolated_app app_data_file setattr AVCs affect model/component files. Preserve the sandbox boundary; do not grant isolated processes general app-data access just to remove logs. A component-load failure needs specific ABI/API and file-descriptor analysis. |
| Memtrack | Two priv_app lookups of IMemtrack are denied. No blanket access for privileged applications or fake memory HAL is added. |
| Wi-Fi driver extras | Two TCP tuning writes remain denied. Optional RX-queue/RPS, cld80211, offload, packet-fate/ring-buffer and scan-IE capabilities are missing/unsupported. There is also a transient busy scan. Connectivity later works; these are not a justification for generic proc_net writes or advertising unimplemented features. |
| Fingerprint | Optional navigation/test interfaces still lack providers; fingerdown_wait is absent while the IRQ fallback is present. Two authentication operations are cancelled; this alone is not an authentication failure. No dummy sysfs operation or default_android_hwservice grant is added. |
| Google app/module state | File-group population and stale Phenotype snapshots fail, some modules/components are unavailable, reminders return HTTP 404, and newer app permission names are unknown to Q. Fixing DeviceConfig authorization does not promise to fix these unrelated app/service contracts. Do not invent Android 11+ APIs/permissions or clear user accounts/data. |
| Video/app telemetry | YouTube QoE telemetry is logged at error priority; 247 messages say an offered playback type is not playable. These messages alone do not locate a decoder/GPU bottleneck or quantify frame drops. Need a real reproduction with codec/player state before tuning decoding or replacing the GPU stack. |
| ART/application API guards | Hidden API/linking and unknown runtime flag warnings occur with newer apps. The capture has no matching fatal app exception. Do not globally disable hidden-API enforcement or force full-AOT compilation for every application. |
| Process/memory state | Empty-process and isolated-service cleanup is recorded. There is no general foreground-crash/ANR or RAM-pressure measurement proving that all kills are excessive. Fifty oom_score_adj EINVAL writes remain task-lifetime/accounting leads, not grounds to retune LMK thresholds. |
| Framework/boot probes | Missing initial cache/provider/backup files, retired input channels/surfaces, first-run resources, absent SIM/operator data, unsupported light/GNSS extras and caught assistant exceptions remain. Treat visible functionality separately from logging priority. |

The targeted runtime collector now records the GMS DeviceConfig permission line,
DRM service/process identity, accessible Uid/Gid/Groups fields and firmware path
metadata. It does not read firmware bytes, keys, subscriber IDs or account data.

## Validation

The prepared configuration regression checks reject a missing/empty configurator
owner and passed locally, along with changed-source syntax checks. These
permission-related source/check changes remain unpublished pending authorization.
The published read-only collector passes shell syntax checks; existing IMS
selection and compiled-policy/neverallow/file-label gates are unchanged. The
proposed app_zygote check would run against real compiled policy on the builder.
Full Android compilation, installed permission
reconciliation, process cleanup, DRM process selection and hardware testing
have not been performed on the assistant host.

## Primary sources

- LineageOS/android_frameworks_base lineage-17.1 core/res/res/values/config.xml,
  services/core/java/com/android/server/pm/PackageManagerService.java
  getDeviceConfiguratorPackageName/ensureSystemPackageName, and
  pm/permission/PermissionManagerService.java configurator permission handling.
- LineageOS/android_system_sepolicy lineage-17.1 public/app_zygote.te and
  private/system_server.te: distinct app-zygote domain and existing kill access.
- Pinned vendor Android DRM 1.2 Widevine init RC and selected Q DRM 1.0 RC,
  plus the device modem firmware fstab masks. Actual process selection remains
  a device-side question.
