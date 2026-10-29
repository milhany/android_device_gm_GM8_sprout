#!/usr/bin/env bash
# Called by build-release while holding its existing build lock.
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
cd "$TOP"
for PROJECT in device/gm/GM8_sprout kernel/gm/msm8937; do
    if ! git -C "$PROJECT" diff --quiet || ! git -C "$PROJECT" diff --cached --quiet; then
        echo "Tracked local edits in $PROJECT; preserve/commit them before selecting this candidate." >&2
        git -C "$PROJECT" status --short --untracked-files=no >&2
        exit 1
    fi
done
KERNEL_SHA=496ace2d356d154ec0ff6ea6d8bb91ce8b8ece20
VENDOR_SHA=74d9accadb684a30bae2339c6a97bf5feb87028e
# Fetch both before switching either. No dependence on a remote named origin.
git -C kernel/gm/msm8937 fetch --no-tags \
    https://github.com/milhany/android_kernel_gm_msm8937.git "$KERNEL_SHA"
git -C vendor/gm/GM8_sprout fetch --no-tags \
    https://github.com/milhany/proprietary_vendor_gm_GM8_sprout.git "$VENDOR_SHA"
RECORD="$(dirname "$TOP")/gm8-lmkd-selection-$(date -u +%Y%m%dT%H%M%SZ)-$$.txt"
for PROJECT in device/gm/GM8_sprout vendor/gm/GM8_sprout kernel/gm/msm8937; do
    printf '%s ' "$PROJECT" >> "$RECORD"
    git -C "$PROJECT" rev-parse HEAD >> "$RECORD"
done
# Protobuf preparation intentionally rewrites tracked vendor ELFs. Preserve
# non-overlapping edits and their index state; never reset or stash them.
python3 "$SCRIPT_DIR/switch-vendor-preserving-edits.py" \
    --repo vendor/gm/GM8_sprout --ref "$VENDOR_SHA" --record-dir "${RECORD%.txt}.vendor"
git -C kernel/gm/msm8937 switch --detach "$KERNEL_SHA"
python3 "$SCRIPT_DIR/check-lmkd-compat.py" --top "$TOP"
echo "Previous revisions: $RECORD"
