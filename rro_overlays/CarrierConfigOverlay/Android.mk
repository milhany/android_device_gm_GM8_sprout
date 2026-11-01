# SPDX-License-Identifier: Apache-2.0
# Android 10 uses Make for runtime resource overlays.
LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)
LOCAL_PACKAGE_NAME := CarrierConfigOverlay
LOCAL_MODULE_TAGS := optional
LOCAL_SDK_VERSION := current
LOCAL_VENDOR_MODULE := true
LOCAL_RRO_THEME := CarrierConfigOverlay
LOCAL_RESOURCE_DIR := $(LOCAL_PATH)/res
LOCAL_MANIFEST_FILE := AndroidManifest.xml
LOCAL_AAPT_FLAGS := --keep-raw-values
include $(BUILD_RRO_PACKAGE)
