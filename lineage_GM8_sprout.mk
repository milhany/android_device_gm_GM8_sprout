#
# General Mobile GM 8 - LineageOS 18.1
#

$(call inherit-product, device/gm/GM8_sprout/device.mk)

PRODUCT_GMS_CLIENTID_BASE := android-a1-gm-rev2
TARGET_BOOT_ANIMATION_RES := 720

# Restore the complete Lineage phone profile, including LineageParts,
# SetupWizard, Updater, themes, SDK and the standard mobile applications.
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)

# Preserve the existing Android 11 Google Mobile Services integration.
# Do not silently produce a vanilla image when the proprietary GApps checkout
# is missing; that made previous test builds boot without GmsCore/Play Store.
ifneq ($(wildcard vendor/gapps/arm64/arm64-vendor.mk),)
$(call inherit-product, vendor/gapps/arm64/arm64-vendor.mk)
else ifneq ($(wildcard vendor/partner_gms/products/gms.mk),)
$(call inherit-product, vendor/partner_gms/products/gms.mk)
else
$(error GM8_sprout: GApps tree missing. Run device/gm/GM8_sprout/setup-gapps.sh from the Android source root before building)
endif

# Device-specific applications not supplied by the common phone profile.
PRODUCT_PACKAGES += \
    Snap \
    Contacts \
    DeskClock \
    Dialer \
    Gallery2

PRODUCT_NAME := lineage_GM8_sprout
PRODUCT_DEVICE := GM8_sprout
PRODUCT_BRAND := GM
PRODUCT_MODEL := GM 8
PRODUCT_MANUFACTURER := General Mobile
PRODUCT_CHARACTERISTICS := nosdcard

PRODUCT_BUILD_PROP_OVERRIDES += \
    PRODUCT_NAME=GM8 \
    TARGET_DEVICE=GM8_sprout
