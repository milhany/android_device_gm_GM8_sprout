# QSEE legacy listener-group exit candidate

Paired kernel source candidate: `a95a09e4390346d2c965118628b81cc3fba35a43` on lineage-20.0.
Use it with the expanded qsee_wait_test.py/qsee_host.c in this device revision.

## Evidence and scope

The existing-build capture matches the November 12 blocked-task symbol layouts:

| Waiter | Return address | Source operation |
| --- | --- | --- |
| qseecomd final close | qseecom_release + 0xd0, 0xffffffc0005a3a7c | Immediately after mutex_lock(app_access_lock), before listener unregister |
| Fingerprint command | qseecom_ioctl + 0x540, 0xffffffc0005a8570 | Immediately after mutex_lock(app_access_lock), in SEND_MODFD_CMD |

The process snapshot also shows Keymaster sleeping in
`__qseecom_process_incomplete_cmd`, while the qseecomd leader is a zombie and a
remaining thread is in final close. The system-server main watchdog waits in
TrustManagerService -> Authorization.onLockScreenEvent -> Keystore. These are
consistent with a listener teardown/client-response dependency. The trace does
not record the active listener ID or every mutex owner, so it does not prove
that the candidate below explains every observed hang.

The earlier single-listener repair only marks the listener whose FD is being
closed. If a dying service group owns multiple listeners and closes a different
FD first, final close blocks on app_access_lock before it can close the FD that
the client needs. The old repair's actual C functions reproduce this case in a
host test and require a test-only reply to escape the deadlock.

## Candidate behavior

Each successful listener registration retains its registering thread group's
`struct pid` identity. A numeric PID is insufficient because it can be reused.
Registration failures acquire no identity reference; successful unregister
releases it after removing the listener under the existing list lock. Failed
unregister retains both the registered entry and its reference, matching the
existing lifetime.

The pre-lock close notification remains limited to the closing listener for an
ordinary close. Only when the current task is PF_EXITING and its group has
SIGNAL_GROUP_EXIT does it additionally mark listeners registered by that same
stable group identity. Other registering groups, single-thread exits and
reentrant QSEE response handling are excluded from the expanded notification.
The registering service group remains the owner; the candidate does not add a
listener-ownership transfer or cross-process takeover protocol for inherited FDs.

It wakes the existing response wait so the client returns the existing TZ
FAILURE/ENODEV path. It does not release app_access_lock around shared protocol
state, synthesize successful secure operations, force-unmap an active ION buffer,
use arbitrary response timeouts or change attestation data. Unregister and buffer
teardown remain serialized behind the client. A scoped kernel diagnostic records
newly aborted listeners for an exiting service group.

## Validation boundary

Host checks compile the actual registration, wait, response, close and unregister
functions. The predecessor reproduces the multi-listener exit deadlock. The
candidate passes normal responses, SCM errors, both QSEE command layouts,
whitelist variants, chained listener responses/failures, unrelated groups, two
distinct PID identities with the same numeric TGID, exit-flag guards, registration
failure/lifetime accounting, reentrant exclusion and 100 single-close plus 100
group-close races. Address/undefined-behavior sanitizers pass. LeakSanitizer cannot
run under this workspace's ptrace supervision; local sanitizer validation used
detect_leaks=0, with explicit PID-reference and allocation-balance assertions.

This is not an ARM kernel build or real firmware acceptance. The normal runtime
build also runs this expanded test against the fetched kernel before building.
Fetch the paired device and kernel revisions, rebuild full target-files and sign
with the existing key directory. Preserve the old signed OTA as a rollback
candidate. A boot-only update would omit the paired GPU-statistics and Bluetooth
profile fixes from the device branch.

On-device acceptance: a fresh reboot, repeated lock/unlock and fingerprint use,
Keystore-backed application operations, and uptime beyond the prior trigger.
Confirm no repeat main-thread Keystore watchdog, GPU-statistics system-server
abort or stuck QSEE final close. Repeated service death itself still needs a
cause if it occurs; this repair addresses the teardown dependency, not why a
proprietary service exits. LCD ambient-display and mm-pp-dpps remain separate
open findings.
