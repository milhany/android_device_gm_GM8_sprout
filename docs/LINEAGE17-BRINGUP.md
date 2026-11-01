# GM8 LineageOS 17.1 bring-up

This is an initial Android 10 source candidate, not a tested daily ROM.
Device base: 792239494f79d323c385f415767f9bb1e4145f38 (18.1 stock Dolby).
Vendor base: 9eec7f5fbaffc9f24cb5af224ce5443da3760b5e.
Kernel base: 1f1981295c7507163310c812e4a430be6f8d8777.
Paired kernel revision: 8f41b70bdb7e7ca8d3c404f414db4ae3fa53fcc0.
Paired vendor revision: a22c80f76f1bc90d07d627bd43af8e959e3b22bc.
The kernel carries the reviewed private input-clock quirk fix; other 19.1
kernel changes are excluded.

## Initial scope

- Select Android 10 audio HIDL 5.0 and audio@2.0 service host. The inspected
  Lineage 17.1 service hosts audio/effects 2/4/5, Bluetooth and soundtrigger;
  remove the separate 18.1 soundtrigger service request.
- Select ClearKey DRM 1.2. Keep camera provider 2.5: unlike audio 6.0, this
  provider and device 3.5 exist in the inspected 17.1 source.
- Keep the stock-derived GPU/HAL/kernel baseline and default HWC policy.
  Do not import V415, WPA3 framework patches or the Android 12 memory trials.
- Use GCC 4.9 and the complete container Perl for the kernel.
- Keep initial bring-up vanilla. Never copy rho/Android 11 or Android 12.1
  GApps into this product. Google apps need a verified Android 10 package
  after basic boot/hardware acceptance. Vanilla is not the final daily setup.
- Retain explicit single-SIM default and existing DSDS startup paths.

## Dolby receiver/call bypass

The newer DMS controller is carried from the 19.1 source with its failed-
attachment checkpoint and explicit retry policy. Android 10's hidden platform
audio-port/patch callbacks notify it of route changes, and playback callbacks
recheck mode on playback start/stop; no periodic polling is
added. The actual selected MUSIC output mask is queried, not the list of all
connected devices (which would always contain the built-in receiver).

If that route includes the earpiece, the mode is call/communication/ringtone,
or the route is unknown, explicitly disable DAP before releasing effect/DMS
handles. Keep the enabled preference/profile so media speaker/headphone
routing can restore them. An ordinary route bypass must not set the persistent
audio-error pause flag. The delayed verifier rechecks the route before reading
back settings. Listener registrations are removed when the service stops.

This is a global effect: bypass during any call is deliberately conservative,
including speakerphone and Bluetooth calls. Async route notifications are not
a sample-accurate native bypass guarantee. Test normal calls, VoIP, proximity
receiver playback, speaker/receiver switches, headphones and audioserver
restart on the phone before treating the change as working.

## Video/MOV acceptance

MOV is a container. Inspect a real failing file's video codec/profile,
resolution, rate, pixel format/bit depth, HDR transfer and audio codec before
altering extractor or decoder configuration. The retained HEVC XML advertises
1920x1088 and 244800 blocks/s; it does not prove Main10/HDR/4K/60fps support.
Do not enlarge these limits to make apps believe unsupported hardware exists.

On a computer with ffprobe, a read-only metadata helper is available:

```sh
python3 device/gm/GM8_sprout/tools/inspect-video.py problem.mov
```

It excludes filenames/tags/location metadata from its output and does not
change the video. If the codec is supported and only container parsing fails,
remuxing may help; if bit depth/profile is unsupported, remuxing cannot fix it.
No failing MOV sample has been provided or decoded in this work. Android 10
alone is not a fix for unsupported media formats or slow software decoding.

## Separate source checkout

Run inside the existing Ubuntu 22.04 gm8-build container as builder. Keep
19.1/18.1 checkouts, output trees and release keys intact. Initialize a new
~/android/lineage-17.1 tree and use configs/gm8-17.1.xml as local manifest.
The same Docker android-directory mount exposes this new sibling directory.
Use repo sync with moderate concurrency; HTTP 429 needs retry/backoff rather
than credentials for these public repositories.

After synchronization:

```sh
cd ~/android/lineage-17.1
set -o pipefail
bash device/gm/GM8_sprout/tools/build-17.1.sh check 2>&1 | tee ~/android/gm8-17.1-check.log
```

The full preflight requires SDK 29, real copy inputs and matching Dolby binary
hashes. Metadata-only mode deliberately does not claim binary or platform
build validation. The check stage runs m nothing. Then boot and target-files
stages are available; neither signs release images nor generates an OTA.
Do not run the Android 12 release signer against Android 10 target-files.

First require build/SELinux/VINTF checks, then boot and hardware evidence.
Before daily use add the proper Google services and repeat a fixed app-switch
and media workload after 1 hour and 24-48 hours, recording reloads, pauses,
camera/audio faults and actual decoder selection. Empty RAM alone is not an
acceptance metric. Android 10 also needs a separate security/app-compatibility
assessment; a new build date is not a new security patch level.

The current phone is on stock Pie. Any eventual cross-ROM installation needs
a backed-up clean-install/recovery plan. No flashing, partition resizing,
signing-key replacement or phone data modification has been performed here.

## Host checks completed

Python syntax and all device XML/JSON passed. Metadata preflight checked 25
XML files and 2584 declared copy inputs using the vendor Git tree; this did
not hash all proprietary files or validate Android modules. The actual Java
route policy compiled and passed 54 mode/route cases. A generated H.264 MOV
was inspected successfully by the ffprobe helper, with filenames/tags omitted.
No full Android build, native DMS playback or device boot has been tested here.

## Android 10 checkout paths and Python

The Q policy entry point is device/qcom/sepolicy-legacy-um/sepolicy.mk
(lowercase). The 17.1 extraction helper belongs to
vendor/lineage/build/tools/extract_utils.sh, not tools/extract-utils.
Preflight no longer requires extraction tooling to build an already-synced
proprietary vendor tree; the two extraction scripts use the correct Q helper.

The GCC wrapper explicitly uses env python2. The build entry point first
probes the synced prebuilts/python/linux-x86/2.7.5/bin/python2 and temporarily
prepends that directory to its own PATH. A runnable host python2.7 is a
fallback. Python 3 is retained for the GM8 preflight/fixup scripts; system
interpreter symlinks and update-alternatives are not changed. If neither
Python 2 candidate can run, stop before building and repair the interpreter
inside gm8-build. No host Ubuntu 26 Python downgrade is needed.

Host make fixtures reproduced the old case-sensitive include failure and
confirmed that the corrected real BoardConfig/policy collect both QCOM and
GM8 policy directories. Shell syntax and Python source parsing were checked.
A complete Android build and the interpreter's behavior in the user's
container remain separate checks.
