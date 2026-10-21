# Recents incident: system-server watchdog and secondary Launcher failure

The owner reports disappearing recents previews, followed by boot animation
after opening Camera, entering recents and swiping. The attached
log(20261021-083753).txt contains an earlier boot plus the later incident.
It is not evidence that the immediately preceding source fixes were installed.

## Confirmed restart chain

At 16:56:14, Keystore2 reports an IKeystoreAuthorization::onLockScreenEvent
request pending for 84.55 seconds. Its nested operation is
lock_screen_lock_bound_key: calling importKey. This puts the start of the wait
around 16:54:50, before the logged Camera launch at 16:56:12 and recents gesture
at 16:56:15. Their timing does not establish that the gesture caused the hang.

At 16:56:19 the system-server watchdog explicitly kills PID 1363 because its
main handler is blocked in TrustManagerService.setDeviceLockedForUser ->
Authorization.onLockScreenEvent -> IKeystoreAuthorization Binder transaction.
The subsequent SystemUI and Google DeadSystemException crashes are downstream.
The camera provider aborts afterwards on an unchecked DEAD_OBJECT HIDL return.
System-server restarts as PID 8809 while Keystore2 PID 427 is still stuck.
The same importKey request remains pending for 179 seconds at the end of the log.

This explains boot animation as an Android runtime restart. It is a different
failure from the first-boot status-bar Fragment null context. No GPU failure
is established by this chain, so keep the owner-confirmed working GPU branch.

## Repair the secondary recents crash

At 16:57:28, the restarted Trebuchet process crashes in
SystemUiProxy.getRecentTasks -> Arrays.asList(null). When the Shell reconnects
or the controller is invalidated, the client must tolerate an absent array,
just as it already tolerates a missing Binder or RemoteException.
Return a fresh empty ArrayList for a null array. Preserve task order, grouped
task objects, maximum count/user/flags and mutable-list behavior on valid
responses. This prevents the confirmed Launcher null-pointer crash; it is not
a fix for the earlier Keystore watchdog or proof that all preview loss is fixed.

apply-runtime-compat.py now includes packages/apps/Trebuchet, and build records
capture that project's revision and local diff. The host regression compiles
the extracted actual method, reproduces the original null-array exception and
passes disconnected/null/empty/valid/RemoteException cases after repair. It
also tests order/identity, mutable independent lists and unchanged IPC arguments.
Three-project patch tests refuse drift in the last source before changing any
earlier source and preserve unrelated local edits. Full Android builds and
on-phone regression tests remain required.

The later camera startup additionally identifies 20 previously unlabeled
camera-specific names in mm-qcamerad PID 873 and the restarted camera provider
PID 8560, including persist.camera.max.snapshot, raw/YUV, HDR, preview and
burst/denoise configuration reads. Add these exact names to the existing scoped
camera type. Do not change values or enable camera modes, thermal overrides or
dump/debug switches. Unrelated SurfaceFlinger/fixed-FPS, Wi-Fi and console probes
retain their existing access restrictions.

## Evidence still needed for the Keymaster wait

The source route is Keystore2 super_key.rs -> KeyMint importKey -> the
Keymaster compatibility implementation -> legacy Keymaster 3.0 advertised by
this device. This log does not include the blocked native HAL/compatibility
thread stacks, so it cannot identify which stage or lock is stuck. The source
guard in Launcher does not repair that wait.

Capture a complete bugreport immediately after reproducing the failure:

```bat
adb bugreport gm8-recents-bugreport.zip
```

Retain the watchdog ANR/native thread stacks for Keystore2, Keymaster and its
compatibility service. Do not clear application data, delete Keystore files,
erase credentials/calibration, disable lock-bound key protection, extend the
system watchdog timeout or hide the problem with a GPU rollback.

Primary sources checked: LineageOS/android_system_security lineage-19.1
keystore2/src/super_key.rs and src/km_compat/km_compat.cpp;
LineageOS/android_hardware_interfaces keymaster/4.1/support/Keymaster3.cpp;
LineageOS/android_frameworks_base TrustManagerService and RecentTasksController;
LineageOS/android_packages_apps_Trebuchet SystemUiProxy.java, blob
f301ebc5c8df5d7234e386b5ddf2a7ec36faff89. The Launcher patch applies to this file.
