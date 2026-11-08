#!/usr/bin/env bash
# SDK33 source inventory and build-graph checkpoint; no boot/OTA production.
set -euo pipefail
stage="${1:-audit}"
case "$stage" in audit|configure) ;; *) echo 'Only audit/configure are ready; runtime ports are still open.' >&2; exit 2;; esac
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
python3 "$script/preflight-20.0.py" --top "$top" --output "$record/source-audit.json"
python3 "$script/tests/ft8006_gesture_test.py" --kernel "$top/kernel/gm/msm8937"
python3 "$script/tests/qsee_wait_test.py" --source "$top/kernel/gm/msm8937/drivers/misc/qseecom.c"
python3 "$script/tests/power_policy_test.py"
echo "Source checkpoint: $record/source-audit.json"
if [[ "$stage" == configure ]]; then
    # ELF isolation is version-independent; the source snapshot ABI, SONAMEs
    # and stock blob hashes remain checked. No SDK32 framework patch is run.
    python3 "$script/fixup-legacy-protobuf.py" --top "$top" --record "$record/protobuf-fixups.json"
    set +u
    source build/envsetup.sh
    lunch lineage_GM8_sprout-userdebug
    m nothing -j32 2>&1 | tee "$record/configure.log"
fi
echo 'No Android boot image, signed OTA or hardware/battery validation was produced.'
echo 'SDK33 network, radio, processgroup and runtime ports remain open; see docs/BRINGUP-20.0.md.'
