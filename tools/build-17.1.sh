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
# The stock GCC wrapper has an env-python2 shebang. Prefer the interpreter
# already synced by the Android 10 manifest; never replace system Python.
GM8_PY2_DIR="$TOP/prebuilts/python/linux-x86/2.7.5/bin"
if [[ -x "$GM8_PY2_DIR/python2" ]] &&
   "$GM8_PY2_DIR/python2" -c 'import os,re,subprocess,sys; assert sys.version_info[:2] == (2,7)' >/dev/null 2>&1; then
    export PATH="$GM8_PY2_DIR:$PATH"
elif command -v python2 >/dev/null &&
     python2 -c 'import os,re,subprocess,sys; assert sys.version_info[:2] == (2,7)' >/dev/null 2>&1; then
    GM8_PY2_DIR=""
else
    echo 'A runnable Python 2.7 is required by the legacy kernel tools.' >&2
    echo 'Check prebuilts/python/linux-x86/2.7.5, or install python2 inside gm8-build as root.' >&2
    echo 'Keep python3 and the system python links unchanged.' >&2
    exit 1
fi
printf 'Legacy tool interpreter: '
python2 --version 2>&1
# Module signing must use the system Perl selected by BoardConfig, without
# Lineage's old PERL5LIB. Check the same imports used by scripts/sign-file.
if ! /usr/bin/env -u PERL5LIB /usr/bin/perl -MFileHandle -MIPC::Open2 -MGetopt::Std \
     -e 'print "Kernel signing Perl: $^V\n"'; then
    echo 'Install the complete perl package inside gm8-build as root (apt-get install -y perl).' >&2
    exit 1
fi
python3 "$SCRIPT_DIR/preflight.py" --top "$TOP"
source build/envsetup.sh
lunch lineage_GM8_sprout-userdebug
if [[ -n "$GM8_PY2_DIR" ]]; then export PATH="$GM8_PY2_DIR:$PATH"; fi
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
    target-files) m target-files-package otatools apksigner -j32 ;;
esac
echo "Build records: $RECORD"
echo 'Bring-up only: no release signing, OTA generation or hardware validation performed.'
