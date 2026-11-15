# QSEE source audit after the unlogged recurrence

The user reports another failure in the last Lineage 20 build, then installed
ArrowOS 11 without collecting a Lineage failure capture. The available November
12 Lineage bugreport and matching qsee-build.txt describe kernel 8f533dcdfaf6,
before the a95a09e group-exit candidate. They cannot establish the call stack or
cause of the reported recurrence. The Arrow report is a separate build and is
not evidence of the state of the latest Lineage kernel.

This audit starts from kernel a95a09e4390346d2c965118628b81cc3fba35a43 and device
2e13abce13d5d0144c39012fce160105018d6009. It finds reproducible source defects,
not a verified explanation for that last phone failure.

## Reproduced defects and candidate repairs

1. **Client FD first during service group exit.** The previous pre-lock abort
   ran only in the listener final-close switch case. An exiting listener owner
   can first close a client-app FD and block on app_access_lock before any
   listener close is reached. The actual release/wait functions reproduce this
   deadlock. Run the notification before the release type switch, but restrict
   the ordinary matching-ID rule to actual listener handles. Whole-group abort
   still requires PF_EXITING, SIGNAL_GROUP_EXIT and the same referenced PID
   identity; unrelated groups and reentrant notification remain excluded. The
   repair changes the pre-lock entry ordering, not secure-app unload semantics.

2. **Unpublished listener ION leaks.** __qseecom_set_sb_memory imports an ION
   handle and maps it before listener publication. Failed physical-address
   lookup, mapping, SCM registration or rejected TZ registration returned without
   balancing the acquired resources; the caller only freed the list allocation.
   Add paired unmap/free error labels and clear failed pointers. Successful
   registration retains its buffer for the existing unregister path. Real
   firmware registration semantics still require phone acceptance.

3. **List sentinel used as a missing listener.** Linux list_for_each_entry does
   not leave its iterator NULL when no element matches. __qseecom_find_svc and
   the legacy incomplete-command lookup could read a fabricated object based on
   the list head. Preserve an explicit found pointer/flag. A host fixture places
   the sentinel at an ASan redzone; the old incomplete-command function produces
   a global-buffer-overflow on the missing-listener case. Both empty and populated
   unmatched lists and valid lookup are covered. This does not rework the separate
   reentrant incomplete-command lifetime/lookup implementation.

4. **Malformed TZ failure reply.** The error helper passed sizeof(pointer)
   rather than sizeof(message), left scatter/gather metadata uninitialized and
   did not select the 64-bit/whitelist message form. Use initialized 20-byte or
   24-byte messages matching include/soc/qcom/qseecomi.h, select the existing
   whitelist command and keep absent SG metadata zero. Keep actual error returns,
   with balanced RPMB/SSD clock votes on success and failures. Missing listeners
   remain errors; no secure operation is converted to success.

## Validation and limits

- The predecessor independently fails the client-first close, listener setup
  reference balance, malformed failure reply and missing-listener ASan checks.
- Candidate tests compile the actual C function bodies. The existing response,
  close/unregister, PID identity/lifetime and 200 race cases remain included.
- Listener-memory tests inject error pointers and NULL import/map failures,
  physical-address, SCM and TZ failures across 480 attempts and both registration
  message layouts. Successful setup retains its reference until explicit teardown.
- Error replies cover both QSEE message versions and whitelist settings, missing
  listeners, cache/clock/SCM failures and balanced clock votes. Reentrant close
  notification remains disabled as before.
- Address/undefined-behavior sanitizers are used with detect_leaks=0 because
  LeakSanitizer cannot run under this workspace's ptrace supervision. Resource
  reference balance is checked explicitly.
- The build entry points run both QSEE suites before a full Android build. Their
  host fixture tests cover build failure propagation and generated-output cleanup.

These are host/source checks, not an ARM kernel build or hardware acceptance.
They do not establish why the proprietary daemon exits, ownership of listeners
after cross-process FD transfer, normal last-thread exit without group-exit flags,
explicit-unregister cancellation semantics, or recovery from a nonresponding
secure firmware call. No broad timeout, forced daemon restart, premature buffer
release, attestation change or key/data deletion is introduced.

Build the paired candidate kernel and device branches together. Preserve the
existing signing keys and use the existing full runtime/signing workflow; this
audit does not require a new key set or a data format. Until lock/unlock,
fingerprint, Keystore operations, suspend and sustained uptime pass on the phone,
the candidate must not be described as a confirmed QSEE fix or stable release.
