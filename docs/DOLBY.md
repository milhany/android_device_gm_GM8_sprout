# GM8 stock Dolby on LineageOS 18.1

The old image packaged a DAP library and DMS init service, but the service had no
SELinux transition and there was no client keeping the global effect attached.
It also paired those blobs with a different Dolby generation's tuning file.

## Matched stock engine

The DMS service, both 32/64-bit DAP stacks and speaker/headphone tuning now come
from [GM8 build 411](https://github.com/TadiT7/gm_gm8_sprout_dump/tree/924fe93161fc1e25cd9d79f606b733dc483d267f).
`vendor/gm/GM8_sprout/dolby/stock-manifest.json` records each source path,
source/output SHA-256 and applied fixups. Stock binaries remain proprietary.

Two storage strings in `libdlbdsservice.so` are relocated in place:

- `/system/etc/dolby/dax-default.xml` -> `/vendor/etc/dolby/dax-default.xml`
- `/data/misc/media/` -> `/data/vendor/ds/`

`libdlbdsservice.so` and `libdlbmemoryservice.so` have an unused `libicuuc.so`
DT_NEEDED entry removed after verifying that they import no ICU 58 symbols.
`tools/fixup-stock-dolby.py` reproduces these changes during blob extraction.
No old ICU or platform framework library is installed. The profile's acoustic
values and amplifier gains are unchanged.

The provided Lenovo source uses another parameter protocol (CPDP command 5,
four profiles); stock GM8 DS1.10 uses command 11, six selectable profiles and
different enable/profile selectors. Its applications and native libraries must
not be mixed merely because both advertise DMS 1.0.

## Android client

`GM8Dolby` is a small platform-signed system application, built from Java source
in this device tree. It offers on/off and the six stock profiles, and maintains
one global AudioEffect on a worker thread. It uses the commands verified against
the stock `DolbyAudioEffect` bytecode: selector `0x01000000` for enable,
`0x06000000` for profile, command 11 and a three-int payload. Profile IDs 1..6
are Movie, Music, Game, Voice, Custom 1 and Custom 2. First boot enables Music;
later boots restore the user's selection from device-protected preferences.
Custom profiles currently use their stock values; this UI has no band editor.

The client reattaches after audioserver restarts, checks the native state before
reporting success, and retries failed attachments. The primary user owns the
global sound selection; secondary users see disabled controls. No stock boot
classpath jar, demo APK, old odex/vdex or Lenovo UI dependency is installed.

AudioFX is excluded so it does not process the same output mix. The DS2 hardware
property remains false: this integration restores the stock DS1 software effect.
The unrelated visualizer's undefined library reference is corrected as well.

## Build and device checks

Sync both device and vendor `lineage-18.1-rework` trees together. Run preflight,
`m nothing`, then `m GM8Dolby sepolicy -j32` before the usual `m bacon -j32`.
No clean or data format is required. The new database directory avoids reusing
the incompatible newer DAP database.

With music playing through the speaker, collect:

```sh
adb shell getprop init.svc.dms-hal-1-0
adb shell ps -AZ | grep -E 'dolby|dms'
adb shell ls -ldZ /data/vendor/ds
adb shell dumpsys media.audio_flinger > gm8-audioflinger.txt
adb logcat -d -b all > gm8-dolby-log.txt
```

Expect a running DMS service in `hal_gm8_dolby_default`, an attached DAP UUID
`9d4921da-8225-4f29-aefa-39537a04bcaa`, and `GM8Dolby: DAP ready` after the
requested state has been read back. Check for linker errors and SELinux AVCs.
Do not disable enforcing or ignore neverallow failures.

Compare Dolby off/on at the same moderate volume with the same track. Test
speaker, wired headphones, Bluetooth, compressed music/offload, notifications,
video, calls and an audioserver/device restart. A source/host check cannot
certify sound quality, HAL ABI compatibility or offload behavior on hardware.
