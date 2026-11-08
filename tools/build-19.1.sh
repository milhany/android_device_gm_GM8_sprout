#!/usr/bin/env bash
# Prepare a separate Android 12.1 checkout and stop at a selected build gate.
set -eo pipefail

if [[ $# -gt 2 ]]; then
    echo "Usage: $0 [check|boot|rom|target-files] [userdebug|user]" >&2
    exit 2
fi
STAGE="${1:-boot}"
case "${STAGE}" in
    check|boot|rom|target-files) ;;
    *) echo "Usage: $0 [check|boot|rom|target-files] [userdebug|user]" >&2; exit 2 ;;
esac
BUILD_VARIANT="${2:-userdebug}"
case "${BUILD_VARIANT}" in
    userdebug|user) ;;
    *) echo "Build variant must be userdebug or user." >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
cd "${TOP}"
if [[ ! -f build/core/version_defaults.mk ]] ||
   ! grep -Eq '^[[:space:]]*PLATFORM_SDK_VERSION[[:space:]]*:?=[[:space:]]*32[[:space:]]*$' build/core/version_defaults.mk; then
    echo "This helper requires a separate LineageOS 19.1 / SDK 32 checkout." >&2
    exit 1
fi

if [[ "${OUT_DIR:-out}" != out || -n "${OUT_DIR_COMMON_BASE:-}" ]]; then
    echo "This fresh-kernel workflow requires standard out/; unset OUT_DIR and OUT_DIR_COMMON_BASE." >&2
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
python3 device/gm/GM8_sprout/tools/apply-runtime-compat.py
python3 device/gm/GM8_sprout/tools/fixup-legacy-protobuf.py
python3 "$SCRIPT_DIR/tests/ft8006_gesture_test.py" --kernel "$TOP/kernel/gm/msm8937"
python3 "$SCRIPT_DIR/tests/qsee_wait_test.py" --source "$TOP/kernel/gm/msm8937/drivers/misc/qseecom.c"
python3 "$SCRIPT_DIR/tests/power_policy_test.py"
python3 device/gm/GM8_sprout/tools/preflight.py

RECORD_DIR="$(dirname "${TOP}")/gm8-19.1-records/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${RECORD_DIR}"
printf 'stage=%s\nvariant=%s\n' "${STAGE}" "${BUILD_VARIANT}" > "${RECORD_DIR}/build-selection.txt"
sha256sum kernel/gm/msm8937/drivers/misc/qseecom.c \
    kernel/gm/msm8937/drivers/input/touchscreen/ft8006/focaltech_core.c \
    kernel/gm/msm8937/drivers/input/touchscreen/ft8006/focaltech_core.h \
    kernel/gm/msm8937/drivers/input/touchscreen/ft8006/focaltech_gesture.c \
    device/gm/GM8_sprout/tools/tests/ft8006_gesture_test.py \
    device/gm/GM8_sprout/tools/tests/qsee_wait_test.py \
    device/gm/GM8_sprout/tools/tests/qsee_host.c \
    device/gm/GM8_sprout/configs/powerhint.json \
    device/gm/GM8_sprout/power-libperfmgr/hidl/Power.cpp \
    vendor/gm/GM8_sprout/proprietary/vendor/etc/init/android.hardware.gnss@2.0-service-qti.rc \
    > "${RECORD_DIR}/stability-inputs.sha256"
repo manifest -r -o "${RECORD_DIR}/manifest.xml"
for PROJECT in device/gm/GM8_sprout vendor/gm/GM8_sprout kernel/gm/msm8937 vendor/gapps; do
    printf '%s ' "${PROJECT}" >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" rev-parse HEAD >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" status --short >> "${RECORD_DIR}/revisions.txt"
done
git -C frameworks/opt/telephony diff HEAD -- src/java/com/android/internal/telephony/RadioConfig.java > "${RECORD_DIR}/radio-local.patch"
git -C packages/modules/Wifi diff HEAD -- service/java/com/android/server/wifi/WifiConfigManager.java service/java/com/android/server/wifi/MacAddressUtil.java > "${RECORD_DIR}/wifi-local.patch"
for PROJECT in frameworks/base lineage-sdk packages/apps/Trebuchet; do
    printf '%s ' "${PROJECT}" >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" rev-parse HEAD >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" diff HEAD > "${RECORD_DIR}/${PROJECT//\//_}-local.patch"
done
for PROJECT in system/bpf system/netd system/core packages/modules/NetworkStack; do
    printf '%s ' "${PROJECT}" >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" rev-parse HEAD >> "${RECORD_DIR}/revisions.txt"
    git -C "${PROJECT}" diff HEAD > "${RECORD_DIR}/${PROJECT//\//_}-local.patch"
done
python3 device/gm/GM8_sprout/tools/fixup-legacy-protobuf.py --check --record "${RECORD_DIR}/protobuf-fixups.json"
echo "Build record: ${RECORD_DIR}"

source build/envsetup.sh
lunch "lineage_GM8_sprout-${BUILD_VARIANT}"
m nothing -j32
if [[ "${STAGE}" != check ]]; then
    # Rebuild kernel/modules together after source and build-generation gates.
    # Keep Android outputs, signing identities and previous release packages.
    rm -rf -- "$TOP/out/target/product/GM8_sprout/obj/KERNEL_OBJ"
    rm -f -- "$TOP/out/target/product/GM8_sprout/kernel" \
        "$TOP/out/target/product/GM8_sprout/boot.img"
    m bootimage -j32
fi
case "${STAGE}" in
    boot) : ;;
    rom) m bacon -j32 ;;
    target-files)
        m target-files-package otatools -j32
        python3 device/gm/GM8_sprout/tools/inspect-release-19.1.py \
            --product-out "$(get_build_var PRODUCT_OUT)" \
            --variant "${BUILD_VARIANT}" --output "${RECORD_DIR}/signing-inputs.txt"
        echo "Target-files preparation only: sign and plan key migration before installation."
        ;;
esac
