#!/system/bin/sh
# Run on the phone with adb shell sh, not on the build host.
# Read-only: no root request, service restart, property changes or data deletion.
# Preserve errors so an absent path is distinguishable from access denial.
exec 2>&1

section() { printf '\n== %s ==\n' "$1"; }
show_file() {
    printf '\n%s\n' "$1"
    cat "$1"
}

section 'Capture identity and access'
date
id
getenforce
cat /proc/uptime
for prop in ro.build.display.id ro.build.date ro.vendor.build.date \
    ro.boot.slot_suffix ro.debuggable ro.boot.hardware.sku ro.boot.hwc \
    ro.boot.product.device ro.boot.product.name gsm.version.baseband \
    persist.radio.multisim.config vendor.gm8.multisim.config \
    persist.vendor.gm8.multisim_override vold.post_fs_data_done \
    init.svc.qcom-c_core-sh init.svc.vendor.qcrild init.svc.vendor.qcrild2 \
    vendor.gm8.fingerprint.sensor init.svc.vendor.gm8-fingerprint-init \
    init.svc.vendor.fps_hal init.svc.fpc_fps_hal \
    init.svc.swfingerprint-hal-1.0 init.svc.gnss_service init.svc.loc_launcher; do
    printf '%s=%s\n' "$prop" "$(getprop "$prop")"
done

section 'Installed source/configuration hashes'
sha256sum /vendor/bin/init.qcom.class_core.sh /vendor/etc/gps.conf \
    /vendor/lib64/hw/fingerprint.msm8937.so /vendor/etc/vintf/manifest.xml \
    /vendor/etc/mixer_paths_mtp.xml

section 'Radio services and selected subscriptions'
for setting in multi_sim_data_call multi_sim_voice_call multi_sim_sms; do
    printf '%s=' "$setting"
    settings get global "$setting"
done
ps -AZ | grep -E 'qcrild|rild|qcrilmsgtunnel|ims'
grep -E 'vendor.qti.hardware.radio|IQcRilAudio|IQtiOemHook|IImsRadio|IQtiRadio|<instance>' \
    /vendor/etc/vintf/manifest.xml
dumpsys audio

section 'Firmware variant sources'
ls -ldZ /mnt/vendor/persist /mnt/vendor/persist/speccfg /persist
for path in /vendor/firmware_mnt/verinfo/ver_info.txt \
    /mnt/vendor/persist/gm8_variant \
    /mnt/vendor/persist/speccfg/vendor_ro.prop \
    /mnt/vendor/persist/speccfg/vendor_persist.prop \
    /mnt/vendor/persist/speccfg/spec \
    /mnt/vendor/persist/speccfg/devicetype; do
    show_file "$path"
done

section 'Fingerprint device, storage and services'
show_file /proc/fp_info
ls -lZ /dev/sunwave_fp /dev/fpc*
ls -lZ /sys/bus/platform/drivers/fpc1020
ls -lZ /sys/bus/platform/drivers/fpc1020/*/irq
ls -ldZ /data/vendor_de /data/vendor_de/sunwave /data/vendor_de/0/fpdata /data/fpc
dumpsys fingerprint
ps -AZ | grep -E 'finger|fps|qcom|gnss|loc_launcher|xtra'

section 'CPU frequency nodes'
show_file /sys/devices/system/cpu/online
ls -l /sys/devices/system/cpu/cpufreq
for cpu in 0 4; do
    ls -ldZ "/sys/devices/system/cpu/cpu$cpu/cpufreq"
    ls -lZ "/sys/devices/system/cpu/cpu$cpu/cpufreq/scaling_min_freq"
done

section 'GNSS configuration and active request'
printf '%s\n' 'Keep the GNSS test app active during capture; a position fix is not required.'
show_file /vendor/etc/gps.conf
dumpsys location

section 'Connectivity and DNS configuration'
dumpsys connectivity
dumpsys dnsresolver

section 'Battery and LED nodes'
dumpsys battery
ls -lZ /sys/class/leds
for led in red green blue; do
    show_file "/sys/class/leds/$led/brightness"
done

section 'Kernel ring buffer (may require rooted debugging)'
dmesg

section 'End of hardware capture'
