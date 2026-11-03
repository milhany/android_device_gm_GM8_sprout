#!/system/bin/sh
# Read-only targeted state. No subscriber IDs, keys, app lists or template data.
echo '=== Installed ROM and kernel ==='
getprop ro.build.version.sdk
getprop ro.lineage.version
getprop ro.build.type
uname -r
echo '=== ART heap and memory pressure snapshot ==='
for gm8_prop in dalvik.vm.heapstartsize dalvik.vm.heapgrowthlimit dalvik.vm.heapsize dalvik.vm.heaptargetutilization dalvik.vm.heapminfree dalvik.vm.heapmaxfree pm.dexopt.install pm.dexopt.bg-dexopt; do
    echo "$gm8_prop=$(getprop "$gm8_prop")"
done
grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree|Dirty|Writeback|SReclaimable):' /proc/meminfo
for gm8_zram in disksize comp_algorithm mm_stat; do
    echo "zram0/$gm8_zram"
    cat "/sys/block/zram0/$gm8_zram" 2>&1
done
echo '=== Running kernel controller configuration ==='
if [ -r /proc/config.gz ]; then
    zcat /proc/config.gz | grep -E '^CONFIG_(CPUSETS|MEMCG|MEMCG_SWAP|BLK_CGROUP|CFQ_GROUP_IOSCHED|ANDROID_LOW_MEMORY_KILLER|SCHED_TUNE|CGROUP_SCHEDTUNE)='
else
    echo '/proc/config.gz is not readable by this shell'
fi
echo '=== Fingerprint selector and initialized driver nodes ==='
getprop vendor.gm8.fingerprint.sensor
ls -lZ /dev/sunwave_fp 2>&1
for gm8_irq in /sys/bus/platform/drivers/fpc1020/*/irq; do
    [ -f "$gm8_irq" ] && ls -lZ "$gm8_irq"
done
echo '=== Registered vendor services ==='
getprop init.svc.fpc_fps_hal
getprop init.svc.vendor.fps_hal
getprop init.svc.swfingerprint-hal-1.0
getprop init.svc.vendor.wifi_hal_legacy
getprop init.svc.wpa_supplicant
getprop init.svc.hostapd_fst
getprop init.svc.vendor.power-hal-1-3
lshal 2>&1 | grep -E 'fingerprint|swfingerprint|dolby|hardware.perf|hardware.wifi'
echo '=== Wi-Fi driver and interface presence (no saved networks or MAC addresses) ==='
getprop wlan.driver.status
getprop wifi.interface
ls -ldZ /sys/class/net/wlan0 /sys/class/ieee80211 /dev/wcnss_ctrl /dev/wcnss_wlan /dev/socket/wifihal 2>&1
for gm8_wifi_node in ifindex operstate phy80211/index; do
    cat "/sys/class/net/wlan0/$gm8_wifi_node" 2>&1
done
echo '=== CPU frequency node ownership and values ==='
for gm8_cpu in 0 1 2 3 4 5 6 7; do
    echo "cpu$gm8_cpu online/cpufreq"
    cat "/sys/devices/system/cpu/cpu${gm8_cpu}/online" 2>&1
    readlink -f "/sys/devices/system/cpu/cpu${gm8_cpu}/cpufreq" 2>&1
    for gm8_node in related_cpus affected_cpus scaling_min_freq scaling_max_freq scaling_governor scaling_available_frequencies; do
        gm8_path="/sys/devices/system/cpu/cpu${gm8_cpu}/cpufreq/$gm8_node"
        ls -lZ "$gm8_path" 2>&1
        cat "$gm8_path" 2>&1
    done
done
echo '=== Policy directories, where provided by this kernel ==='
ls -ldZ /sys/devices/system/cpu/cpufreq/policy* 2>&1
echo '=== Power service identity and CPU hotplug state ==='
ps -AZ | grep -E 'power@1.3-service|gm8.dolby|dolby.*dms'
cat /sys/devices/system/cpu/online /sys/devices/system/cpu/offline 2>&1
ls -ldZ /sys/devices/system/cpu/cpu0/cpufreq /sys/devices/system/cpu/cpu4/cpufreq 2>&1
echo '=== Optional RPM statistics paths (presence only) ==='
ls -lZ /d/system_stats /sys/kernel/debug/system_stats /sys/kernel/debug/rpm_stats /sys/power/rpm_stats 2>&1
echo '=== Stock media performance client selection ==='
getprop ro.vendor.extension_library
ls -lZ /vendor/lib/libqti-perfd-client.so /vendor/lib64/libqti-perfd-client.so 2>&1
echo '=== RTC and FPC sysfs node presence (no fingerprint templates) ==='
ls -lZ /dev/rtc /dev/rtc0 /dev/rtc1 2>&1
for gm8_rtc in /sys/class/rtc/rtc*/name; do
    [ -f "$gm8_rtc" ] && cat "$gm8_rtc" 2>&1
done
for gm8_fpc in /sys/bus/platform/drivers/fpc1020/*; do
    [ -d "$gm8_fpc" ] || continue
    ls -ldZ "$gm8_fpc" "$gm8_fpc/irq" "$gm8_fpc/fingerdown_wait" 2>&1
done
echo '=== Google Services Framework package presence (optional GApps) ==='
pm path com.google.android.gsf 2>&1
echo '=== Recent targeted service failures ==='
logcat -d -b all -t 2000 2>/dev/null | grep -E 'libperfmgr: Failed|Wifi Hal|Failed to register wifi|Failed to start supplicant|GM8Dolby|GM8Fingerprint|scontext=u:r:gm8_dolby_app'
echo '=== Available controllers and actual cgroup mounts ==='
cat /proc/cgroups 2>&1
cat /proc/self/cgroup 2>&1
cat /proc/mounts 2>&1 | grep -E 'cgroup| /dev '
echo '=== Task file labels ==='
ls -ldZ /dev/cpuctl /dev/cpuset /dev/stune /dev/memcg /dev/blkio 2>&1
ls -lZ /dev/cpuctl/tasks /dev/cpuset/tasks /dev/cpuset/top-app/tasks /dev/stune/tasks /dev/stune/top-app/tasks /dev/stune/rt/tasks /dev/memcg/apps/tasks /dev/blkio/tasks 2>&1
for gm8_group in foreground background system-background restricted top-app camera-daemon; do
    echo "cpuset/$gm8_group"
    cat "/dev/cpuset/$gm8_group/cpus" "/dev/cpuset/$gm8_group/mems" 2>&1
done
echo '=== LMKD properties ==='
getprop ro.lmk.use_psi
getprop ro.lmk.use_minfree_levels
getprop ro.lmk.low
getprop ro.lmk.medium
getprop ro.lmk.critical
