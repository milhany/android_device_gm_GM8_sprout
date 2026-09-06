#
# General Mobile GM 8 - Android 11 product configuration
#
# Built from the LineageOS 18.1 / AOSP Android 11 source base, while keeping
# the product profile intentionally AOSP/GM-facing instead of inheriting the
# LineageOS application, SDK, theme, updater, setup wizard and branding stack.
#

# Inherit the hardware/device configuration. device.mk already pulls the
# Android 11 AOSP full-base telephony product and the 64/32-bit architecture.
$(call inherit-product, device/gm/GM8_sprout/device.mk)

# Keep the user-facing Lineage product profile out, but retain the Lineage
# framework runtime used by the LineageOS 18.1 framework and SystemUI.
# In particular this installs the feature declarations for global actions,
# settings and hardware services.  We intentionally do not inherit
# vendor/lineage/config/common.mk, so LineageParts, Updater, LineageSetupWizard
# and Lineage branding are still excluded.
include vendor/lineage/config/lineage_sdk_common.mk

PRODUCT_PACKAGES += \
    LineageSettingsProvider

# Optional build-time Google services.  Proprietary Google binaries stay out
# of this public device tree; if a compatible GApps vendor tree is present in
# the source checkout it is baked into the ROM automatically.
ifneq ($(wildcard vendor/gapps/arm64/arm64-vendor.mk),)
$(call inherit-product, vendor/gapps/arm64/arm64-vendor.mk)
else
$(call inherit-product-if-exists, vendor/partner_gms/products/gms.mk)
endif

# General Mobile / AOSP-facing application profile.
# Lineage common_mobile is intentionally not inherited, so explicitly keep
# the stock Android application counterparts and the Launcher3-based QuickStep
# implementation that is present in this Android 11 source checkout.
PRODUCT_PACKAGES += \
    Browser2 \
    Calendar \
    Camera2 \
    Contacts \
    DeskClock \
    Dialer \
    Email \
    ExactCalculator \
    Exchange2 \
    Gallery2 \
    LatinIME \
    Messaging \
    Music \
    TrebuchetQuickStep

# Keep the home process pre-optimized like the normal mobile product profile.
PRODUCT_DEXPREOPT_SPEED_APPS += \
    TrebuchetQuickStep

# Device identity
PRODUCT_NAME := gm_GM8_sprout
PRODUCT_DEVICE := GM8_sprout
PRODUCT_BRAND := GM
PRODUCT_MODEL := GM 8
PRODUCT_MANUFACTURER := General Mobile
PRODUCT_CHARACTERISTICS := nosdcard

# Preserve the public product/device identity used by the stock firmware while
# allowing the internal lunch target to stay distinct.
PRODUCT_BUILD_PROP_OVERRIDES += \
    PRODUCT_NAME=GM8 \
    TARGET_DEVICE=GM8_sprout

# General Mobile / Android One client id used by the stock software family.
PRODUCT_SYSTEM_PROPERTIES += \
    ro.com.google.clientidbase=android-a1-gm-rev2

# full_base.mk defines the AOSP ringtone through PRODUCT_PROPERTY_OVERRIDES.
# Override it in the same property bucket so GeneralMobile wins deterministically
# on a clean first boot.
PRODUCT_PROPERTY_OVERRIDES += \
    ro.config.ringtone=GeneralMobile.mp3 \
    ro.config.notification_sound=hangouts_message.ogg \
    ro.config.alarm_alert=Oxygen.ogg
