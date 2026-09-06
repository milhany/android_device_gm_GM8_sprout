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

# Keep Lineage-specific framework additions out of this GM product profile.
TARGET_DISABLE_LINEAGE_SDK := true

# LineageOS frameworks_base still treats org.lineageos.platform-res as a
# system resource asset even when the Lineage SDK/product profile is disabled.
# Keep only this runtime resource APK so Zygote can create the system
# AssetManager without pulling Lineage apps, branding, updater or SDK services.
PRODUCT_PACKAGES += \
    org.lineageos.platform-res

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
    ro.com.google.clientidbase=android-a1-gm-rev2 \
    ro.config.ringtone=GeneralMobile.mp3 \
    ro.config.notification_sound=hangouts_message.ogg \
    ro.config.alarm_alert=Oxygen.ogg
