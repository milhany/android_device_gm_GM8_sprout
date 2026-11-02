# SPDX-License-Identifier: Apache-2.0
# GM8 3 GiB / 720x1440: values observed in the supplied stock Pie report.
# These are ART heap/GC targets, not reserved memory or LMK kill thresholds.
# Preserve the stock growth/max limits so large applications retain room.
PRODUCT_PROPERTY_OVERRIDES += \
    dalvik.vm.heapstartsize=16m \
    dalvik.vm.heapgrowthlimit=192m \
    dalvik.vm.heapsize=512m \
    dalvik.vm.heaptargetutilization=0.75 \
    dalvik.vm.heapminfree=4m \
    dalvik.vm.heapmaxfree=8m
