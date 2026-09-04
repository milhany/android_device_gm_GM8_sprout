#
# Copyright (C) 2020-2026 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from the device configuration
$(call inherit-product, device/gm/GM8_sprout/device.mk)

# Inherit LineageOS common phone configuration
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)

# Device identifiers
PRODUCT_NAME := lineage_GM8_sprout
PRODUCT_DEVICE := GM8_sprout
PRODUCT_BRAND := GM
PRODUCT_MODEL := GM 8
PRODUCT_MANUFACTURER := General Mobile

# Device launched on Android 8.x; device.mk already inherits
# product_launched_with_o_mr1.mk.
PRODUCT_GMS_CLIENTID_BASE := android-gm

# 720x1440 panel
TARGET_BOOT_ANIMATION_RES := 720
