# GM8 camera baseline and SELinux fixes

The supplied `gm8-kamera-log.txt` and `gm8-kamera-dump.txt` contain enough
information to fix property-policy failures, but cannot establish visual
image quality without original photographs.

## What these records show

- Two cameras are enumerated, with rear/front facing metadata and a device 3.3
  interface. Both advertise hardware level 3, RAW, manual controls and
  reprocessing capabilities. Advertised capabilities still require real capture
  testing; this is not proof that every RAW/HDR/application combination works.
- These Snap sessions use the legacy PhotoModule path. Actual JPEG encoder
  jobs show 3120 x 4160, and capture parameters show JPEG quality 95.
- The inactive Camera1 shim dump shows JPEG 85 and a 144 x 176 picture size.
  These are not evidence of low-resolution saved photographs: the same log
  shows full-size encoder jobs. Do not tune the camera from idle shim values.
- Vendor exposure/white-balance processing is active. An AEC line marked
  ERROR, such as `aelux = 258`, is not itself proof that autoexposure failed.
  There is no chromatix load trace in this capture, so it cannot verify which
  tuning libraries were loaded or whether all calibration was applied.
- The HAL exposes vendor Camera1 auto-HDR options, while Camera2's scene-mode
  list in this dump does not include standard HDR mode 18. Those interfaces
  must not be treated as equivalent.

## Policy change

Repeated `mm-qcamerad` writes to `persist.vendor.camera.aeinfo` resolve to
`vendor_default_prop`; `persist.camera.debug.logfile` resolves to `default_prop`.
Both now have exact-name, string-valued contexts with dedicated vendor-internal
types. Only `mm-qcamerad` receives their property-write permission; the vendor
camera provider receives read access for its matching native-library consumers.
The existing
QCOM mapping for `persist.vendor.camera.debug.logfile` remains separate.

The log also shows zygote and Snap denied reads of `exported_camera_prop`.
Earlier records show the same read denial in Gallery/GMS. Add read-only property
access for those four observed domains. This rule lives in platform-private
policy because the Lineage app types are private and must not become vendor
API dependencies. No application receives property-write permission.

These fixes do not change exposure algorithms, enable debug logging, change
JPEG quality, modify calibration or grant blanket default-property access.
Correct property access removes a known compatibility failure; it does not
by itself demonstrate better photographs.

## Build and retest

Sync the device tree, apply the existing radio framework patch if needed,
then run preflight and `m sepolicy -j32` before a full ROM build. These are
system/vendor policy changes and do not take effect through a Snap or Dolby APK
update. Keep SELinux enforcing; no data wipe is required for this policy change.

After installing the ROM, open both cameras, capture photographs, switch
photo/video and inspect fresh logs for the two property writes and exported
camera property reads. Repeat Gallery and camera use by other apps. Compare
original JPEGs at the same resolution, scene, lighting and focus before changing
noise reduction, sharpening, HDR or chromatix tuning.

Other boot denials in the supplied log (old init actions, Wi-Fi controls,
Qualcomm daemon capabilities and unrelated properties) are not fixed by this
camera-specific policy. They need separate ownership/use checks rather than
blanket audit-derived permissions.
