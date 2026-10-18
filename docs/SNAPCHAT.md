# Snapchat recording: software HEVC experiment

For the later measured 29.86 fps output, remaining darkness and a default-off
automatic-exposure comparison, see [SNAPCHAT-AE.md](SNAPCHAT-AE.md).

The supplied 2026-10-18 recording is from the 2026-10-17 ROM, before the
power/thermal changes. The normal Camera application records correctly;
Snapchat's live view stutters severely, with milder stutter in saved playback.

Snapchat opens Camera2/HAL3 and repeatedly creates `c2.android.hevc.encoder`
(the Android CPU encoder), including an 852x480, 30 fps, 2.5 Mbit/s session.
The exposed GM8 codec configuration has hardware AVC encoding and HEVC decoding,
but no hardware HEVC encoder. Software HEVC encoding is a concrete candidate for
excess CPU contention, not proof of the entire preview-stutter cause. Some
observed sessions can be background processing/transcoding rather than live
capture; a phone comparison is required.

The camera snapshot has no CameraService error trace. Its AE range is 7-30 fps,
with an 80 ms exposure/frame duration (about 12.5 fps) and ISO 1596. This also
limits preview smoothness in that lighting. It does not demonstrate 0.5 fps at
the sensor. Compare in good light without a lens/filter.

## Narrow test override

Android 11's `Codec2InfoBuilder.cpp` loads APEX codec definitions, then
`media_codecs_c2.xml`, then the ordinary vendor XML. Its parser accepts
`update="true" enabled="false"`; the builder skips disabled entries. See the
matching LineageOS 18.1 sources:

- https://github.com/LineageOS/android_frameworks_av/blob/lineage-18.1/media/codec2/sfplugin/Codec2InfoBuilder.cpp
- https://github.com/LineageOS/android_frameworks_av/blob/lineage-18.1/media/libstagefright/xmlparser/MediaCodecsXmlParser.cpp
- https://github.com/LineageOS/android_frameworks_av/blob/lineage-18.1/media/codec2/components/hevc/C2SoftHevcEnc.cpp

The vendor override hides only `c2.android.hevc.encoder` from codec enumeration
and lookup through MediaCodecList. It does not globally disable Codec2, change
camera HAL selection, force clock/thermal settings, or modify playback decoders.
It affects all applications: optional CPU HEVC encoding becomes unavailable.
Apps requiring HEVC encoding without an AVC fallback may fail; verify before
moving this experiment to the stable branch. It cannot force a closed-source
app to choose AVC or clear an app's cached codec choices.

## Phone gate

Host validation used the actual LineageOS 18.1 MediaCodecsXmlParser source and
header with Expat (only Android logging, property/status and unused OMX-role
boundaries stubbed). Parsing both a mixed codec fixture and the branch's actual
`media/libstagefright/data/media_codecs_sw.xml` followed by this override
sets the disabled attribute only on the CPU HEVC encoder, preserves all codec
types and other entries, and allows repeated parsing without duplicates.
This validates XML semantics, not Snapchat fallback or a full Android build.

Use a matching ROM, or test this one vendor XML on a userdebug phone with
root debugging and a successful `adb remount`. Check whether the destination
already exists and save its content before replacing it. Reboot after a push
so media services and app codec caches in memory are recreated. Do not clear
Snapchat data or disable SELinux. If remount fails, use the matching ROM;
do not continue pushing to a read-only partition.

Record a fresh log while taking 15-second front and rear videos in good light,
without filters. Check live preview, saved video, audio, the normal Camera app,
and HEVC playback. Expected successful fallback is `OMX.qcom.video.encoder.avc`
for the recording, with no `c2.android.hevc.encoder` creation. Confirm the codec
for the actual recording session, not just a later transcode/thumbnail task.
Successful fallback and better frame pacing remain unverified on hardware.

If recording fails, retains HEVC software encoding, or stays equally slow,
collect logcat plus `dumpsys media.camera` during recording. Restore the previous
XML (or remove only the newly added file if none existed) and reboot to roll
back a manual push. For a permanent source rollback, remove this file's
`PRODUCT_COPY_FILES` entry and rebuild the matching vendor image/ROM.

