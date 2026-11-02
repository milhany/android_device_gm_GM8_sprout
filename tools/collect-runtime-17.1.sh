#!/system/bin/sh
# Read-only targeted state. No subscriber IDs, keys, app lists or template data.
echo '=== Installed ROM and kernel ==='
getprop ro.build.version.sdk
getprop ro.lineage.version
getprop ro.build.type
uname -r
echo '=== Fingerprint selector and initialized driver nodes ==='
getprop vendor.gm8.fingerprint.sensor
ls -lZ /dev/sunwave_fp 2>&1
for gm8_irq in /sys/bus/platform/drivers/fpc1020/*/irq; do
    [ -f "$gm8_irq" ] && ls -lZ "$gm8_irq"
done
echo '=== Registered vendor services ==='
lshal 2>&1 | grep -E 'fingerprint|swfingerprint|dolby|hardware.perf'
echo '=== CPU frequency node ownership and values ==='
for gm8_cpu in 0 4; do
    for gm8_node in scaling_min_freq scaling_max_freq scaling_governor scaling_available_frequencies; do
        gm8_path="/sys/devices/system/cpu/cpu${gm8_cpu}/cpufreq/$gm8_node"
        ls -lZ "$gm8_path" 2>&1
        cat "$gm8_path" 2>&1
    done
done
echo '=== Available controllers and actual cgroup mounts ==='
cat /proc/cgroups 2>&1
cat /proc/self/cgroup 2>&1
cat /proc/mounts 2>&1 | grep -E 'cgroup| /dev '
echo '=== Task file labels ==='
ls -ldZ /dev/cpuctl /dev/cpuset /dev/stune /dev/memcg 2>&1
ls -lZ /dev/cpuctl/tasks /dev/cpuset/tasks /dev/cpuset/top-app/tasks /dev/stune/tasks /dev/stune/top-app/tasks /dev/memcg/apps/tasks 2>&1
echo '=== LMKD properties ==='
getprop ro.lmk.use_psi
getprop ro.lmk.use_minfree_levels
getprop ro.lmk.low
getprop ro.lmk.medium
getprop ro.lmk.critical
