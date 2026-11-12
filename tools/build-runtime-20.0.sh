#!/usr/bin/env bash
# One full SDK33 runtime-candidate build; never uses inherited SDK32 patch helpers.
set -euo pipefail
script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
top="$(cd "$script/../../../.." && pwd)"
cd "$top"
command -v repo >/dev/null || { echo 'Run as builder inside the gm8-build container (repo is missing).' >&2; exit 1; }
[[ "${OUT_DIR:-out}" == out ]] || { echo 'This guarded kernel rebuild expects OUT_DIR=out.' >&2; exit 1; }
record="$(dirname "$top")/gm8-20.0-records/$(date -u +%Y%m%dT%H%M%SZ)-runtime-$$"
mkdir -p "$record"
exec > >(tee "$record/runtime-build.log") 2>&1
echo "Full runtime candidate build log: $record/runtime-build.log"
repo manifest -r -o "$record/manifest.xml"
python3 "$script/apply-runtime-stack-20.0.py" --top "$top" --record "$record/runtime-stack.json"
python3 "$script/preflight-20.0.py" --top "$top" --output "$record/source-audit.json"
python3 "$script/check-runtime-20.0.py" --top "$top"
python3 "$script/tests/kernel_host_link_test.py" --kernel "$top/kernel/gm/msm8937"
python3 "$script/tests/ft8006_gesture_test.py" --kernel "$top/kernel/gm/msm8937"
python3 "$script/tests/qsee_wait_test.py" --source "$top/kernel/gm/msm8937/drivers/misc/qseecom.c"
python3 "$script/tests/power_policy_test.py"
python3 "$script/fixup-legacy-protobuf.py" --top "$top" --record "$record/protobuf-fixups.json"
set +u
source build/envsetup.sh
lunch lineage_GM8_sprout-userdebug
set -u
# Remove only generated GM8 kernel products, with no symlink traversal.
python3 - "$top" <<'PY'
from pathlib import Path
import shutil,sys
top=Path(sys.argv[1])
paths=['out/target/product/GM8_sprout/obj/KERNEL_OBJ',
       'out/target/product/GM8_sprout/kernel','out/target/product/GM8_sprout/boot.img']
for name in paths:
    path=top/name
    if any(parent.is_symlink() for parent in [path,*path.parents] if parent!=top and top in parent.parents):
        raise SystemExit('Refusing to clean a symlinked output: '+str(path))
for name in paths:
    path=top/name
    if path.is_dir():shutil.rmtree(path)
    elif path.exists():path.unlink()
print('Removed generated GM8 kernel outputs; source trees and other build outputs retained.')
PY
set +u
m target-files-package otatools -j32
set -u
python3 "$script/inspect-target-files-20.0.py" --top "$top" --output "$record/target-files-inspection.json"
echo "Full build completed. Records: $record"
echo "Target-files: $top/out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates"
echo 'Unsigned userdebug source candidate. No OTA/signing/installation or hardware acceptance was performed.'
echo 'Next checkpoint: inspect the new packaged outputs and plan the first boot; do not install older bring-up artifacts.'
