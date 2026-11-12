# GM8 LCD sleep policy on SDK33

The Android 13 device overlay inherited a nonempty `config_dozeComponent`
pointing to SystemUI's DozeService. The screen-off capture showed that service
starting after sleep, although SurfaceFlinger requested OFF and the kernel
reported zero brightness and panel power-off. There was no captured later
system_server, SurfaceFlinger or zygote restart in that recording.

On the phone, disabling these three secure settings together restored complete
screen blanking:

```sh
adb shell settings put secure doze_enabled 0
adb shell settings put secure doze_always_on 0
adb shell settings put secure screensaver_enabled 0
```

This confirms the combined workaround. It does not isolate which setting alone
is sufficient, prove a panel-driver fault or explain the separately reported
return to the boot animation. The settings survive an ordinary reboot.

`overlay-display` now supplies an empty `config_dozeComponent` and keeps always-on
display unavailable. In SDK33, AmbientDisplayConfiguration uses this component
to determine ambient-display availability; DreamManagerService cannot select a
doze dream when the component is empty. The overlay is first in
PRODUCT_PACKAGE_OVERLAYS so common Lineage product resources cannot restore the
inherited component. The lower device overlay no longer selects DozeService.

Ordinary screensavers default to disabled for fresh settings. Existing ordinary
screensaver preferences are preserved by the framework; the three commands
above remain the tested workaround for this installed user. No database reset,
forced settings service, GPIO change or panel-command rewrite is added.

This policy affects display dreams. DeviceIdleController, background Doze power
saving, hardware composer and the kernel suspend path are unchanged.

Validation: XML and framework resource names/types checked against SDK33;
product overlay inclusion and precedence reviewed. The runtime workaround was
confirmed on the phone. The packaged resource overlay still needs compilation
and verification on a later build. An overlay-only update needs target-files
and OTA signing with the existing keys, not a kernel rebuild or data format.

After installation, verify the packaged component resolves to an empty string:

```sh
adb shell cmd overlay lookup android android:string/config_dozeComponent
adb shell cmd overlay lookup android android:bool/config_dozeAlwaysOnDisplayAvailable
```

Test sleep from both the power button and screen timeout, notification arrival
while asleep, charging, and wake by button and fingerprint. Confirm the panel
stays fully dark. If the boot animation returns again, collect a bugreport
immediately after recovery; this change does not claim to fix an unobserved
restart.
