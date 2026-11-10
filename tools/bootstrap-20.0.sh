#!/usr/bin/env bash
# Source checkout only. Run as builder in the existing gm8-build container.
set -euo pipefail
umask 077
if [[ $# != 1 || ! -f "$1" ]]; then
    echo 'Usage: bash bootstrap-20.0.sh path/to/reviewed-local-manifest.xml' >&2
    exit 2
fi
manifest="$(realpath "$1")"
android_parent="${GM8_ANDROID_PARENT:-$HOME/android}"
target="$android_parent/lineage-20.0"
for tool in repo git git-lfs python3 flock; do
    command -v "$tool" >/dev/null || { echo "Missing $tool; run in gm8-build as builder." >&2; exit 1; }
done
mkdir -p "$android_parent"
exec 9>"$android_parent/.gm8-lineage20-source.lock"
flock -n 9 || { echo 'Another GM8 20.0 source sync is running.' >&2; exit 1; }
python3 - "$target" "$manifest" <<'PY'
import os
from pathlib import Path
import re
import shutil
import sys
import xml.etree.ElementTree as ET
target, manifest = map(Path, sys.argv[1:])
root = ET.parse(manifest).getroot()
expected = {
    'device/gm/GM8_sprout': ('milhany/android_device_gm_GM8_sprout', 'lineage-20.0'),
    'vendor/gm/GM8_sprout': ('milhany/proprietary_vendor_gm_GM8_sprout', 'lineage-20.0'),
    'kernel/gm/msm8937': ('milhany/android_kernel_gm_msm8937', 'lineage-20.0'),
    'vendor/gapps': ('MindTheGapps/vendor_gapps', 'tau'),
}
projects = root.findall('project')
actual = {p.get('path'): (p.get('name'), p.get('revision')) for p in projects}
if actual != expected or len(projects) != 4:
    raise SystemExit('Unexpected GM8 Android 13 local manifest; no sync started.')
remotes = {p.get('name'): p.get('fetch') for p in root.findall('remote')}
if remotes != {'gm8-github': 'https://github.com/', 'gm8-gitlab': 'https://gitlab.com/'}:
    raise SystemExit('Unexpected source remotes; no sync started.')
if any(p.get('remote') != ('gm8-gitlab' if p.get('path') == 'vendor/gapps' else 'gm8-github') for p in projects):
    raise SystemExit('Unexpected project remote selection.')
if target.is_symlink():
    raise SystemExit('Refusing a symlink as the new source checkout.')
repo_dir = target / '.repo'
default = repo_dir / 'manifests/default.xml'
resume = default.is_file()
# The repo launcher can create only .repo/repo before an init option is
# rejected. Accept that narrow interrupted-init state, not an unknown tree.
repo_tool_only = (repo_dir.is_dir() and not repo_dir.is_symlink() and
                 {p.name for p in target.iterdir()} == {'.repo'} and
                 {p.name for p in repo_dir.iterdir()} <= {'repo'})
if target.exists() and any(target.iterdir()) and not (resume or repo_tool_only):
    raise SystemExit('Destination is nonempty without .repo; existing files preserved.')
if resume:
    setting = ET.parse(default).getroot().find('default') if default.is_file() else None
    if setting is None or setting.get('revision') not in ('lineage-20.0', 'refs/heads/lineage-20.0'):
        raise SystemExit('Existing manifest is not Lineage 20.0; checkout preserved.')
sdk = target / 'build/core/version_defaults.mk'
if sdk.exists() and not re.search(r'^\s*PLATFORM_SDK_VERSION\s*:?=\s*33\s*$', sdk.read_text(), re.M):
    raise SystemExit('Existing checkout is not SDK33; no branch transition attempted.')
minimum = int(os.environ.get('GM8_MIN_FREE_GIB', '150' if resume else '400'))
if minimum < 50:
    raise SystemExit('GM8_MIN_FREE_GIB must be at least 50.')
free = shutil.disk_usage(target if target.exists() else target.parent).free / (1024 ** 3)
print(f'Free space: {free:.1f} GiB; source/build budget guard: {minimum} GiB', flush=True)
if free < minimum:
    raise SystemExit('Insufficient working space; no existing ROM trees were deleted.')
PY
mkdir -p "$target"
cd "$target"
repo_init_args=(-u https://github.com/LineageOS/android.git -b lineage-20.0)
repo_init_help="$(repo init -h 2>&1)"
repo_native_lfs=false
if [[ "$repo_init_help" == *--git-lfs* ]]; then
    repo_init_args+=(--git-lfs)
    repo_native_lfs=true
else
    echo 'Legacy repo: LFS objects will be fetched explicitly after source sync.'
fi
repo init "${repo_init_args[@]}"
mkdir -p .repo/local_manifests
if [[ -e .repo/local_manifests/gm8.xml ]] && ! cmp -s "$manifest" .repo/local_manifests/gm8.xml; then
    echo 'Existing gm8.xml differs; preserving it. Review the local manifest before retrying.' >&2
    exit 1
fi
cp "$manifest" .repo/local_manifests/gm8.xml
set -o pipefail
repo sync -c -j8 --no-clone-bundle --fail-fast 2>&1 | tee "$android_parent/gm8-20.0-sync.log"
if [[ "$repo_native_lfs" == false ]]; then
    # repo 2.17 has no --git-lfs. Materialize only projects with LFS paths,
    # using their manifest remote; stop before audit on any transfer error.
    repo forall -e -c '
        set -eu
        gm8_lfs_paths=$(git lfs ls-files --name-only)
        if [ -n "$gm8_lfs_paths" ]; then
            echo "Fetching Git LFS objects: $REPO_PATH"
            git lfs install --local
            git lfs pull -I "" -X "" "$REPO_REMOTE"
            git lfs fsck
        fi
    '
fi
bash device/gm/GM8_sprout/tools/build-20.0.sh audit
