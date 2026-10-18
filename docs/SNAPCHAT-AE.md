# Snapchat automatic-exposure comparison

## Measured state

The owner confirms CPU-HEVC exclusion removed the severe recording stutter.
After the fixed-FPS experiment, the new 2026-10-18 13:35 Snapchat output has
198 AVC frames, 1920x1080, about 12.7 Mbit/s and 29.86 fps by presentation
timestamps. Median interval is 33.33 ms and maximum 38.47 ms. No near-identical
adjacent pairs were found in a reduced-resolution grayscale comparison. The
clip is visibly darker than the earlier sample; scene/lighting/exposure changes
were not controlled sufficiently to assign the entire difference to the patch.

The later `gm8-snap-pozlama.txt` identifies a Camera2/HAL3 Snapchat session:

- result exposure 30,000,000 ns, frame duration 33,333,333 ns;
- result sensor sensitivity 431 and post-RAW sensitivity boost 100;
- AE ON, AE lock OFF, capture intent PREVIEW;
- noise reduction FAST in both request and result, correcting the earlier
  OFF-request observation from a different dump;
- a 1280x720 preview surface, which must not be confused with encoded 1080p.

`gm8-kamera-pozlama.txt` shows the normal Camera using native HAL1 instead of
Camera2, so it has vendor parameters rather than Camera2 result monitoring:
`cur-exposure-time=29.999999`, `cur-iso=3533`, recording-hint true, 30-30 fps,
continuous-video AF and denoise-on. The vendor ISO field and Camera2 sensor ISO
may account for gain differently. These readings are not proof that setting
Camera2 ISO to 3533 is appropriate. Camera2 advertises sensor ISO 100-1600 and
post-RAW boost 100-3199. Do not change advertised limits or force an ISO value.

## Default-off hypothesis test

Android 11 documents manual sensor exposure/sensitivity and post-RAW sensitivity
boost as overridden by AE when automatic exposure is on. The public Qualcomm
HAL family inspected still forwards supplied control fields into its parameter
batch. This motivates removing only the observed ignored template defaults; it
does not establish a fault in the closed-source GM8 binary or prove that the
fields cause darkness. Source references:

- https://github.com/LineageOS/android_system_media/blob/lineage-18.1/camera/docs/metadata_definitions.xml
- https://github.com/LineageOS/android_hardware_qcom_camera/blob/lineage-17.0/msm8998/QCamera2/HAL3/QCamera3HWI.cpp

Apply `tools/apply-camera-fps-compat.py` first, then
`tools/apply-camera-auto-gain-compat.py`. Patch 0002 is a separate guarded
CameraDeviceClient hook after permission checks and keeps patch 0001 intact.
Preflight checks both. Build libcameraservice and the matching ROM; the vendor
property context must be installed together with the framework library.

`persist.vendor.camera.gm8_auto_gain=false` is the product default. When explicitly
enabled, the new hook requires the exact Snapchat package, one repeating logical
non-reprocess request, AUTO control, AE ON/unlocked, PREVIEW/VIDEO_RECORD intent
and a 30-30 FPS request. All three supplied defaults must be present: sensor ISO
100, exposure 10263 ns and post-RAW boost 100. The camera's own static ranges must
confirm those minima and expose additional post-RAW gain. Nondefault controls,
manual AE, still captures and missing/malformed metadata pass through.

Only those three fields are erased from a copy of the request. All erases must
succeed before the copy replaces it. No numeric sensor/gain/exposure value is
invented; FPS, frame duration, resolution, AF, scene, NR, tone curves and capture
intent remain unchanged. This is not a forced brightness or quality adjustment.
The same public vendor boolean type as the FPS experiment permits cameraserver
reads and rooted userdebug toggling without new broad policy permissions.

## Controlled phone comparison

Keep HAL3 restored, HEVC exclusion installed and `gm8_fps30=true`. In identical
lighting, camera framing and focus, first record with auto-gain false. Then:

```sh
adb root
adb shell setprop persist.vendor.camera.gm8_auto_gain true
adb shell am force-stop com.snapchat.android
```

Reopen Snapchat and repeat. Logcat should contain `GM8 Snapchat AE compat` if
the default-control gates match. Enable tag monitoring for both ISO and boost:

```sh
adb shell dumpsys media.camera -m android.sensor.exposureTime,android.sensor.sensitivity,android.control.postRawSensitivityBoost,android.sensor.frameDuration
# During a newly started recording:
adb shell dumpsys media.camera > gm8-auto-gain-camera.txt
adb shell dumpsys media.camera -m off
```

Compare actual result ISO/boost/exposure and encoded FPS, brightness, highlight
clipping, noise, focus and sound. Test front/rear and verify normal Camera is
unchanged. If the marker is absent, inspect the gates before changing more tags.
If there is no useful gain or a regression, restore false and reopen Snapchat;
the independently tested FPS/HEVC behavior remains. The flag is persistent and
true stays true over reboot/OTA until explicitly reset to false.

Host fixtures compile the actual patch functions with Android 11 metadata tag
constants and mocked Android metadata/property boundaries. They check defaults,
opt-in, request/capability/manual exclusions, unchanged remaining metadata,
idempotence and transactional failure. Helper checks cover both patches together,
preserving unrelated work and refusing divergence. These do not replace a full
Android library/ROM build or establish a brightness improvement on hardware.
