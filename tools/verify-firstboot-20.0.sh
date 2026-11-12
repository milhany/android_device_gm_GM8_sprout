#!/usr/bin/env bash
# Recheck retained signed outputs; no compilation, signing, keys or phone access.
set -euo pipefail
umask 077
if [[ $# -gt 1 ]]; then
    echo 'Usage: verify-firstboot-20.0.sh [existing-firstboot-output-directory]' >&2
    exit 2
fi
script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
top="$(cd "$script/../../../.." && pwd)"
parent="${GM8_FIRSTBOOT_OUTPUT_PARENT:-$HOME/android/gm8-20.0-firstboot}"
if [[ $# == 1 ]]; then
    output="$1"
else
    [[ -d "$parent" ]] || { echo "Missing first-boot output parent: $parent" >&2; exit 1; }
    # Select the newest timestamped staging folder, never fall back to an
    # older package just because the newest one is incomplete or invalid.
    latest="$(find "$parent" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' |
        LC_ALL=C sort | sed -n '/^[0-9]\{8\}T[0-9]\{6\}Z-[[:alnum:]]\{6\}$/p' | tail -n 1)"
    [[ -n "$latest" ]] || { echo "No timestamped first-boot staging directory in $parent" >&2; exit 1; }
    output="$parent/$latest"
fi
[[ -d "$output" ]] || { echo "Missing existing output directory: $output" >&2; exit 1; }
echo "Verifying retained first-boot outputs: $output"
python3 "$script/tests/firstboot_20_0_test.py"
python3 "$script/firstboot-20.0.py" verify --top "$top" --output-dir "$output"
