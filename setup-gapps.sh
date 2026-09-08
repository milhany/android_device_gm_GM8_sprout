#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
GAPPS_DIR="${TOP}/vendor/gapps"
REMOTE="https://gitlab.com/MindTheGapps/vendor_gapps.git"
BRANCH="rho"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
    echo "Usage: $0 [full-40-character-MindTheGapps-commit]"
    echo "Without a commit, only a clean rho checkout can be fast-forwarded."
    exit 0
fi
[[ $# -le 1 ]] || die "Expected at most one full MindTheGapps commit SHA."

REVISION="${1:-}"
if [[ -n "${REVISION}" && ! "${REVISION}" =~ ^[0-9a-fA-F]{40}$ ]]; then
    die "Pass a full commit SHA to pin GApps, or omit it to follow ${BRANCH}."
fi
REVISION="${REVISION,,}"
[[ -f "${TOP}/build/envsetup.sh" ]] || die "Place this tree at device/gm/GM8_sprout in an Android source checkout."

if [[ -e "${GAPPS_DIR}" ]]; then
    # repo checkouts and worktrees use a .git file rather than a directory.
    [[ -e "${GAPPS_DIR}/.git" ]] || die "vendor/gapps exists but is not a Git checkout; leaving it untouched."
    [[ -z "$(git -C "${GAPPS_DIR}" status --porcelain --untracked-files=all)" ]] || \
        die "vendor/gapps has local changes; commit or move them before updating."
    case "$(git -C "${GAPPS_DIR}" remote get-url origin)" in
        https://gitlab.com/MindTheGapps/vendor_gapps.git|https://gitlab.com/MindTheGapps/vendor_gapps|git@gitlab.com:MindTheGapps/vendor_gapps.git)
            ;;
        *) die "vendor/gapps origin is not the expected MindTheGapps repository; leaving it untouched." ;;
    esac
    if [[ -z "${REVISION}" ]]; then
        CURRENT_BRANCH="$(git -C "${GAPPS_DIR}" symbolic-ref --quiet --short HEAD || true)"
        [[ "${CURRENT_BRANCH}" == "${BRANCH}" ]] || \
            die "vendor/gapps is not on ${BRANCH}; pass an explicit commit to update a pinned checkout."
    fi
else
    echo "Cloning MindTheGapps Android 11 branch (${BRANCH})..."
    git clone --depth=1 --branch "${BRANCH}" "${REMOTE}" "${GAPPS_DIR}"
fi

if [[ -n "${REVISION}" ]]; then
    git -C "${GAPPS_DIR}" fetch --depth=1 origin "${REVISION}"
    FETCHED_REVISION="$(git -C "${GAPPS_DIR}" rev-parse FETCH_HEAD)"
    [[ "${FETCHED_REVISION}" == "${REVISION,,}" ]] || die "Fetched GApps commit does not match the requested SHA."
else
    git -C "${GAPPS_DIR}" fetch origin "${BRANCH}"
    FETCHED_REVISION="$(git -C "${GAPPS_DIR}" rev-parse FETCH_HEAD)"
fi

git -C "${GAPPS_DIR}" cat-file -e "${FETCHED_REVISION}:arm64/arm64-vendor.mk" || \
    die "The fetched revision lacks arm64/arm64-vendor.mk; checkout was not changed."

if [[ -n "${REVISION}" ]]; then
    git -C "${GAPPS_DIR}" checkout --detach "${FETCHED_REVISION}"
else
    git -C "${GAPPS_DIR}" merge --ff-only "${FETCHED_REVISION}"
fi

[[ -f "${GAPPS_DIR}/arm64/arm64-vendor.mk" ]] || die "vendor/gapps/arm64/arm64-vendor.mk was not found."
echo "MindTheGapps commit: $(git -C "${GAPPS_DIR}" rev-parse HEAD)"
echo "MindTheGapps is ready. gm_GM8_sprout.mk will include it automatically."
