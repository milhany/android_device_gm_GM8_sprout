#!/usr/bin/env bash
# Package an existing SDK33 userdebug build; no source build or phone operation.
set -euo pipefail
umask 077
if [[ $# != 1 ]]; then
    echo 'Usage: make-firstboot-20.0.sh /absolute/path/to/target-files.zip' >&2
    exit 2
fi
script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
top="$(cd "$script/../../../.." && pwd)"
target="$1"
keys="${GM8_SIGNING_KEY_DIR:-$HOME/android/gm8-signing/keys}"
parent="${GM8_FIRSTBOOT_OUTPUT_PARENT:-$HOME/android/gm8-20.0-firstboot}"
[[ -f "$target" ]] || { echo "Target-files missing: $target" >&2; exit 1; }
[[ -d "$keys" ]] || { echo "Existing key directory missing: $keys; no keys were created." >&2; exit 1; }
python3 "$script/tests/firstboot_20_0_test.py"
mkdir -p "$parent"
output="$(mktemp -d "$parent/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
echo "First-boot package staging: $output"
python3 "$script/firstboot-20.0.py" package --top "$top" --target-files "$target" \
    --key-dir "$keys" --output-dir "$output"
echo "Verified package and report directory: $output"
