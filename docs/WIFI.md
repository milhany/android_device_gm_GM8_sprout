# Experimental WPA3-Personal client support

Use device branch `lineage-18.1-wpa3-test` with the existing vendor and kernel
`lineage-18.1-rework` branches. The kernel backport is stored here as a small
checked patch, applied locally before the build; no global driver replacement
or different-device firmware is installed.

## Observed failure

`log(20261017-074154).txt` shows a saved SAE network, repeated
`Failed to select authenticated key management type` and `Failed to set WPA
key management and encryption suites`. The driver advertises `key_mgmt=0xd0f`,
which lacks `WPA_DRIVER_CAPA_KEY_MGMT_SAE` (0x10000). This failure occurs before
password authentication. The old Wi-Fi KeyStore generation timeout does not
recur in that recording; ordinary WPA2 connectivity still needs a separate test.

## Implementation

The existing Prima driver contains a host SAE implementation, but kernel builds
did not configure it and the 3.18 cfg80211 API lacked external authentication.
The kernel patch enables SAE with existing PMF support, adds station external
authentication and connection ownership/cleanup, preserves upstream netlink
numbers, admits SAE CONNECT only with external auth and PMF, and transfers PMKs
through PMKSA. Replies require the CONNECT socket owner. SSID/PMK lengths are
validated; driver request failures propagate as failures.

Lineage 18.1's supplicant already compiles SAE. Its patch requests CONNECT
socket ownership for driver-SME SAE so kernel authentication requests reach it
even without control-port-over-nl80211 support. Ordinary WPA2 behavior remains
unchanged. Existing Wi-Fi MAC/KeyStore and SIM2 framework patches are retained.

This is experimental WPA3-Personal **client** support. Physical firmware/frame
transport, SAE handshake and PMF operation need testing on GM8. This does not
add H2E-only compatibility, Enterprise 192-bit mode, WPA3 hotspot, new Wi-Fi
bands, or Wi-Fi certification. Do not treat a mixed WPA2/WPA3 connection as
proof of WPA3: verify SAE and PMF explicitly.

## Build

From the Android root after selecting the experimental device branch:

```sh
python3 device/gm/GM8_sprout/tools/apply-radio-compat.py
python3 device/gm/GM8_sprout/tools/apply-wifi-keystore-compat.py
python3 device/gm/GM8_sprout/tools/apply-wifi-compat.py
source build/envsetup.sh
lunch lineage_GM8_sprout-userdebug
python3 device/gm/GM8_sprout/tools/preflight.py
m bacon -j32
```

The WPA3 helper checks both projects before changing either, accepts already
applied patches, and refuses divergent source. It modifies kernel/gm/msm8937
and external/wpa_supplicant_8 locally. Recheck after syncing those projects;
do not discard local source edits blindly. Preflight requires both patches.
Install the complete matching ROM, including its boot image. No data wipe is
needed. Keep a known working build available while testing the experiment.

## Phone checks

First connect to a separate WPA2 hotspot and verify traffic with mobile data
off, reconnect and reboot. Next use a WPA3-Personal-only test SSID with PMF
required and an SAE method compatible with Android 11 (not H2E-only). Capture:

```sh
adb logcat -b all -v threadtime > gm8-wpa3-log.txt
adb shell dumpsys wifi > gm8-wifi-dump.txt
```

If available on the userdebug ROM, `adb shell wpa_cli -i wlan0 status` should
show `key_mgmt=SAE`, `wpa_state=COMPLETED` and `pmf=1`. A missing wpa_cli or socket
permission is a diagnostic limitation; it is not justification for a broad
SELinux grant. Check real traffic, wrong-password rejection, reboot, suspend,
Bluetooth, mixed-mode networks and WPA2 regression. Redact network identifiers
and never share passwords.

## Local validation

The final patch compiles all of `net/wireless/` and `drivers/staging/prima/`,
including their built-in links, with GM8's ARM64 msm8937-perf_defconfig and
Android GCC 4.9. The modern host DTC build uses `HOSTCFLAGS=-O2 -fcommon`.
All 395 existing netlink command/attribute values remain unchanged; new fields
use the upstream ABI numbers. The paired helper passes fresh application,
exact output, already-applied and divergent-source/no-write checks. Run the
real-handler host regression test with:

```sh
python3 device/gm/GM8_sprout/tools/tests/wifi_external_auth_test.py \
  --kernel kernel/gm/msm8937
```

It executes the actual C external-auth/PMKSA handlers with netlink/driver
fixtures, checking socket ownership, callbacks, length limits, failure status
and PMK transfer. This is not a full ROM/supplicant build or hardware test.

## Source references

- [AOSP WPA3 requirements](https://source.android.com/docs/core/connect/wifi-wpa3-owe)
- [External authentication, 40cbfa90218b](https://github.com/torvalds/linux/commit/40cbfa90218bc570a7959b436b9d48a18c361041)
- [SAE CONNECT, 10773a7c09b3](https://github.com/torvalds/linux/commit/10773a7c09b3)
- [Callback check correction, db8d93a7a355](https://github.com/torvalds/linux/commit/db8d93a7a355)
- [Connection ownership, bd2522b16884](https://github.com/torvalds/linux/commit/bd2522b168847106c1885f0319a2833bdf88bf9a)
- [Supplicant capability definitions](https://github.com/LineageOS/android_external_wpa_supplicant_8/blob/lineage-18.1/src/drivers/driver.h)
