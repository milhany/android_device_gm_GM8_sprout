# First Android 10 runtime correction

The submitted boot log reaches BOOT_COMPLETED and opens the camera preview.
It also shows recurring vendor failures, rather than a general Android crash.

## Changes in this candidate

- The 64-bit stock perf service cannot find `vendor.qti.hardware.perf@1.0.so`.
  Q's selected `vendor/qcom/opensource/interfaces` branch has no perf package.
  Add Lineage's legacy IPerf 1.0 source with a Q-compatible HIDL build and a
  separate package root. Install system/vendor variants and register the
  service in the device manifest. The five methods/signatures/order match the
  legacy GM8 interface exports. The service's eleven imported IPerf base symbols
  also resolve in the stock library inspected for comparison. No stock binary
  is added or replaced in this change.
- The time daemon exits after SELinux rejects setgid. The actual stock binary
  imports setgid and setuid and contains both corresponding failure paths.
  Grant only these capabilities to its existing domain; sys_time is already
  granted by the imported Q policy.
- GM8Dolby runs as platform_app and cannot find its DMS service. Assign only
  the platform-signed privileged package `org.lineageos.gm8.dolby` to a dedicated
  app domain and make that domain a DMS client. Keep existing client/server
  Binder callbacks. No permission is granted to platform_app generally.

The copied IPerf source retains its Apache-2.0 copyright/license header. It is
from LineageOS/android_vendor_qcom_opensource_interfaces, lineage-18.1,
`perf/1.0/IPerf.hal`. Its SHA-256 and frozen interface hash are
`3b62e5f205de632f6c1d6b46d01a2945b5a855ec4a98247515ce8d14b51a4fa3`.
The same source/hash exists in that upstream repository at commit
`b75ec20e94b35e067f3af67e628df294b49505d0`.
Only Q-supported build properties are used; system_ext_specific is omitted.

The target-files build checks that the perf AArch64 library and service are
packaged, and that IPerf/default is registered, before starting signing.
The early SELinux checks remain enabled. Host source/package checks are not
a full Android compilation or hardware validation.

## Still needs device evidence

- libperfmgr reports fd=-1 for cpu0/scaling_min_freq. Determine whether opening
  the node fails because of ownership, timing or absence before changing power
  limits. The power profile has not been retuned in this candidate.
- FingerprintService reports that the standard fingerprint HIDL is unavailable.
  Read `vendor.gm8.fingerprint.sensor`, driver nodes and lshal before choosing a
  driver or forcing a HAL.
- lmkd reports EINVAL while writing oom_score_adj, and zygote encounters a tasks
  file labeled as device on tmpfs. Capture actual mounts/controller state;
  granting writes to the generic device type would hide a likely setup issue.

Do not reuse an earlier --resume signing plan to include these source changes.
Run the normal incremental build-release-17.1.sh, then install and retest.


For an update over the already installed 17.1 build using the same keys, run:

```bash
GM8_INSTALL_MODE=update bash device/gm/GM8_sprout/tools/build-release-17.1.sh
```

Update mode requires every planned signing key to exist, creates no replacement
identity and requests no Format Data. It does not prove the installed phone's
signing identity; use it only when the phone has this same signed 17.1 ROM.
The initial clean-install default remains available for fresh bring-up.

For remaining fingerprint/cgroup/node issues, run the read-only
`tools/collect-runtime-17.1.sh` through `adb shell sh` and review its output.
It collects only hardware service registration, driver presence, CPU node
ownership/values, controller mounts/labels and LMKD settings. It changes no
properties, limits, mounts, files, services or fingerprint templates.
