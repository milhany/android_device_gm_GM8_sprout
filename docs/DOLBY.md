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

### Android 11 ABuffer ABI fix

The first device test (`log(7).txt`) showed DMS dying inside
`DolbyMemoryService::EventHandler::sendMessage` at memcpy address `0x18`,
followed by the audio HAL aborting its failed HIDL transaction. The 12-byte
parameter packet reached DMS; the destination buffer address was invalid.

API 27 `ABuffer` contains an extra `mMediaBufferBase` pointer before `mData`.
That field is absent in API 30. Stock inline `data()` therefore reads capacity
and range length as pointers (12 + 12 = `0x18`), rather than data and range
offset. This is not a missing SELinux allow rule.

`configs/audio/dolby_abuffer_fixups.json` records the exact build IDs, virtual
addresses, original/replacement bytes and meanings for the eight ARM Thumb and
ten AArch64 load instructions in `libdlbmemoryservice.so`. The fixup adjusts all
inline buffer accesses in both sendMessage overloads and the receive handler;
it rejects a different build ID or unknown instruction. The larger old
allocation sizes remain safe. AHandler/ALooper and AMessage's stored fields
have the same layout in these releases. No system library is replaced.

Reference headers:

- [API 27 ABuffer](https://android.googlesource.com/platform/frameworks/av/+/refs/tags/android-8.1.0_r1/media/libstagefright/foundation/include/media/stagefright/foundation/ABuffer.h)
- [API 30 ABuffer](https://android.googlesource.com/platform/frameworks/av/+/refs/tags/android-11.0.0_r46/media/libstagefright/foundation/include/media/stagefright/foundation/ABuffer.h)

The host regression test executes actual before/after ARM instructions against
an API 30 buffer layout, reproduces the reported `0x18` address, and verifies
pointer/length results at all eight sites with five buffer configurations:

```sh
python3 -m pip install unicorn pyelftools
python3 device/gm/GM8_sprout/tools/tests/test_dolby_abuffer_abi.py -v
```

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

Before creating the AudioEffect, `StockDmsClient` registers a non-null DMS
callback as native-service client type 3. Stock `registerClient` only invokes
`DsManager::init` for that client type; the effect's type-2 registration alone
does not initialize the profile manager. The client uses stock DMS transactions
1/2 with the callback binder, type and PID; it implements the callback's IBase
identity/hash responses and synchronous parameter notification acknowledgement.
The callback hashes match the stock interface library. The platform app's DMS
client permission is explicit. No mismatched Lenovo HIDL bindings are built.

The client reattaches after an ordinary audioserver restart and requires five
stable seconds plus native state readback before reporting success. A failed
attach or audio-server death during this period pauses Dolby until an explicit
user retry. A committed device-protected checkpoint also stops a process crash
from triggering another attach on automatic app restart. Internal preference
writes cannot schedule audio transactions. Turning Dolby off releases the effect
without sending parameters to a possibly broken native service. The primary user owns the
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

If the first image is repeatedly restarting audio, temporarily disable its
client with `adb root` then `adb shell pm disable-user --user 0 org.lineageos.gm8.dolby`.
After installing the fixed image, re-enable it with
`adb shell pm enable --user 0 org.lineageos.gm8.dolby` and open Dolby Audio.
If the safety guard has paused an attach, use its Retry button once and collect
the new log if it pauses again. Do not clear the guard in a boot-time loop.
