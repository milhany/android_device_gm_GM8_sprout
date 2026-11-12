# GM8 LCD sleep investigation on SDK33

Disabling Ambient Display and ordinary screensavers is a confirmed temporary
workaround, not a root-cause repair. The permanent product overlay from
9d7aed2 was withdrawn: the inherited DozeService component is restored and no
screensaver preference is forced by this source change. DeviceIdleController
background power saving was never disabled.

The earlier sleep capture showed SurfaceFlinger requesting OFF and the kernel
reporting zero brightness and panel power-off. DozeService then started. There
was no captured system-server restart in that earlier window. Disabling these
three secure settings together restored full LCD blanking on the phone:

```sh
adb shell settings put secure doze_enabled 0
adb shell settings put secure doze_always_on 0
adb shell settings put secure screensaver_enabled 0
```

They persist across an ordinary reboot and are not reset by the next OTA.
Because all three were changed together, the result does not establish whether
Ambient Display, an ordinary screensaver, or their transition caused it. No
GPIO, minimum-brightness clamp or DCS command change is proven by this capture.

The later bugreport separately exposes actual system_server GPU-statistics
aborts and a Keystore/Keymaster lockup on screen-lock notification; see
RESTART-BLUETOOTH-20.0.md. Stabilize and distinguish those paths before treating
another boot animation as an ambient-display failure.

After the runtime fixes are installed and the phone has fully rebooted, an
isolated Ambient Display test can restore only doze_enabled, retaining AOD and
ordinary screensavers off. Record the original value and restore it after the
test if the fault returns. Do not turn on all three settings together: that
would discard the isolation needed to identify the failing path.

A proper display repair must preserve notification-pulse behavior and verify
power-button sleep, timeout sleep, notifications while asleep, charging, and
button/fingerprint wake. Merely removing the feature does not meet that
acceptance condition. The root cause remains open.
