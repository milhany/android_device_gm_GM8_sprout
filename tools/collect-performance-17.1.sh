#!/system/bin/sh
# Read-only. No benchmarks, trim, compilation, root requests, serials or app data.
read_node() {
    echo "[$1]"
    if [ -r "$1" ]; then cat "$1" 2>&1; else echo 'missing or not readable'; fi
}
echo '=== ROM ==='
getprop ro.lineage.version
getprop ro.build.version.sdk
uname -r
read_node /proc/uptime
echo '=== ART ==='
for gm8_key in pm.dexopt.boot pm.dexopt.install pm.dexopt.bg-dexopt dalvik.vm.heapgrowthlimit dalvik.vm.heapsize debug.hwui.renderer debug.gralloc.gfx_ubwc_disable vendor.gralloc.disable_ubwc vendor.gralloc.enable_fb_ubwc; do
    echo "$gm8_key=$(getprop "$gm8_key")"
done
echo '=== CPU placement ==='
for gm8_group in foreground background system-background restricted top-app camera-daemon; do
    read_node "/dev/cpuset/$gm8_group/cpus"
done
read_node /sys/devices/system/cpu/online
read_node /proc/sys/kernel/sched_boost
for gm8_cpu in 0 1 4 5; do
    for gm8_node in related_cpus scaling_governor scaling_min_freq scaling_max_freq scaling_cur_freq cpuinfo_max_freq interactive/target_loads interactive/above_hispeed_delay; do
        read_node "/sys/devices/system/cpu/cpu$gm8_cpu/cpufreq/$gm8_node"
    done
done
echo '=== GPU ==='
for gm8_node in gpuclk gpu_available_frequencies gpubusy max_pwrlevel min_pwrlevel thermal_pwrlevel default_pwrlevel force_clk_on force_rail_on idle_timer devfreq/governor devfreq/min_freq devfreq/max_freq; do
    read_node "/sys/class/kgsl/kgsl-3d0/$gm8_node"
done
echo '=== Memory / pressure ==='
cat /proc/meminfo
read_node /proc/swaps
for gm8_node in comp_algorithm disksize mm_stat stat; do read_node "/sys/block/zram0/$gm8_node"; done
read_node /proc/sys/vm/swappiness
for gm8_node in enable_process_reclaim min_score_adj pressure_min pressure_max; do
    read_node "/sys/module/process_reclaim/parameters/$gm8_node"
done
echo '=== Storage state: reads only, no CID or serial ==='
df -k /data
grep -E ' /data | / | /vendor ' /proc/mounts
for gm8_node in scheduler read_ahead_kb nr_requests rotational discard_max_bytes; do
    read_node "/sys/block/mmcblk0/queue/$gm8_node"
done
for gm8_card in /sys/class/mmc_host/mmc0/mmc0:*; do
    [ -d "$gm8_card" ] || continue
    for gm8_node in type name life_time pre_eol_info; do read_node "$gm8_card/$gm8_node"; done
done
for gm8_fs in /sys/fs/f2fs/*; do
    [ -d "$gm8_fs" ] || continue
    for gm8_node in lifetime_write_kbytes free_segments dirty_segments gc_idle gc_min_sleep_time cp_interval; do
        read_node "$gm8_fs/$gm8_node"
    done
done
echo '=== Thermal / battery sensors ==='
read_node /sys/module/msm_thermal/core_control/enabled
for gm8_zone in /sys/class/thermal/thermal_zone*; do
    read_node "$gm8_zone/type"
    read_node "$gm8_zone/temp"
done
for gm8_node in temp capacity current_now voltage_now; do read_node "/sys/class/power_supply/battery/$gm8_node"; done
echo '=== Two pressure / disk counter samples (5 s apart) ==='
for gm8_sample in 1 2; do
    echo "Sample $gm8_sample"
    cat /proc/uptime
    grep -E '^(pgmajfault|allocstall|pgscan|pgsteal|pswpin|pswpout|compact_stall|nr_dirty|nr_writeback)' /proc/vmstat
    cat /sys/block/mmcblk0/stat
    [ "$gm8_sample" = 2 ] || sleep 5
done