## Remaining low-light FPS experiment

The owner reports the HEVC exclusion fixed the severe stutter. A supplied
Snapchat output is AVC High, 1920x1080, 12.8 Mbit/s, with 82 frames over 6.32 s
(about 12.9 fps by presentation timestamps, median interval 80.47 ms). No interval
exceeds 81 ms. This file alone does not identify the specific AVC implementation.
The same-scene Camera output is AVC Baseline, 1920x1080, 20.6 Mbit/s, about
29.84 fps (median interval 33.51 ms). Neither sample has near-identical adjacent
frames in a reduced-resolution grayscale comparison; this is not proof of
sensor-readout timing. Both show motion blur/noise. Do not attribute the entire
quality difference to bitrate or promise that a FPS change will remove noise.

Changing the HAL3 switches produced no perceived improvement; without a new
dump this does not prove whether HAL selection changed. Restore both switches
to 1 for subsequent testing. The old Camera2 dump shows an automatic PREVIEW
request with AE 7-30 fps and an 80 ms result exposure. Both GM8 cameras advertise
30-30 fps. These facts motivate a separate app-scoped frame-rate experiment.

`tools/apply-camera-fps-compat.py` applies a checked single-file frameworks/av
patch. Apply it before preflight, then build `libcameraservice`, sepolicy and
the matching ROM. This change needs the framework library and vendor property
policy together; a Snapchat APK or another media XML cannot implement it.

The runtime opt-in is `persist.vendor.camera.gm8_fps30=true`, declared in this
device product with a vendor-public, exact boolean property. Other products
without that property keep their existing behavior. The patch runs after
request permission checks and only changes the observed 7-30 pair to 30-30 if:

- the validated camera client package is exactly `com.snapchat.android`;
- it is one repeating, non-reprocess request with one logical settings entry;
- control mode is AUTO, AE mode is ON, AE is not locked, and capture intent is
  PREVIEW or VIDEO_RECORD;
- the current camera's own static metadata contains the 30-30 pair.

Other FPS ranges, burst/physical requests, still-capture and manual controls
pass through. Only the AE FPS pair changes; AF, ISO, exposure, scene mode and
capture intent are retained. Preview is also affected: Snapchat's camera output
can be a preview surface that the app records itself, so the service cannot
reliably infer its record-button state. This is an experiment, not a measured
image-quality fix. A shorter exposure budget may make dark scenes darker or
noisier. A supported request range is not proof that every workload achieves it.

On the matching userdebug ROM, compare using a newly started recording/session:

Host checks exercise the actual patched function with Android metadata/property
boundaries mocked and real Android 11 metadata tag constants. They cover opt-in,
package/request/capability/AE guards, unchanged other metadata, repeat application
and update failures. The patch helper preserves unrelated work, is idempotent,
and refuses a divergent source without writes. The property rules compile in an
Android 11 policy reference with neverallows enabled; full target compilation,
property-context installation and frame-rate/image-quality validation remain
phone/build gates. Run the host check with
`python3 device/gm/GM8_sprout/tools/tests/camera_fps_compat_test.py`.

```sh
adb root
adb shell setprop persist.vendor.camera.gm8_fps30 false
adb shell am force-stop com.snapchat.android
# Reopen Snapchat and record the same scene, then enable and repeat:
adb shell setprop persist.vendor.camera.gm8_fps30 true
adb shell am force-stop com.snapchat.android
```

The property is persistent; false remains false after reboot and OTA until set
back to true. A currently submitted repeating request is not rewritten when
the property changes; reopening the app submits a fresh request. With the flag
on, logcat should contain `GM8 Snapchat FPS compat` when the observed request is
rewritten, and a camera dump during recording should show 30-30. Capture a fresh
recording and compare actual frame timestamps, brightness, noise, focus, sound,
front/rear cameras and normal Camera behavior. If the marker never appears,
inspect the request gates rather than forcing more metadata. Turning the flag
off restores request behavior; keep the independently successful HEVC override.
