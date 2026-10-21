# Camera capture and outstanding Keymaster wait

The focused capture contains retained October 20 boot records and October 21
runtime records. The old TTS Java crash and child-init SIGABRT are not new
crashes during this camera test. No raw user logs or device identifiers are
stored in this repository.

## Repeated camera property denials

The October 21 camera daemon reads three unlabeled properties:

- persist.camera.ltm.noip: 2873 denied reads.
- persist.camera.ltm.sw: 2873 denied reads.
- persist.camera.ltm.overlap: 6 denied reads.

Add these three exact names to the existing gm8_legacy_camera_prop type and
reuse the existing camera-domain read permission. Values remain untouched,
including any unset defaults. No prefix-wide default_prop access, property
write permission or image-processing override is introduced. The unrelated
persist.debug.sf.showfps denial remains separate.

These 5752 read failures are a concrete policy defect and repeated log traffic.
Removing them does not establish a fix for frame pacing, DSPS or Keymaster.
Verify the names no longer produce denials after building/installing the new
policy; full SELinux compilation and phone validation are still required.

## Sensors and camera state

Both the sensors HAL and sensors.qti are running. SensorService enumerates
BMI160 gyroscope/accelerometer; accelerometer clients are active and sensor
privacy is disabled. The camera app's framework sensor connection is its
OrientationEventListener using the accelerometer. This does not inspect the
camera daemon's direct sensor1/DSP connection or prove gyro delivery to camera.

The active front-camera client is in PREVIEW with a 1920x1080 preview and a
30-30 FPS request. Stabilization is OFF. Static supported ranges and old/closed
session dumps are not the active stream's measured FPS. There are 34 DSPS
request timeout messages in the October 21 portion, including start/stop paths.
No matching sensor-domain permission denial identifies their cause.

QCamera handleBufferWithLock messages print frame numbers and buffer addresses
at ERROR severity without a dropped-buffer status. Their severity alone does
not establish frame loss. Retain sensor/EIS configuration while obtaining the
missing request/response evidence.

## Higher-priority Keymaster/QSEE wait

Keystore2 reports outstanding importKey and generateKey calls for
SecurityLevel(1), including generate_key without attestation. The same calls
are printed repeatedly; thousands of watchdog lines do not mean thousands of
distinct key requests. The oldest visible operation is pending for about 735
seconds at the end of capture. Its inferred start is around 18:40:40, preceding
the first camera event at 18:46:28 in CameraService history and the focused
opening at 18:51:19. Camera causation is not established.

The process snapshot provides a more specific blocking point:

- keystore2: binder_ioctl.
- android.hardware.keymaster@3.0-service-qti:
  __qseecom_process_incomplete_cmd.
- A qseecomd child: state D in qseecom_release; parent in do_wait.

The kernel's drivers/misc/qseecom.c shows that the incomplete-command path
waits for a listener response and that release may take app_access_lock.
These samples narrow the investigation to the listener/cleanup path but do
not identify a listener ID, prove mutex ownership or establish a lock cycle.
Do not bypass the secure backend or pretend a timed-out key operation worked.

One Play Store input-dispatch ANR occurs at 18:47:21. Its Java/native
main-thread trace is needed to establish whether it waits for this backend.
No new system-server watchdog kill occurs in the October 21 capture.

While blocked, preserve a bugreport and thread-level ps before a full reboot.
Native Keystore traces were blocked on the production user build in the earlier
bugreport. A temporary userdebug ROM signed with the existing release keys is
the next diagnostic option. The existing release helper currently accepts
user target-files only; do not feed it userdebug archives or replace the keys.

References: GM8 lineage-19.1 kernel drivers/misc/qseecom.c at
b0555eee97c41a59830d94134b4c882c75027220; the focused camera log, SensorService,
CameraService and process snapshots supplied on October 21. Kernel and camera
configuration are unchanged by this policy fix.
