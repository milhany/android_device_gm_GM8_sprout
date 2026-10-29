#!/usr/bin/env bash
# Select the paired experimental sources, then use the existing release builder.
# No flashing, formatting, reset, branch force-update or key generation here.
set -eo pipefail
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --inside ) ]]; then
    echo "Usage: bash $0" >&2
    exit 2
fi
if [[ "${1:-}" != --inside && "$(id -un)" != builder ]]; then
    command -v docker >/dev/null || { echo 'Expected the GM8 Docker host or builder user.' >&2; exit 1; }
    sudo docker start gm8-build >/dev/null
    exec sudo docker exec -it --user builder \
        --workdir /home/builder/android/lineage-19.1 gm8-build \
        bash device/gm/GM8_sprout/tools/build-lmkd-test-19.1.sh --inside
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
cd "$TOP"
exec bash "$SCRIPT_DIR/build-release-19.1.sh" --inside --lmkd-test
