# GM8 SDK33 first hardware boot: Wi-Fi service wiring

The owner confirmed the first successful Android boot on 2026-11-12. The supplied
37,490-line log contains kernel, init and userspace startup. Wall-clock time jumps
during startup; use event order rather than treating every printed timestamp as
an accurate elapsed-time measurement. This note omits raw device identifiers.

## Confirmed Wi-Fi blocker

The WLAN firmware loads, the kernel reports `driver loaded`, the vendor Wi-Fi
HAL adds `wlan0` and `p2p0`, and wificond creates the client/scanner interface.
The next step attempts the declared AIDL supplicant instance, but init cannot
find its lazy-service entry. The log contains 197 missing-instance start errors
and 94 WifiThreadRunner timeout messages. Stack traces put the Wi-Fi worker in
`ServiceManager.waitForDeclaredService`, called from
`SupplicantStaIfaceHalAidlImpl.startDaemon`.

The SDK33 wpa_supplicant Android.mk installs its AIDL VINTF fragment, but installs
`aidl/android.hardware.wifi.supplicant-service.rc` only when
`WIFI_HIDL_UNIFIED_SUPPLICANT_SERVICE_RC_ENTRY=true`. This board omitted the flag.
The log lists the vendor init files being parsed without a supplicant RC.

The board now enables that existing upstream gate. The standard RC registers
`android.hardware.wifi.supplicant.ISupplicant/default`, invokes the matching
vendor executable, creates the control socket and retains disabled/oneshot
lifecycle management. No framework AIDL-to-HIDL workaround, firmware replacement
or SELinux relaxation is needed for this identified wiring problem.

The packaged-output inspector and first-boot signer now check the RC, executable
and VINTF instance together. A stale archive with the missing RC is rejected
before signing. This is a packaging consistency check, not proof of connectivity.

## Other findings retained for follow-up

| Area | Evidence | Interpretation / next check |
| --- | --- | --- |
| SetupWizard | Three ANRs while executing `.logging.ScreenOnClock` | Wi-Fi is blocked and initial GApps work is busy. A causal link needs an ANR main-thread trace; retest after the supplicant fix. |
| Process groups | `blkio` mount fails and 35 `/dev/blkio//cgroup.procs` open warnings; memory/cgroup-v2 mounts also fail | CPU/cpuset/cpuacct are available. Review each unsupported controller and task profile before changing scheduling; successful process cleanup alone is not full cgroup acceptance. |
| GPU memory accounting | Three waits for `bpf.progs_loaded` | The graphics-stats GPU-memory worker still waits for eBPF. Do not set a fake readiness property; inspect this consumer separately from the already ported GPU-work collector. |
| IMS video | `lib-imsvt.so` load chain cannot find `vendor.qti.hardware.camera.device@1.0.so` | Review system_ext namespace/ABI and actual library inventory. This does not by itself establish whether voice IMS works. |
| Fingerprint extensions | Two service-manager denials for navigation/test extensions | Both resolve to the default hwservice type. Check whether these optional extensions exist and are needed before adding labels/permissions; not proof that ordinary fingerprint authentication fails. |
| Audio | Qualcomm performance-lock failures, an ION ioctl error, DSP payload warnings and Dolby parameter-property access warnings | Retest speaker/headset/call paths and inspect dependencies; this log alone does not establish Dolby operation. Tas2560 register traces are not all transaction failures. |
| Init / legacy vendor | Rejected unexported property triggers, duplicate cnd/dpmQmiMgr/ipacm service definitions, top-level data directory permission failures and failed module-loader commands | Inventory old stock init actions and their actual hardware purpose. Avoid importing broad permissions or blindly starting obsolete services. |
| Filesystem / verity | Repeated unknown `verify` flag and dm device-status probes | Audit the full packaged fstab, including system entries; userdata formatting does not fix these obsolete flags. |
| First-start / offline noise | GApps resolver errors, flattened-APEX backing-file warnings and first-run package scanning | Reassess after networking and setup complete. These messages alone do not justify removing GApps or altering certificate policy. |

The log contains no `FATAL EXCEPTION`, native `Fatal signal`, kernel panic or
kernel Oops marker. That observation covers this recording only and does not
establish stability. LMKD starts and ActivityManager connects; that does not yet
prove memory-pressure behavior. Bpfloader selects the intended legacy path;
DNS, UID accounting, firewall/VPN and tethering remain hardware acceptance work.

## Validation and next build

* 22 first-boot host tests pass, including seven negative packaged Wi-Fi cases
  and the existing signing, trust-store, key persistence, boot and payload cases.
* Evaluating the actual upstream SDK33 Android.mk conditional with GNU Make
  selects no supplicant init RC before the board change and the correct AIDL RC
  afterward; that RC contains the matching service name and interface.
* Python compilation passes. No Android build or on-device Wi-Fi retest has been
  run in the assistant environment.

Rebuild target-files/otatools using the runtime build entry, inspect the new
packaged output, then run the existing-key first-boot signing wrapper. The
supplicant RC belongs to vendor, so updating only boot.img does not deliver this
fix. After installation, verify service startup, scan, WPA2 association, DHCP,
DNS and reconnect after reboot; test WPA3/hotspot independently afterward.
