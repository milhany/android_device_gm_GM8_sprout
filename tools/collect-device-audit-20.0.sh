#!/system/bin/sh
# Read-only diagnostic capture on the existing userdebug build. No phone reboot,
# package changes, service restarts, key deletion or partition writes.
set -u
include_boot=0
case "${1:-}" in
    "") ;;
    --include-boot) include_boot=1 ;;
    *) echo "Usage: $0 [--include-boot]" >&2; exit 2 ;;
esac
output="/data/local/tmp/gm8-audit-$(date +%Y%m%dT%H%M%S)-$$"
umask 077
mkdir -p "$output" || exit 1
getprop > "$output/properties.txt" 2>&1
getenforce > "$output/selinux.txt" 2>&1
ps -A -T > "$output/threads.txt" 2>&1
service list > "$output/services.txt" 2>&1
lshal > "$output/lshal.txt" 2>&1
cat /proc/interrupts > "$output/interrupts.txt" 2>&1
dmesg > "$output/kernel.txt" 2>&1
logcat -b all -d -v threadtime > "$output/logcat.txt" 2>&1
for name in time_daemon qseecomd android.hardware.keymaster@3.0-service-qti android.hardware.biometrics.fingerprint@2.1-service; do
    for pid in $(pidof "$name" 2>/dev/null); do
        folder="$output/process-$pid"
        mkdir -p "$folder"
        for item in status stat stack wchan maps; do
            cat "/proc/$pid/$item" > "$folder/$item.txt" 2>&1
        done
        ls -l "/proc/$pid/fd" > "$folder/fds.txt" 2>&1
        for thread in /proc/"$pid"/task/*; do
            tid="${thread##*/}"
            cat "$thread/stack" > "$folder/thread-$tid-stack.txt" 2>&1
        done
    done
done
for file in /vendor/bin/time_daemon /vendor/bin/qseecomd /vendor/lib64/libtime_genoff.so /vendor/lib64/libdrmtime.so /vendor/lib/libtime_genoff.so /vendor/lib/libdrmtime.so; do
    sha256sum "$file" >> "$output/vendor-sha256.txt" 2>&1
done
for device in /sys/bus/platform/drivers/fpc1020/*; do
    [ -d "$device" ] || continue
    ls -la "$device/" >> "$output/fpc-sysfs.txt" 2>&1
    for node in irq wakeup_enable fingerdown_wait; do
        [ -f "$device/$node" ] && ls -l "$device/$node" >> "$output/fpc-sysfs.txt" 2>&1
    done
done
for name in fingerprint sensorservice media.camera audio wifi; do
    dumpsys "$name" > "$output/dumpsys-$name.txt" 2>&1
done
# Preserve persistent traces before a later reboot can replace them.
for source in /sys/fs/pstore /data/misc/recovery /cache/recovery; do
    [ -d "$source" ] || continue
    name=$(echo "$source" | tr / _)
    cp -R "$source" "$output/$name" 2>> "$output/persistent-copy-errors.txt"
done
[ ! -r /proc/last_kmsg ] || cat /proc/last_kmsg > "$output/last_kmsg.txt"
cat /proc/cmdline > "$output/cmdline.txt" 2>&1
if [ "$include_boot" = 1 ]; then
    slot=$(getprop ro.boot.slot_suffix)
    case "$slot" in
        _a|_b)
            source="/dev/block/by-name/boot$slot"
            echo "$source" > "$output/boot-source.txt"
            dd if="$source" of="$output/current-boot.img" bs=1048576 count=64 \
                2> "$output/boot-copy.txt"
            sha256sum "$output/current-boot.img" > "$output/boot-sha256.txt" 2>&1
            ;;
        *) echo "Unknown slot; boot copy skipped: $slot" > "$output/boot-copy.txt" ;;
    esac
fi
archive="$output.tar.gz"
tar -czf "$archive" -C /data/local/tmp "${output##*/}" || exit 1
echo "Diagnostic capture: $archive"
echo "Pull this archive with adb pull."
