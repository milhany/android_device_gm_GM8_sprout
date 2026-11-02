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

## Controller and fingerprint follow-up

The runtime-state capture selects FPC and shows only cpu/cpuacct mounted.
The cpuset, stune and memcg paths are ordinary tmpfs directories, not mounted
controllers. The paired 3.18 defconfig also lacks these controllers. Enable
CPUSETS, MEMCG (including swap accounting), and
the BLK_CGROUP/CFQ group interface expected by Android Q. Keep MEMCG_KMEM off
and retain the existing in-kernel lowmemorykiller. This is compatibility work,
not a guarantee of lower RAM use: memory accounting itself has some overhead.

SchedTune is not integrated into this QHMP scheduler: tune.o is not linked and
the EAS energy-model hooks used by tune.c are absent. Leave SCHED_TUNE and
CGROUP_SCHEDTUNE disabled. Its unmounted /dev/stune path is not a functional
controller and must not be made writable by adding generic device-type rules.
Remove the device init write to schedtune.colocate, which this kernel does not
implement. The new boot build gate inspects the resolved .config, rather than
assuming requested defconfig options survived Kconfig dependency resolution.

Add the missing standard android.hardware.biometrics.fingerprint 2.1/default
hwbinder entry. Preserve the existing driver-based FPC/Sunwave selection and
vendor extensions. Registration and actual enrollment still need device tests.
The target-files gate now verifies this standard entry as well as IPerf.

The captured CPU minimums (960000 and 768000) match the lowest frequencies
actually exposed by each cluster. The power HAL runs as root, and Q's public
domain policy already grants CPU-directory traversal/symlink reads. Do not
change frequency tables or add redundant traversal permissions from this
capture. If fd=-1 persists after the perf dependency fix, obtain the actual
open error/AVC before changing node ownership or policy.

The lmkd EINVAL messages do not by themselves establish a broken kill policy:
this kernel can reject oom_score_adj after a task has lost its mm during exit.
Do not copy the 19.1 experimental LMKD/PSI settings into this Q candidate.

Host checks use the real Kconfig parser to resolve the requested controller
options and reject a resolved config missing any required controller. These
checks are not a full Android/kernel build or hardware validation. After
installing the paired kernel/vendor update, check actual cpuset, memory and
blkio mounts and labels again; SchedTune intentionally remains unsupported.

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
