#!/bin/bash
#
# Copyright (C) 2016 The CyanogenMod Project
# Copyright (C) 2017-2020 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

set -e

DEVICE=GM8_sprout
VENDOR=gm

# Load extract_utils and do some sanity checks
MY_DIR="${BASH_SOURCE%/*}"
if [[ ! -d "${MY_DIR}" ]]; then MY_DIR="${PWD}"; fi

ANDROID_ROOT="${MY_DIR}/../../.."

HELPER="${ANDROID_ROOT}/tools/extract-utils/extract_utils.sh"
if [ ! -f "${HELPER}" ]; then
    echo "Unable to find helper script at ${HELPER}"
    exit 1
fi
source "${HELPER}"

# Default to sanitizing the vendor folder before extraction
CLEAN_VENDOR=true

KANG=
SECTION=

while [ "${#}" -gt 0 ]; do
    case "${1}" in
        -n | --no-cleanup )
                CLEAN_VENDOR=false
                ;;
        -k | --kang )
                KANG="--kang"
                ;;
        -s | --section )
                SECTION="${2}"; shift
                CLEAN_VENDOR=false
                ;;
        * )
                SRC="${1}"
                ;;
    esac
    shift
done

if [ -z "${SRC}" ]; then
    SRC="adb"
fi

function blob_fixup() {
    case "${1}" in
    vendor/lib/libril-qc-hal-qmi.so|vendor/lib64/libril-qc-hal-qmi.so|vendor/lib/libsettings.so|vendor/lib64/libsettings.so|vendor/lib64/libwvhidl.so|vendor/lib/mediadrm/libwvdrmengine.so|vendor/lib64/mediadrm/libwvdrmengine.so)
        python3 "${MY_DIR}/tools/fixup-legacy-protobuf.py" --blob "${2}" --relative-path "${1}" --patchelf "${PATCHELF}"
        ;;
    vendor/lib/libdlbdsservice.so|vendor/lib64/libdlbdsservice.so|vendor/lib/libdlbmemoryservice.so|vendor/lib64/libdlbmemoryservice.so)
        python3 "${MY_DIR}/tools/fixup-stock-dolby.py" "${2}" --patchelf "${PATCHELF}"
        ;;
    vendor/lib/hw/camera.msm8937.so)
        sed -i "s/service.bootanim.exit/service.bootanim.zzzz/g" "${2}"
        ;;
    product/lib64/libdpmframework.so|system_ext/lib64/libdpmframework.so)
        "${PATCHELF}" --add-needed "libshim_dpmframework.so" "${2}"
        ;;
    vendor/lib/hw/gatekeeper.msm8937.so)
        "${PATCHELF}" --set-soname gatekeeper.msm8937.so "${2}"
        ;;
    vendor/lib64/hw/gatekeeper.msm8937.so)
        "${PATCHELF}" --set-soname gatekeeper.msm8937.so "${2}"
        ;;
    vendor/lib/hw/keystore.msm8937.so)
        "${PATCHELF}" --set-soname keystore.msm8937.so "${2}"
        ;;
    vendor/lib64/hw/keystore.msm8937.so)
        "${PATCHELF}" --set-soname keystore.msm8937.so "${2}"
        ;;
    esac
}

# Initialize the helper
setup_vendor "${DEVICE}" "${VENDOR}" "${ANDROID_ROOT}" false "${CLEAN_VENDOR}"

extract "${MY_DIR}/proprietary-files.txt" "${SRC}" "${KANG}" --section "${SECTION}"

"${MY_DIR}/setup-makefiles.sh"
