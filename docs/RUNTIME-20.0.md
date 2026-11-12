# GM8 SDK33 paired runtime candidate

This batch completes the planned source implementation before a full Android
build and first-boot test. It does not claim that Android 13 boots, that every
peripheral works, or that battery/performance has improved. The kernel remains
the GM8 3.18 branch; this is not the abandoned 4.19 experiment.

## Build once, with the whole stack

Inside the existing Ubuntu 22.04 `gm8-build` container, as `builder`, at the
root of `~/android/lineage-20.0`:

```sh
bash device/gm/GM8_sprout/tools/build-20.0.sh runtime
```

The entry point records the pinned manifest, prepares every source patch on
isolated file copies, and only then applies the complete result. It accepts a
pristine tree, the previously published patch prefix, or a repeat of the whole
stack. Conflicting source changes stop before live source writes. Unrelated
edits are retained. A later file-write failure rolls back completed writes;
concurrent edits that make rollback unsafe are reported, never overwritten.
No Git reset, force checkout, source sync or automatic vendor replacement runs.

The build runs predecessor installer regressions on an isolated normalized
copy, then compiles/tests final factory, native socket backend and Java routing
methods against explicit host fixtures. It runs the inherited QSEE, touch,
kernel-host-link and PowerHAL checks, validates source inputs and prepares the
existing protobuf ABI fixups. A full `target-files-package otatools -j32` build
then validates the actual Android graph, kernel/native/Java sources, policy and
packaging. Generated `KERNEL_OBJ`, installed kernel and `boot.img` are removed
before this build to force a kernel rebuild; other outputs are retained.

Host Java is selected and probed from the real checkout before creating a
source-only test fixture. Its absolute path is passed to every Java host test
through `GM8_HOST_JAVA`, including permission/snapshot/runtime and TCP parser
checks. A system-wide `java` installation or PATH entry is not required when
the checkout JDK works. A broken explicit override or missing compiler fails
with the selected path and probe error before the long test suite.

Records and the live log are under `../gm8-20.0-records/*-runtime-*/`.
The target-files output remains in the normal product packaging directory.
The final inspector reads that new archive. No keys are generated or modified,
no release signing/OTA runs, and no phone is accessed or formatted.

## Paired implementation

* Netd owns the qtaguid device FD, tagging permission table and counter writes.
  Startup checks actual active module flags and opens required proc/stat files;
  missing/unsupported access fails visibly. DNS tagging uses this same backend.
* NetworkStatsService constructs BPF maps/updaters only in the default BPF mode.
  Legacy foreground/background sets and UID purge go through private fwmark IPC
  to netd. The UID set cache changes only after a successful kernel write. A
  successful purge also removes that UID from cumulative factory snapshots.
* Counter commands require root or the exact system_server UID + SELinux peer
  context. CLAT commands have the same authentication and reserved-field/FD
  validation. Public app-facing CLAT tagging remains denied. There is no new
  public Binder permission or exported APEX API.
* Private IPC has bounded I/O timeouts and propagates connection, short-message,
  ACK and kernel errors. The paired Tethering build receives the wire header
  from a separate APEX-available header-only module; platform libnetd_client is
  not linked into the APEX.
* Software CLAT skips unavailable eBPF maps, tags the actual IPv6 raw socket,
  retains a duplicate FD under a monotonic token and untags/closes it on stop.
  The inherited legacy bandwidth rules exclude duplicate CLAT accounting.
* VPN ingress and lockdown use IPv4 + IPv6 rules with the actual allowed ingress
  ifindex. Classic xt_bpf reads IFINDEX metadata without eBPF syscalls or maps.
  Unknown interfaces fail rather than becoming wildcards. Explicit wildcard,
  loopback/system UID/ESP/RST handling follows the reviewed SDK33 BPF semantics.
  Failed rule replacement attempts both rollbacks and invalidates readiness if
  rollback cannot restore both families.
* Only `CONFIG_NETFILTER_XT_MATCH_BPF=y` is added for that classic filter. The
  eBPF loader skips objects on the selected legacy kernel without setting
  `bpf.progs_loaded`. Netd, Java map consumers, software CLAT, Tethering and GPU
  work accounting select their corresponding legacy/optional paths together.
* Tethering honors the existing GM8 overlay disabling eBPF offload without
  opening API31 maps first. GPU work energy accounting stays uninitialized on
  the legacy kernel; rendering is unchanged.
* SDK33 RadioConfig selects the existing PhoneSwitcher ALLOW_DATA path under
  the GM8 property. Default single-SIM remains unchanged; manual DSDS retains
  both modem paths. No automatic single/dual detection is introduced.
* Wi-Fi reuses/persists a valid per-network randomized MAC without KeyStore HMAC
  under the existing GM8 selector. It repairs invalid stored values, retains
  existing valid addresses and preserves default KeyStore behavior elsewhere.
* The legacy TCP-info parser validates attribute lengths, bounds and padding,
  and skips legitimately shorter 3.18 layouts. SystemUI removes its tuner view
  callback on view teardown. Current SDK33 optional charging-HAL and Trebuchet
  null-recents guards already contain the earlier fixes and need no duplicate.

## Validation boundaries

Host tests compile actual changed C++ classes and selected Java method bodies,
with Android APIs, netd services and syscalls replaced only inside test fixtures.
They cover error propagation, cache retry/purge, IPC FD transfer, IPv4/IPv6
rollback, IFINDEX bytecode, repeated/conflicting stack application, Wi-Fi MAC
persistence and single/dual modem command selection. Predecessor tests retain
their original scopes. The final full Java stats factory also exercises UID
reuse after purge against kernel-generated text fixtures. These checks do not
establish real SELinux, routing, VPN/CLAT, arithmetic or hardware operation.

Source bases reviewed: Connectivity `205270f5728b3c1fda246ec413ee39e83a73df03`,
netd `43d137e94717639b96f5020607920f734433be92`, system/core
`c0500ffe2cc283d61f1e3db1b2c979bfbd9beb8c`, system/bpf
`52121cd0ee9eb6a5624665d3cf8922f7244ef1cd`, telephony
`4d7a7cb98c2356fcbc0eb24f44b5d717ff01fe7e`, Wi-Fi
`043cdd377acda29796c9b1ddf42db9db7c929b02`, and AOSP NetworkStack/iptables
`android-13.0.0_r75`. Each actual build records its current manifest, affected
source SHA256 hashes and patch hashes. Changed source context is checked rather
than trusting a branch name alone.

After compilation, inspect the new packaged images before planning a first
boot. Userdata remains explicitly unencrypted F2FS bring-up: FBE, encrypted
data migration and an Android-version downgrade without data loss are not
implemented. Hardware acceptance must include DNS/Wi-Fi/mobile data, UID
stats, VPN + lockdown, IPv6-only CLAT, hotspot, radio/DSDS, camera/audio/Dolby,
GNSS/sensors/fingerprint, suspend/wake, charging and idle battery measurement.
Thermal HAL still reports sensors without its own mitigation policy; the
existing kernel/firmware protection must be checked on hardware. No battery
life or thermal improvement is claimed from successful compilation.

The full runtime candidate subsequently compiled on the build host. See
[FIRSTBOOT-20.0.md](FIRSTBOOT-20.0.md) for the existing-target-files signing and
first-boot package workflow; no additional source build is required for it.
