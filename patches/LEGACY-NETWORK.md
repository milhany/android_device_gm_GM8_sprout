# Android 12.1 network compatibility for GM8 kernel 3.18

The failed boot captured on 2026-10-19 reached post-fs-data, then bpfloader
failed to create tether_error_map with ENOSYS (-38). Init rebooted with
`bpfloader-failed`. The stock kernel has CONFIG_NETFILTER_XT_MATCH_QTAGUID=y
but no Android 12 eBPF syscall/maps ABI. Enabling CONFIG_BPF_SYSCALL alone
would not supply the missing Android networking hooks.

The two patches are copied unchanged, including author attribution, from
[8890q/patches at 9ce066611ad946435041cee7d5a45461e4dea398](https://github.com/8890q/patches/tree/9ce066611ad946435041cee7d5a45461e4dea398):

- system_bpf/0001-Ignore-bpf-errors-for-4.9-kernels.patch
- system_netd/0001-Add-back-support-for-non-bpf-trafic-monitoring.patch

They restore Android 11-style xt_qtaguid socket tagging, iptables accounting,
bandwidth/data-saver rules and owner firewall paths. Both default to the
ordinary eBPF implementation unless ro.kernel.ebpf.supported=false. Failures
on the enabled eBPF path still fail boot; reboot_on_failure is retained.
Existing Android 12.1 NetworkStatsFactory/JNI still support /proc/net/xt_qtaguid
and choose that path when the BPF stats map is absent. Existing platform
SELinux rules permit netd's qtaguid access. GM8 adds a system-owned, boolean
property label readable only by bpfloader/netd rather than relying on an
unreadable default_prop. SELinux remains enforcing.

GM8TetheringOverlay disables the module's BPF offload resource. The target is
the Tethering APK in com.android.tethering, and the resource is explicitly
overlayable under the TetheringConfig/product policy. Software tethering
remains available; a persisted DeviceConfig override can supersede this RRO.

Run tools/apply-legacy-network-compat.py from the device tree, or use
tools/build-19.1.sh which applies/checks both patches. The helper validates
both projects before applying either, preserves unrelated edits and refuses
source drift. Preflight requires both patches and built-in qtaguid/quota2/
policy/mark support. Build records include the actual local network diffs.

Limits: this is a legacy compatibility path, not an eBPF backport or a claim
of Android 12 network feature parity. UID ingress-interface filtering explicitly
returns EOPNOTSUPP on this path; VPN isolation/lockdown, restricted networking,
data saver, per-UID counters, Wi-Fi, both SIMs and tethering require device
tests before release. Restored C++ tests exercise both accounting modes but
must be compiled/run in the Android build environment. Host patch checks
alone do not prove that the ROM boots or that all networking behavior works.
