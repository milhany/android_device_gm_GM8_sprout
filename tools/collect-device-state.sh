#!/usr/bin/env bash
# Read-only diagnostics. Does not root, modify properties or request attestation.
set -euo pipefail

command -v adb >/dev/null || { echo "adb is required." >&2; exit 1; }
adb get-state >/dev/null

echo "Build, boot, encryption and SIM state:"
for prop in \
    ro.build.type ro.build.tags ro.build.version.sdk ro.build.version.security_patch \
    ro.product.first_api_level ro.vndk.version ro.secure ro.adb.secure ro.debuggable \
    ro.boot.mode ro.boot.verifiedbootstate ro.boot.flash.locked ro.boot.vbmeta.device_state \
    ro.crypto.state ro.crypto.type \
    persist.radio.multisim.config vendor.gm8.multisim.config persist.vendor.gm8.multisim_override \
    persist.sys.usb.config persist.vendor.usb.config \
    init.svc.qcrild init.svc.qcrild2 init.svc.vendor.keymaster-3-0; do
    value="$(adb shell getprop "$prop" | tr -d '\r')"
    printf '%s=%s\n' "$prop" "$value"
done

echo "SELinux:"
adb shell getenforce
echo "/data mount (source, mountpoint, filesystem):"
adb shell cat /proc/mounts | awk '$2 == "/data" { print $1, $2, $3 }'
echo "Effective framework icon mask and configured slot count:"
adb shell cmd overlay lookup android android:string/config_icon_mask || true
adb shell cmd overlay lookup android android:integer/config_num_physical_slots || true
echo "Registered radio/keymaster HALs (if lshal is available):"
adb shell lshal 2>/dev/null | awk '/android.hardware.(radio|keymaster)|vendor.qti.hardware.radio/' || true
echo "GMS/Play Store package versions:"
for package in com.google.android.gms com.android.vending; do
    echo "$package"
    adb shell dumpsys package "$package" | awk '/versionName=|versionCode=/ { print; if (++n == 2) exit }' || true
done

echo "Run the Play Integrity checker separately and keep its raw verdict or API error."
