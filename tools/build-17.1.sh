#!/usr/bin/env bash
# Run inside gm8-build as builder, in the separate Android 10 checkout.
set -eo pipefail
STAGE="${1:-check}"
case "$STAGE" in check|boot|target-files) ;; *) echo 'Usage: build-17.1.sh [check|boot|target-files]' >&2; exit 2;; esac
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$TOP"
if ! grep -Eq '^[[:space:]]*PLATFORM_SDK_VERSION[[:space:]]*:?=[[:space:]]*29[[:space:]]*$' build/core/version_defaults.mk; then
    echo 'Expected separate LineageOS 17.1 / SDK 29 checkout. Do not reuse 19.1 out/.' >&2
    exit 1
fi
python3 "$SCRIPT_DIR/preflight.py" --top "$TOP"
source build/envsetup.sh
lunch lineage_GM8_sprout-userdebug
RECORD="$(dirname "$TOP")/gm8-17.1-records/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$RECORD"
repo manifest -r -o "$RECORD/manifest.xml"
for PROJECT in device/gm/GM8_sprout vendor/gm/GM8_sprout kernel/gm/msm8937; do
    printf '%s ' "$PROJECT" >> "$RECORD/revisions.txt"
    git -C "$PROJECT" rev-parse HEAD >> "$RECORD/revisions.txt"
    git -C "$PROJECT" status --short >> "$RECORD/revisions.txt"
done
m nothing -j32
case "$STAGE" in
    boot) m bootimage GM8Dolby -j32 ;;
    target-files) m target-files-package otatools -j32 ;;
esac
echo "Build records: $RECORD"
echo 'Bring-up only: no release signing, OTA generation or hardware validation performed.'
