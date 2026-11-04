#!/system/bin/sh
# Temporary GM8 Q experiment. Only cpuset masks and a /dev (tmpfs) undo record
# are written. No flash, dexopt, app data, clocks, voltage or thermal changes.
gm8_state=/dev/gm8-cpuset-test
gm8_groups='background system-background restricted'

fail() { echo "ERROR: $*" >&2; exit 1; }

show() {
    for gm8_group in foreground top-app $gm8_groups; do
        printf '%s: ' "$gm8_group"
        cat "/dev/cpuset/$gm8_group/cpus" 2>&1
    done
}

restore() {
    # Validate all undo records before writing any mask.
    for gm8_group in $gm8_groups; do
        [ -r "$gm8_state/$gm8_group" ] || return 1
        gm8_saved=$(cat "$gm8_state/$gm8_group")
        case "$gm8_saved" in ''|*[!01234567,-]*) return 1 ;; esac
    done
    gm8_failed=0
    for gm8_group in $gm8_groups; do
        cat "$gm8_state/$gm8_group" > "/dev/cpuset/$gm8_group/cpus" || gm8_failed=1
    done
    [ "$gm8_failed" = 0 ] || return 1
    for gm8_group in $gm8_groups; do rm "$gm8_state/$gm8_group" || return 1; done
    rmdir "$gm8_state"
}

case "${1:-status}" in
    status) show; exit 0 ;;
    apply|restore) [ "$(id -u)" = 0 ] || fail 'Requires adb root on the userdebug build; no permissions will be changed.' ;;
    *) fail 'Use status, apply or restore.' ;;
esac

if [ "$1" = restore ]; then
    [ -d "$gm8_state" ] || fail 'No undo record; a reboot also resets this experiment.'
    restore || fail 'Restore failed; retain the undo record or reboot.'
    echo 'Original masks restored.'
    show
    exit 0
fi

command -v getprop >/dev/null 2>&1 || fail 'Android property service is required.'
[ "$(getprop ro.build.version.sdk)" = 29 ] || fail 'This test is only for Android 10.'
case "$(getprop ro.product.device)" in GM8_sprout|GM8_d_sprout) ;; *) fail 'Not a GM8 device.' ;; esac
gm8_soc=$(cat /sys/devices/soc0/soc_id 2>/dev/null)
[ -n "$gm8_soc" ] || gm8_soc=$(cat /sys/devices/system/soc/soc0/id 2>/dev/null)
[ "$gm8_soc" = 313 ] || fail 'Expected GM8 SoC 313; preserving CPU placement.'
for gm8_cluster in 0 4; do
    gm8_related=
    for gm8_cpu in "$gm8_cluster" "$((gm8_cluster + 1))" "$((gm8_cluster + 2))" "$((gm8_cluster + 3))"; do
        gm8_file="/sys/devices/system/cpu/cpu$gm8_cpu/cpufreq/related_cpus"
        [ -r "$gm8_file" ] || continue
        gm8_related=$(tr -d '[:space:]' < "$gm8_file")
        break
    done
    case "$gm8_cluster:$gm8_related" in 0:0123|0:0-3|4:4567|4:4-7) ;; *) fail 'Unexpected CPU policy topology.' ;; esac
done
for gm8_group in foreground top-app; do
    [ "$(cat "/dev/cpuset/$gm8_group/cpus" 2>/dev/null)" = 0-7 ] || fail 'Foreground/top-app is already customized.'
done
for gm8_group in $gm8_groups; do
    gm8_file="/dev/cpuset/$gm8_group/cpus"
    [ -r "$gm8_file" ] && [ -w "$gm8_file" ] || fail "Cannot access $gm8_file; no permissions will be changed."
    gm8_mask=$(cat "$gm8_file")
    case "$gm8_mask" in ''|*[!01234567,-]*) fail 'Unexpected original mask.' ;; esac
done
umask 077
mkdir "$gm8_state" || fail 'An experiment is already active; restore it first.'
for gm8_group in $gm8_groups; do
    cat "/dev/cpuset/$gm8_group/cpus" > "$gm8_state/$gm8_group" || fail 'Could not save masks; no CPU writes performed yet.'
done
trap 'restore; exit 1' HUP INT TERM
for gm8_group in $gm8_groups; do
    if ! printf '4-7\n' > "/dev/cpuset/$gm8_group/cpus"; then
        restore
        fail 'Apply failed; attempted rollback. Reboot if restoration failed.'
    fi
done
trap - HUP INT TERM
echo 'Temporary masks applied. Restore with the restore argument, or reboot.'
show
