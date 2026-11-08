#!/system/bin/sh
# Temporary GNSS verbosity only. No firmware, assistance-data or policy changes.
set -eu
umask 077

duration=${1:-180}
case "$duration" in ''|*[!0-9]*) echo 'Duration must be 30..300 seconds.' >&2; exit 2;; esac
if [ "$duration" -lt 30 ] || [ "$duration" -gt 300 ]; then
    echo 'Duration must be 30..300 seconds.' >&2; exit 2
fi
if [ "$(id -u)" != 0 ]; then
    echo 'ADB root is required. Run adb root first; no Magisk is needed.' >&2
    exit 1
fi
gps=/vendor/etc/gps.conf
izat=/vendor/etc/izat.conf
base=/data/local/tmp/gm8-gps-diagnostic
lock=/data/local/tmp/gm8-gps-diagnostic.lock
for file in "$gps" "$izat"; do
    if [ ! -f "$file" ] || [ -L "$file" ]; then
        echo "Expected a regular config: $file" >&2; exit 1
    fi
done
for service in gnss_service loc_launcher; do
    if [ "$(getprop "init.svc.$service")" != running ]; then
        echo "$service is not running. Open the GPS test app first; no changes made." >&2
        exit 1
    fi
done
if ! mkdir "$lock"; then
    echo 'A diagnostic lock already exists; do not start another capture.' >&2
    exit 1
fi
work=
gps_mounted=0
izat_mounted=0
services_touched=0
logger_pid=
filter_pid=

stop_services() {
    stop gnss_service
    stop loc_launcher
    for service in gnss_service loc_launcher; do
        count=0
        while [ "$(getprop "init.svc.$service")" != stopped ]; do
            count=$((count + 1))
            [ "$count" -lt 10 ] || return 1
            sleep 1
        done
    done
}

start_services() {
    start loc_launcher
    start gnss_service
}

cleanup() {
    result=$?
    trap - EXIT INT TERM
    set +e
    if [ -n "$logger_pid" ]; then
        kill "$logger_pid" 2>/dev/null
        wait "$logger_pid" 2>/dev/null
    fi
    # Closing logcat's pipe lets grep flush its final partial output buffer.
    if [ -n "$filter_pid" ]; then wait "$filter_pid" 2>/dev/null; fi
    configs_ok=1
    services_ok=1
    if [ "$services_touched" = 1 ]; then
        stop_services || services_ok=0
    fi
    if [ "$izat_mounted" = 1 ]; then umount "$izat" || configs_ok=0; fi
    if [ "$gps_mounted" = 1 ]; then umount "$gps" || configs_ok=0; fi
    if [ -n "$work" ]; then
        cmp -s "$gps" "$work/gps.conf.original" || configs_ok=0
        cmp -s "$izat" "$work/izat.conf.original" || configs_ok=0
    fi
    if [ "$services_touched" = 1 ]; then start_services || services_ok=0; fi
    if [ "$configs_ok" != 1 ]; then
        echo 'RESTORE FAILED: reboot the phone to remove temporary bind mounts.' >&2
        result=1
    else
        echo 'Original config bytes preserved/restored.'
    fi
    if [ "$services_ok" != 1 ]; then
        echo 'Service control failed; reboot the phone before another capture.' >&2
        result=1
    fi
    if [ -n "$work" ]; then
        printf 'exit_status=%s\nconfigs_restored=%s\nservice_commands_ok=%s\n' \
            "$result" "$configs_ok" "$services_ok" > "$work/result.txt"
        rm -f "$work/log.pipe"
        echo "Capture directory: $work"
    fi
    rmdir "$lock"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "$base"
work="$base/$(date +%Y%m%dT%H%M%S)-$$"
mkdir "$work"
cp "$gps" "$work/gps.conf.original"
cp "$izat" "$work/izat.conf.original"

make_verbose() {
    original=$1
    key=$2
    output=$3
    count=$(grep -Ec "^[[:space:]]*$key[[:space:]]*=" "$original" || true)
    if [ "$count" != 1 ]; then
        echo "Expected exactly one active $key setting; no config mounted." >&2
        return 1
    fi
    sed "s/^[[:space:]]*$key[[:space:]]*=.*$/$key = 5/" "$original" > "$output"
    chmod 0644 "$output"
}
make_verbose "$work/gps.conf.original" DEBUG_LEVEL "$work/gps.conf.verbose"
make_verbose "$work/izat.conf.original" IZAT_DEBUG_LEVEL "$work/izat.conf.verbose"

# Match the original inode's SELinux type; never change enforcement or policy.
for name in gps izat; do
    if [ "$name" = gps ]; then target=$gps; else target=$izat; fi
    label=$(ls -Zd "$target")
    label=${label%% *}
    case "$label" in u:object_r:*:s0) ;; *) echo 'Cannot resolve config SELinux context.' >&2; exit 1;; esac
    chcon "$label" "$work/$name.conf.verbose"
done

{
    date
    getprop ro.build.version.sdk
    getprop ro.lineage.version
    getprop ro.build.type
    getprop gsm.version.baseband
    sha256sum "$gps" "$izat" /vendor/bin/xtra-daemon \
        /vendor/lib64/libizat_core.so /vendor/lib64/libloc_api_v02.so /vendor/lib64/libgnss.so
    ls -Z "$gps" "$izat"
} > "$work/environment.txt" 2>&1
dumpsys location > "$work/location-before.txt" 2>&1
mkfifo "$work/log.pipe"
logcat -b all -v threadtime -T 1 > "$work/log.pipe" 2> "$work/logcat-stderr.txt" &
logger_pid=$!
grep -iE 'LocSvc|QMI_FW|Gnss|GpsPsds|XTRA|NTP|loc_launcher|gnss_service|avc:.*(location|gps)' \
    < "$work/log.pipe" > "$work/gps-log.txt" &
filter_pid=$!

services_touched=1
stop_services
mount -o bind "$work/gps.conf.verbose" "$gps"
gps_mounted=1
mount -o bind "$work/izat.conf.verbose" "$izat"
izat_mounted=1
start_services
echo "GPS capture started for $duration seconds. Keep the GPS app foreground, outdoors."
echo 'Only temporary verbose logging is enabled; reboot also removes these config mounts.'
elapsed=0
while [ "$elapsed" -lt "$duration" ]; do
    step=15
    remaining=$((duration - elapsed))
    if [ "$remaining" -lt "$step" ]; then step=$remaining; fi
    sleep "$step"
    elapsed=$((elapsed + step))
    echo "$elapsed/$duration seconds"
done
dumpsys location > "$work/location-after.txt" 2>&1
