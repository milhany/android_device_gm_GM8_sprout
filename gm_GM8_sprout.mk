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

# Keep the normal Lineage product profile disabled so the user-facing
# Lineage application, updater, setup wizard and branding stack stay out.
TARGET_DISABLE_LINEAGE_SDK := true

# Minimal Lineage framework runtime required by the LineageOS 18.1
# frameworks_base we are building on top of.  Do not advertise the optional
# Lineage SDK feature XMLs here; that keeps LineageSystemServer from starting
# optional Lineage services while still providing the resource package,
# framework jar and direct-boot settings provider used by framework/SystemUI.
PRODUCT_PACKAGES += \
    org.lineageos.platform-res \
    org.lineageos.platform \
    LineageSettingsProvider

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
    ro.com.google.clientidbase=android-a1-gm-rev2 \
    ro.config.ringtone=GeneralMobile.mp3 \
    ro.config.notification_sound=hangouts_message.ogg \
    ro.config.alarm_alert=Oxygen.ogg
