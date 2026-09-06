#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
GAPPS_DIR="${TOP}/vendor/gapps"
REMOTE="https://gitlab.com/MindTheGapps/vendor_gapps.git"
BRANCH="rho"

cd "${TOP}"

if [[ -d "${GAPPS_DIR}/.git" ]]; then
    echo "Updating MindTheGapps (${BRANCH}) in vendor/gapps..."
    git -C "${GAPPS_DIR}" fetch origin "${BRANCH}"
    git -C "${GAPPS_DIR}" checkout "${BRANCH}"
    git -C "${GAPPS_DIR}" reset --hard "origin/${BRANCH}"
else
    echo "Cloning MindTheGapps Android 11 branch (${BRANCH})..."
    git clone --depth=1 --branch "${BRANCH}" "${REMOTE}" "${GAPPS_DIR}"
fi

if [[ ! -f "${GAPPS_DIR}/arm64/arm64-vendor.mk" ]]; then
    echo "ERROR: vendor/gapps/arm64/arm64-vendor.mk was not found." >&2
    exit 1
fi

echo "MindTheGapps is ready. gm_GM8_sprout.mk will include it automatically."
