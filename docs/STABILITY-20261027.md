# GM8 Android 12 stability candidate

Status: **source/host checks passed; full build and phone validation pending**.
This is an experimental device profile based on working lineage-19.1, not a
claim that the ROM is now stable or that a measured battery-life improvement
has occurred. The daily-driver kernel remains the existing GM8 3.18 tree.

## Evidence from October 27 captures

The owner reproduced disappearing images while scrolling YouTube Music and
Snapchat. Disabling HWUI partial updates did not help. Disabling hardware
overlays through Developer Options did stop the observed disappearing images.
The supplied SurfaceFlinger dump confirms `h/w composer disabled`, V415 GLES
on Adreno 505, and RGBA_8888_UBWC application layers routed through client
composition. This narrows the failure to a path affected by HWC composition;
it does not identify a particular driver instruction, UBWC defect or fence bug.

The battery summary covers 23h49m59s on battery with 28 system starts, not one
continuous discharge. It records 19h18m48s screen-off realtime, of which
5h32m05s is uptime (approximately 28.7%). This is not a clean idle experiment:
music, Android Auto, radio/network and other app activity are present. Do not
attribute all of that uptime to a suspend defect.

Notable actual partial-wakelock durations include YouTube Music AudioMix about
2h29m, Android Auto WSSS about 1h48m and a WhatsApp job about 1h27m. Actual
durations overlap and must not be added into a total. The separately reported
blamed times differ because overlapping locks share attribution. DMSS has
about 3h09m summed user/system CPU time; summed CPU time is not wall time or
proof that all of it ran in the background. Earlier runtime logs do show
cached DMSS processes terminated for excessive CPU, which merits app-level
investigation if it persists during a controlled comparison.

At the power snapshot the phone is USB-powered and Dozing, HAL autosuspend is
enabled, HAL interactive mode is off, and the framework's wake/display suspend
blockers are not held. That snapshot does not demonstrate a permanently stuck
framework suspend blocker. The charge-counter discharge fields report zero,
Bluetooth scan duration is negative, and the device power-profile XML is a
legacy single-table model rather than a calibrated Android 12 cluster model.
Do not use estimated per-app mAh rankings as calibrated consumption, rewrite
capacity to hide the problem, or infer battery health from the learned value.

## Device-side candidate changes

1. Prefer linear graphics allocations/client targets with the supported legacy
   gralloc `debug.gralloc.gfx_ubwc_disable=1` override and the HWC allocation
   controls `vendor.gralloc.disable_ubwc=1`,
   `vendor.gralloc.enable_fb_ubwc=0`. These are initialization-time controls;
   the matching rebuilt ROM and a reboot are required. This tests UBWC layout
   compatibility while allowing hardware composition. It may increase memory
   bandwidth and power, and is not a confirmed repair until HWC-enabled scroll
   testing passes. Explicit video formats and actual video operation still
   require device validation. No new GPU blobs or global forced-client
   composition setting is installed.
2. Change the EXPENSIVE_RENDERING GPU minimum vote from power level 0 to 3,
   already used by the interaction profile. Level 0 is the fastest end of the
   KGSL table; the previous minimum and maximum votes both selected 0 for the
   duration of the hint. The new minimum permits governor scaling over the
   existing 0..3 range rather than forcing the top state. It is not a new
   maximum-frequency cap. Screen-off and LOW_POWER cancellation and the
   existing boost durations remain covered by the real-source host test.
   The dumps do not establish that this hint was continuously active or that
   this change explains the measured standby discharge. Check both frame time
   and power before adopting the profile.

The companion vendor memory candidate is
`84fc751087f7e4777eb6cf380ec8f55bdfaeb429` on
`lineage-19.1-memory-test`: PPR off for SoC 313 and 1.5 GiB logical zRAM for
the 3 GiB non-Go GM8. Its actual-function host tests pass. Larger swap is not
additional physical RAM and neither memory change has a measured performance
benefit yet. The cached-process limit remains at the platform default; the
proposed 16-process experiment was withdrawn. The unsuccessful Instagram
warmer-component and HWUI-partial-update experiments should be restored before
comparing the combined ROM candidate.

## Validation and release gate

Properties were checked against the actual Lineage 19.1 CAF msm8996 gralloc
and HWC source readers. JSON node/action references and values were checked.
The actual GM8 Power.cpp and InteractionHandler.cpp pass the existing host
tests for early events, LOW_POWER transitions, screen-off cancellation, audio,
rendering and bounded interaction hints. These do not execute a phone's GPU,
gralloc, display driver or PMIC. An allocator built from another source could
ignore an override, so its result must be verified on the installed image.

Build complete user target-files and sign with the existing GM8 release keys.
Boot.img alone cannot install system properties, the power profile and the
vendor memory script. The changes themselves require no Format Data. Keep the
previous signed release available. Existing signing-helper messages describing
the initial clean-install workflow are not evidence that this particular
source change requires erasing data; verify package/signing compatibility
before installing an update.

After installing, turn OFF Developer Options' "Disable HW overlays" and
verify SurfaceFlinger reports **h/w composer enabled**. Check the property
values and allocation formats; compare newly started application layers,
because pre-existing buffers can retain old formats. Reproduce scrolling in
YouTube Music and Snapchat with HWC enabled. If images still disappear, this
candidate has failed its graphics gate: do not call it a stable repair.

Measure Snapchat launches using the same APK/profile/cache state. Check
ordinary camera/Snapchat video, Dolby playback, Bluetooth audio, fingerprint,
SIM data/calls and Wi-Fi reconnect/suspend before release. Compare screen-on
and screen-off battery separately under the same brightness, radio/network
and app workloads. Do not force idle, clear logs or change app restrictions
while collecting the baseline. A RAM average or one percentage drop is not
sufficient evidence of success.

Primary source references: LineageOS/android_hardware_qcom_display,
lineage-19.1-caf-msm8996, libgralloc/alloc_controller.cpp,
libgralloc/gpu.cpp, include/display_properties.h and
sdm/libs/hwc2/hwc_display.cpp; GM8 KGSL/power sources and the actual uploaded
diagnostic summaries. No raw logs, account names or private device identifiers
are included in this repository.
