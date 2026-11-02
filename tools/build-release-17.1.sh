#!/usr/bin/env bash
# Run as builder in gm8-build. Incremental build, private signing, full A/B OTA.
set -eo pipefail
umask 077
GM8_INSTALL_MODE="${GM8_INSTALL_MODE:-clean}"
case "$GM8_INSTALL_MODE" in clean|update) ;; *) echo 'GM8_INSTALL_MODE must be clean or update.' >&2; exit 2;; esac
RESUME_DIR=""
if [[ $# -eq 2 && "$1" == --resume ]]; then
    RESUME_DIR="$2"
elif [[ $# -ne 0 ]]; then
    echo "Usage: bash $0 [--resume prepared-release-directory]" >&2
    exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$TOP"
for GM8_TOOL in repo python3 flock tee openssl; do
    command -v "$GM8_TOOL" >/dev/null || { echo "Missing $GM8_TOOL; run inside gm8-build as builder." >&2; exit 1; }
done
if [[ "${OUT_DIR:-out}" != out || -n "${OUT_DIR_COMMON_BASE:-}" ]]; then
    echo 'This workflow requires standard out/; unset OUT_DIR and OUT_DIR_COMMON_BASE.' >&2
    exit 1
fi
if [[ ! -f build/core/version_defaults.mk ]] ||
   ! grep -Eq '^[[:space:]]*PLATFORM_SDK_VERSION[[:space:]]*:?=[[:space:]]*29[[:space:]]*$' build/core/version_defaults.mk; then
    echo 'Expected the separate LineageOS 17.1 / SDK 29 checkout.' >&2
    exit 1
fi
KEY_DIR="$(dirname "$TOP")/gm8-signing/keys"
# Reuse the original release identities. Additional Q APEX/custom identities
# may be created by prepare; it never replaces an existing complete key pair.
for GM8_KEY in releasekey platform shared media networkstack; do
    for GM8_SUFFIX in pk8 x509.pem; do
        if [[ ! -f "$KEY_DIR/$GM8_KEY.$GM8_SUFFIX" || -L "$KEY_DIR/$GM8_KEY.$GM8_SUFFIX" ]]; then
            echo "Original release key missing: $KEY_DIR/$GM8_KEY.$GM8_SUFFIX; no build started." >&2
            exit 1
        fi
    done
done
# Check the signing interpreter before spending time on a ROM build.
python3 "$SCRIPT_DIR/release-17.1.py" check-python --top "$TOP"
RELEASE_ROOT="$(dirname "$TOP")/gm8-17.1-release"
mkdir -p "$RELEASE_ROOT"
exec 9>"$RELEASE_ROOT/.build.lock"
flock -n 9 || { echo 'Another GM8 17.1 release build is running.' >&2; exit 1; }
if [[ -e "$RELEASE_ROOT/latest" && ! -L "$RELEASE_ROOT/latest" ]]; then
    echo "$RELEASE_ROOT/latest must be absent or a symlink; preserving existing files." >&2
    exit 1
fi
if [[ -n "$RESUME_DIR" ]]; then
    RUN_DIR="$(realpath -e "$RESUME_DIR")"
    if [[ ! -d "$RUN_DIR" || "$(dirname "$RUN_DIR")" != "$RELEASE_ROOT" || ! -f "$RUN_DIR/release-plan.json" ]]; then
        echo 'Resume requires an existing prepared run directly inside gm8-17.1-release.' >&2
        exit 1
    fi
    echo "Resuming signing only: $RUN_DIR (no ROM build or key preparation)"
else
    RUN_DIR="$(mktemp -d "$RELEASE_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
fi
echo "Build/signing log: $RUN_DIR/build.log"
(
    trap 'echo "FAILED: release incomplete; previous latest preserved. See $RUN_DIR/build.log" >&2' ERR
    if [[ -z "$RESUME_DIR" ]]; then
        bash "$SCRIPT_DIR/build-17.1.sh" target-files
        GM8_TARGETS=(out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates/*target_files*.zip)
        if [[ ${#GM8_TARGETS[@]} -ne 1 || ! -f "${GM8_TARGETS[0]}" ]]; then
            echo 'Expected exactly one target-files ZIP; preserving all outputs for inspection.' >&2
            exit 1
        fi
        python3 "$SCRIPT_DIR/release-17.1.py" prepare --top "$TOP" \
            --target-files "${GM8_TARGETS[0]}" --key-dir "$KEY_DIR" \
            --output-dir "$RUN_DIR" --install-mode "$GM8_INSTALL_MODE"
    fi
    python3 "$SCRIPT_DIR/release-17.1.py" sign --top "$TOP" --output-dir "$RUN_DIR"
    (cd "$RUN_DIR" && sha256sum gm8-17.1-userdebug-release.zip gm8-17.1-userdebug-release-boot.img > SHA256SUMS)
    ln -s "$RUN_DIR" "$RELEASE_ROOT/.latest-$$"
    mv -Tf "$RELEASE_ROOT/.latest-$$" "$RELEASE_ROOT/latest"
    echo "SIGNED ZIP: $RELEASE_ROOT/latest/gm8-17.1-userdebug-release.zip"
    echo "BOOT IMAGE: $RELEASE_ROOT/latest/gm8-17.1-userdebug-release-boot.img"
    echo "BUILD LOG: $RUN_DIR/build.log"
) 2>&1 | tee -a "$RUN_DIR/build.log"
