#!/usr/bin/env bash
# Prepare a separate Android 12.1 checkout and stop at a selected build gate.
set -eo pipefail

if [[ $# -gt 1 ]]; then
    echo "Usage: $0 [check|boot|rom]" >&2
    exit 2
fi
STAGE="${1:-boot}"
case "${STAGE}" in check|boot|rom) ;; *) echo "Usage: $0 [check|boot|rom]" >&2; exit 2 ;; esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
cd "${TOP}"
if [[ ! -f build/core/version_defaults.mk ]] ||
   ! grep -Eq '^[[:space:]]*PLATFORM_SDK_VERSION[[:space:]]*:?=[[:space:]]*32[[:space:]]*$' build/core/version_defaults.mk; then
    echo "This helper requires a separate LineageOS 19.1 / SDK 32 checkout." >&2
    exit 1
fi

if [[ "${STAGE}" != check ]]; then
    if ! /usr/bin/env -u PERL5LIB /usr/bin/perl -MGetopt::Std -MIPC::Open2 -MFileHandle -e 1; then
        echo "Kernel module signing needs the container's full Perl: sudo apt install perl" >&2
        exit 1
    fi
    if [[ ! -x /sbin/depmod ]]; then
        echo "Kernel module installation needs depmod: sudo apt install kmod" >&2
        exit 1
    fi
fi

GAPPS_SHA=f75a18fd21f0ceaa73b3c2c01bdb257aff976f2f
bash device/gm/GM8_sprout/setup-gapps.sh "${GAPPS_SHA}"
python3 device/gm/GM8_sprout/tools/apply-radio-compat.py
python3 device/gm/GM8_sprout/tools/apply-wifi-keystore-compat.py
python3 device/gm/GM8_sprout/tools/apply-legacy-network-compat.py
python3 device/gm/GM8_sprout/tools/apply-processgroup-compat.py
python3 device/gm/GM8_sprout/tools/fixup-legacy-protobuf.py
python3 device/gm/GM8_sprout/tools/preflight.py

RECORD_DIR="$(dirname "${TOP}")/gm8-19.1-records/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${RECORD_DIR}"
repo manifest -r -o "${RECORD_DIR}/manifest.xml"
for PROJECT in device/gm/GM8_sprout vendor/gm/GM8_sprout kernel/gm/msm8937 vendor/gapps; do
    printf '%s ' "${PROJECT}" >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" rev-parse HEAD >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" status --short >> "${RECORD_DIR}/revisions.txt"
done
git -C frameworks/opt/telephony diff HEAD -- src/java/com/android/internal/telephony/RadioConfig.java > "${RECORD_DIR}/radio-local.patch"
git -C packages/modules/Wifi diff HEAD -- service/java/com/android/server/wifi/WifiConfigManager.java service/java/com/android/server/wifi/MacAddressUtil.java > "${RECORD_DIR}/wifi-local.patch"
for PROJECT in system/bpf system/netd system/core packages/modules/NetworkStack; do
    printf '%s ' "${PROJECT}" >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" rev-parse HEAD >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" diff HEAD > "${RECORD_DIR}/${PROJECT//\//_}-local.patch"
done
python3 device/gm/GM8_sprout/tools/fixup-legacy-protobuf.py --check --record "${RECORD_DIR}/protobuf-fixups.json"
echo "Build record: ${RECORD_DIR}"

source build/envsetup.sh
lunch lineage_GM8_sprout-userdebug
m nothing -j32
case "${STAGE}" in
    boot) m bootimage -j32 ;;
    rom) m bacon -j32 ;;
esac
