#
# General Mobile GM 8 - LineageOS 17.1
#

$(call inherit-product, device/gm/GM8_sprout/device.mk)

PRODUCT_GMS_CLIENTID_BASE := android-a1-gm-rev2
# Boot animation dimensions for the GM8 18:9 panel (LineageOS Q).
TARGET_SCREEN_WIDTH := 720
TARGET_SCREEN_HEIGHT := 1440

# Restore the complete Lineage phone profile, including LineageParts,
# SetupWizard, Updater, themes, SDK and the standard mobile applications.
# The GM8 stock DAP owns the global output mix; avoid two audio processors.
TARGET_EXCLUDES_AUDIOFX := true
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)

# Initial bring-up is vanilla. Never import the Android 11/12 GApps checkout.
# Add an explicitly verified Android 10 package only after the base boots.

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
