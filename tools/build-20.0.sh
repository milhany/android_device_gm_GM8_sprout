#!/usr/bin/env bash
# SDK33 audit, build graph and unsigned target-files compilation checkpoints.
set -euo pipefail
stage="${1:-audit}"
case "$stage" in audit|configure|compile|network-stats|network-firewall|network-policy|network-sockets) ;; *) echo 'Usage: build-20.0.sh [audit|configure|compile|network-stats|network-firewall|network-policy|network-sockets]' >&2; exit 2;; esac
script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
top="$(cd "$script/../../../.." && pwd)"
cd "$top"
if ! grep -Eq '^[[:space:]]*PLATFORM_SDK_VERSION[[:space:]]*:?=[[:space:]]*33[[:space:]]*$' build/core/version_defaults.mk; then
    echo 'Expected the separate LineageOS 20 / SDK33 checkout.' >&2
    exit 1
fi
record="$(dirname "$top")/gm8-20.0-records/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$record"
repo manifest -r -o "$record/manifest.xml"
if [[ "$stage" != audit ]]; then
    # This is an SDK33 source port, separate from the inherited SDK32 helpers.
    python3 "$script/apply-processgroup-20.0.py" --top "$top"
    python3 "$script/apply-network-stats-20.0.py" --top "$top"
    python3 "$script/apply-firewall-20.0.py" --top "$top"
    python3 "$script/apply-network-policy-20.0.py" --top "$top"
    python3 "$script/apply-socket-20.0.py" --top "$top"
fi
python3 "$script/preflight-20.0.py" --top "$top" --output "$record/source-audit.json"
python3 "$script/tests/kernel_host_link_test.py" --kernel "$top/kernel/gm/msm8937"
python3 "$script/tests/ft8006_gesture_test.py" --kernel "$top/kernel/gm/msm8937"
python3 "$script/tests/qsee_wait_test.py" --source "$top/kernel/gm/msm8937/drivers/misc/qseecom.c"
python3 "$script/tests/power_policy_test.py"
echo "Source checkpoint: $record/source-audit.json"
if [[ "$stage" != audit ]]; then
    python3 "$script/tests/processgroup_20_0_test.py" --source "$top/system/core/libprocessgroup/processgroup.cpp"
    python3 "$script/tests/network_stats_20_0_test.py" --source "$top/packages/modules/Connectivity/service-t/jni/com_android_server_net_NetworkStatsService.cpp" --kernel "$top/kernel/gm/msm8937/net/netfilter/xt_qtaguid.c"
    python3 "$script/tests/firewall_20_0_test.py" --top "$top"
    python3 "$script/tests/network_policy_20_0_test.py" --top "$top"
    python3 "$script/tests/socket_20_0_test.py" --top "$top"
    # ELF isolation is version-independent; the source snapshot ABI, SONAMEs
    # and stock blob hashes remain checked. No SDK32 framework patch is run.
    python3 "$script/fixup-legacy-protobuf.py" --top "$top" --record "$record/protobuf-fixups.json"
    set +u
    source build/envsetup.sh
    lunch lineage_GM8_sprout-userdebug
    if [[ "$stage" == configure ]]; then
        m nothing -j32 2>&1 | tee "$record/configure.log"
    elif [[ "$stage" == network-sockets ]]; then
        echo "Native socket-backend compilation log: $record/network-sockets.log"
        m netd -j32 2>&1 | tee "$record/network-sockets.log"
        echo 'Native legacy socket backend compiled; Java permission routing and BPF startup remain pending.'
    elif [[ "$stage" == network-policy ]]; then
        echo "SDK33 network-policy compilation log: $record/network-policy.log"
        m netd service-connectivity -j32 2>&1 | tee "$record/network-policy.log"
        echo 'Native bandwidth policy and Java netd routing compiled; complete networking and boot acceptance remain pending.'
    elif [[ "$stage" == network-firewall ]]; then
        echo "Native UID-firewall compilation log: $record/network-firewall.log"
        m netd -j32 2>&1 | tee "$record/network-firewall.log"
        echo 'Native netd UID-firewall backend compiled; SDK33 Java routing and complete networking remain pending.'
    elif [[ "$stage" == network-stats ]]; then
        echo "Native TrafficStats compilation log: $record/network-stats.log"
        m libservice-connectivity -j32 2>&1 | tee "$record/network-stats.log"
        echo 'Native TrafficStats component compiled; complete SDK33 network compatibility is still pending.'
    else
        echo "Full compilation log: $record/compile.log"
        m target-files-package -j32 2>&1 | tee "$record/compile.log"
        echo "Target-files output directory: $top/out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates"
        echo 'Target-files is an unsigned build artifact, not an installation OTA.'
    fi
fi
if [[ "$stage" == compile ]]; then
    echo 'Build outputs were generated; no release signing, installation or hardware/battery validation was performed.'
    echo 'Do not install these bring-up outputs; runtime compatibility ports remain open.'
else
    echo 'No Android boot image, signed OTA or hardware/battery validation was produced.'
fi
echo 'SDK33 network/radio ports and processgroup/userdata runtime acceptance remain open; see docs/BRINGUP-20.0.md.'
