#!/usr/bin/env bash
# One entry point on ilhan@ubuntu or builder@gm8-build. No sync or flashing.
set -eo pipefail

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --inside ) ]]; then
    echo "Usage: bash $0" >&2
    exit 2
fi
if [[ "${1:-}" != --inside && "$(id -un)" != builder ]]; then
    command -v docker >/dev/null || { echo 'Run on the Docker host or as builder in gm8-build.' >&2; exit 1; }
    sudo docker start gm8-build >/dev/null
    exec sudo docker exec -it --user builder \
        --workdir /home/builder/android/lineage-19.1 gm8-build \
        bash device/gm/GM8_sprout/tools/build-release-19.1.sh --inside
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
cd "$TOP"
for GM8_TOOL in repo python3 flock tee openssl; do
    command -v "$GM8_TOOL" >/dev/null || { echo "Missing $GM8_TOOL in gm8-build; no outputs cleaned." >&2; exit 1; }
done
if [[ "${OUT_DIR:-out}" != out || -n "${OUT_DIR_COMMON_BASE:-}" ]]; then
    echo 'This workflow requires the standard out/ directory; unset OUT_DIR and OUT_DIR_COMMON_BASE.' >&2
    exit 1
fi
if [[ ! -f build/core/version_defaults.mk ]] ||
   ! grep -Eq '^[[:space:]]*PLATFORM_SDK_VERSION[[:space:]]*:?=[[:space:]]*32[[:space:]]*$' build/core/version_defaults.mk; then
    echo 'Expected LineageOS 19.1 / SDK 32; no outputs cleaned.' >&2
    exit 1
fi
KEY_DIR="$(dirname "$TOP")/gm8-signing/keys"
if [[ ! -f "$KEY_DIR/releasekey.pk8" || ! -f "$KEY_DIR/releasekey.x509.pem" ]]; then
    echo "Original release keys missing: $KEY_DIR; no keys generated and no outputs cleaned." >&2
    exit 1
fi
RELEASE_ROOT="$(dirname "$TOP")/gm8-release"
mkdir -p "$RELEASE_ROOT"
exec 9>"$RELEASE_ROOT/.build.lock"
flock -n 9 || { echo 'Another GM8 release build is already running.' >&2; exit 1; }
if [[ -e "$RELEASE_ROOT/latest" && ! -L "$RELEASE_ROOT/latest" ]]; then
    echo "$RELEASE_ROOT/latest must be absent or a symlink; preserving existing files." >&2
    exit 1
fi
RUN_DIR="$(mktemp -d "$RELEASE_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
echo "Build log: $RUN_DIR/build.log"
(
    trap 'echo "FAILED: release incomplete; previous latest release preserved. See $RUN_DIR/build.log" >&2' ERR
    python3 "$SCRIPT_DIR/clean-kernel-19.1.py" --top "$TOP"
    bash "$SCRIPT_DIR/build-19.1.sh" target-files user
    GM8_TARGETS=(out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates/*target_files*.zip)
    if [[ ${#GM8_TARGETS[@]} -ne 1 || ! -f "${GM8_TARGETS[0]}" ]]; then
        echo 'Expected exactly one target-files archive from this build.' >&2
        exit 1
    fi
    python3 "$SCRIPT_DIR/release-19.1.py" prepare --top "$TOP" \
        --target-files "${GM8_TARGETS[0]}" --key-dir "$KEY_DIR" \
        --output-dir "$RUN_DIR" --install-mode update
    python3 "$SCRIPT_DIR/release-19.1.py" sign --top "$TOP" --output-dir "$RUN_DIR"
    (cd "$RUN_DIR" && sha256sum gm8-19.1-user-release.zip gm8-19.1-user-release-boot.img > SHA256SUMS)
    ln -s "$RUN_DIR" "$RELEASE_ROOT/.latest-$$"
    mv -Tf "$RELEASE_ROOT/.latest-$$" "$RELEASE_ROOT/latest"
    echo "SIGNED ZIP: $RELEASE_ROOT/latest/gm8-19.1-user-release.zip"
    echo "BOOT IMAGE: $RELEASE_ROOT/latest/gm8-19.1-user-release-boot.img"
    echo "BUILD LOG: $RUN_DIR/build.log"
) 2>&1 | tee "$RUN_DIR/build.log"
