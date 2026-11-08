# GM8 Android 10 stability candidate — 2026-11-08

Branch in all three repositories: `lineage-17.1-stability-20261108`.
This is a combined source candidate, not a hardware-validated release.

## Included changes

| Repository | Change | Acceptance boundary |
| --- | --- | --- |
| kernel | FT8006 per-device gesture lock and IRQ-wake ownership; propagate failed I2C reads/writes and release owned wake votes during resume/remove | Actual extracted C host fault-injection tests passed; hardware suspend/resume still required |
| kernel | Non-reentrant QSEE final listener close wakes the matching blocked command, which sends a FAILURE response through the existing TZ path before listener teardown can acquire the app mutex | Actual extracted C reproduces the original close/wait deadlock and tests the candidate; real TZ firmware and phone validation still required |
| device | Exact `persist.vendor.camera.aeinfo` → `camera_prop` mapping with compiled-policy and target-files checks | Uses Q's existing userdebug setter; no broad allow or permissive domain; does not improve image quality by itself |
| vendor | Register the existing GNSS 2.0 init service's `IGnss/default` interface | Repairs init service lookup only; not proof of a GPS fix or improved RF reception |
| device | Run gesture and QSEE host tests before the Android build, retain source hashes, and check the compiled camera label/policy | Full Android checks run on the build host; not performed in the preparation workspace |

## Source selection and build

Fetch and select this branch in device/gm/GM8_sprout, vendor/gm/GM8_sprout
and kernel/gm/msm8937 before invoking the existing signed-release helper.
Use ordinary `git switch --detach FETCH_HEAD`, without a forced checkout or
reset. If Git reports conflicting local work, preserve it and compare it
before switching. The private candidate packages are not needed after all
three source branches are selected.

Inside the existing `gm8-build` container as builder, from the SDK29 checkout:

```sh
GM8_INSTALL_MODE=update bash device/gm/GM8_sprout/tools/build-release-17.1.sh
```

The existing helper reuses the release key directory, runs source/policy
checks, rebuilds KERNEL_OBJ and modules, creates target-files and signs the
update. It preserves the previous latest release on failure. It does not
install anything on a phone. Do not install a separately built boot image
with stale vendor kernel modules.

## GNSS investigation and optional diagnostic

The recent GNSS capture increased satellite-status counters without a new
location report or a new qualifying top-four C/N0 sample. Historical fix/TTFF
statistics were not counted as new fixes. An XTRA injection request alone did
not establish a successful complete injection. Native unknown-session errors
coincided with the diagnostic's deliberate GNSS service restart, so normal
runtime failure was not established by that experiment.

`tools/diagnostics/gm8-gps-diagnose.sh` preserves the previously prepared
optional root diagnostic. It changes temporary verbosity through bind mounts
and deliberately stops/restarts GNSS services; this can invalidate sessions.
It is not installed or run by the ROM build. Do not repeat it as a GPS fix or
use it as the clean-boot fix test. Its cleanup/config preservation host tests
are in `tools/tests/gps_diagnostic_17_1_test.py`.

## Open work

QSEE final-close progress does not explain why qseecomd terminated. Explicit
UNREGISTER ioctl and reentrant QSEE paths are outside this narrow candidate.
GPS RF/assistance/session performance still needs a clean-boot outdoor test.
Rotation worked in the latest observation but is not declared permanently
fixed by a source change. Thermal/battery, video, IMS and app-specific issues
remain separate acceptance items; they are not all resolved by these patches.

Required phone acceptance includes boot, PIN/lock screen, fingerprint,
application key operations, Wi-Fi, repeated suspend/resume and extended use
without another Watchdog loop. A single successful boot is insufficient.

No keys, credential files, raw user logs or location records are published.
