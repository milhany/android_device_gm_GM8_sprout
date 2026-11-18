#!/system/bin/sh
# Read-only performance capture: no task killing, cache dropping, tunable writes,
# service restarts, key access or application database collection.
set -u
case "${1:-}" in
    --help) echo 'Usage: sh collect-performance-20.0.sh (adb root required)'; exit 0 ;;
    "") ;;
    *) echo 'Unexpected argument' >&2; exit 2 ;;
esac
[ "$(id -u)" = 0 ] || { echo 'Run adb root first.' >&2; exit 1; }
command -v timeout >/dev/null || { echo 'timeout is required for bounded dumps.' >&2; exit 1; }
umask 077
output="/data/local/tmp/gm8-performance-$(date +%Y%m%dT%H%M%S)-$$"
mkdir -p "$output" || exit 1

read_nodes() {
    for node in "$@"; do
        [ -r "$node" ] || continue
        printf '\n%s\n' "$node"
        cat "$node" 2>&1
    done
}

snapshot() {
    label="$1"
    timeout 20 dumpsys meminfo > "$output/meminfo-$label.txt" 2>&1
    timeout 15 dumpsys gfxinfo > "$output/gfxinfo-$label.txt" 2>&1
    timeout 10 dumpsys graphicsstats > "$output/graphicsstats-$label.txt" 2>&1
    ps -A -T > "$output/threads-$label.txt" 2>&1
}

getprop > "$output/properties.txt" 2>&1
getenforce > "$output/selinux.txt" 2>&1
read_nodes /proc/version /proc/cmdline /proc/cpuinfo /proc/swaps \
    /sys/module/lowmemorykiller/parameters/* \
    /sys/module/process_reclaim/parameters/* > "$output/policy.txt" 2>&1
for zone in /sys/class/thermal/thermal_zone*; do
    read_nodes "$zone/type" "$zone/temp"
done > "$output/thermal-map.txt" 2>&1
snapshot before
echo 'Recording for about one minute: switch between your usual apps and reproduce the freeze.'
sample=0
while [ "$sample" -lt 30 ]; do
    {
        printf '\nSAMPLE %s\n' "$sample"
        date; cat /proc/uptime
        read_nodes /proc/meminfo /proc/vmstat /proc/stat /proc/diskstats /proc/loadavg \
            /sys/block/zram0/disksize /sys/block/zram0/max_comp_streams \
            /sys/block/zram0/comp_algorithm /sys/block/zram0/orig_data_size \
            /sys/block/zram0/compr_data_size /sys/block/zram0/mem_used_total \
            /sys/block/zram0/mm_stat /sys/block/zram0/stat \
            /sys/devices/system/cpu/online \
            /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq \
            /sys/devices/system/cpu/cpu*/cpufreq/scaling_min_freq \
            /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq \
            /sys/class/kgsl/kgsl-3d0/gpuclk \
            /sys/class/kgsl/kgsl-3d0/gpubusy \
            /sys/class/kgsl/kgsl-3d0/num_pwrlevels \
            /sys/class/thermal/thermal_zone*/temp
    } >> "$output/samples.txt" 2>&1
    sample=$((sample+1))
    sleep 2
done
snapshot after
logcat -b all -d -v threadtime > "$output/logcat.txt" 2>&1
dmesg > "$output/kernel.txt" 2>&1
mkdir -p "$output/anr"
for source in $(ls -t /data/anr/anr_* 2>/dev/null | head -n 5); do
    [ -f "$source" ] && cp "$source" "$output/anr/" 2>> "$output/anr-copy-errors.txt"
done
archive="$output.tar.gz"
tar -czf "$archive" -C /data/local/tmp "${output##*/}" || exit 1
echo "Diagnostic capture: $archive"
echo 'Capture finished. Pull the archive with adb pull.'
