# Snapchat recording: software HEVC experiment

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
