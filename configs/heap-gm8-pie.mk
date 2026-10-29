# GM8 3 GiB stock-profile experiment, from the supplied Pie runtime properties.
# These are ART heap/GC targets, not physical RAM reservations or a memory cap
# for the whole process. Denser heaps may increase GC work; validate on hardware.
PRODUCT_VENDOR_PROPERTIES += \
    dalvik.vm.heapstartsize=16m \
    dalvik.vm.heapgrowthlimit=192m \
    dalvik.vm.heapsize=512m \
    dalvik.vm.heaptargetutilization=0.75 \
    dalvik.vm.heapminfree=4m \
    dalvik.vm.heapmaxfree=8m
