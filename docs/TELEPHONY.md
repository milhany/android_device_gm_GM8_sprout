# GM8 Lineage 18.1 data switching

The SIM2 test log shows repeated `SET_PREFERRED_DATA_MODEM` responses with
`INTERNAL_ERR` (38). PhoneSwitcher retries every five seconds. SIM2 has circuit
switched voice service, but its packet service remains unregistered; PhoneGlobals
reports `NOT_ATTACHED`. The subscription becomes valid and SIM2 is selected for
default data. An `internet` default APN is found and sent to the modem.

Lineage 18.1's `RadioConfig.isSetPreferredDataCommandSupported()` selects the
new command whenever the HAL advertises version 1.1 or later. GM8's radio config
service advertises 1.1, yet the observed command fails. The compatibility patch
adds the opt-in `ro.ril.use_legacy_data_switch` property to this decision. GM8
sets it in `system.prop`, so PhoneSwitcher uses its existing per-phone
`setDataAllowed`/`ALLOW_DATA` path. Other products keep their original behavior.
The `ro.ril.` prefix already has the platform `radio_prop` context. No additional
SELinux permission or vendor binary modification is needed.

The device owner reported SIM2 mobile data working after the patched ROM on
2026-10-17. This confirms the reported use case on their phone; the wider
SIM-switching, voice/SMS and reboot matrix below remains a release check.
Neither returning fake success nor ignoring error 38 would attach the second SIM.

## Apply before building

After syncing the matching device and vendor branches, from the Android root:

```sh
python3 device/gm/GM8_sprout/tools/apply-radio-compat.py
python3 device/gm/GM8_sprout/tools/preflight.py
```

The helper uses checked `git apply`, accepts an already applied patch, and
refuses incompatible source without resetting or overwriting local changes.
It modifies `frameworks/opt/telephony/src/java/com/android/internal/telephony/RadioConfig.java`.
Keep this framework change locally; recheck after a framework sync. Preflight
rejects a missing patch. Build and install the full ROM, since both framework
code and the system property must reach the device; no data wipe is needed.

Single SIM remains the default (`ssss`). Persisted `dsds` is preserved, both
RIL startup paths remain available, and no automatic SIM-mode detection is
introduced. Physical-slot count, network defaults, APNs and modem NV are not
changed by this workaround.

## Device validation

With Wi-Fi off, select SIM2 for data and toggle mobile data off/on. Capture
`adb logcat -b radio -b main -b system -v threadtime` and
`adb shell dumpsys activity service com.android.phone/.TelephonyDebugService`.
Use the telephony debug service because `dumpsys phone` can stop early with a
shell/package security exception on this build. Also collect
`adb shell dumpsys telephony.registry`.

Expect `adb shell getprop ro.ril.use_legacy_data_switch` to return `true`,
`ALLOW_DATA` for the selected modem with a successful response, then packet
registration and a successful data call. The repeated preferred-data command
should disappear. Test a SIM in each slot separately, then both SIMs together,
switch data SIM1 -> SIM2 -> SIM1, and test voice/SMS and a reboot in `ssss` and
`dsds` modes. DSDS provides a selected default data SIM; this workaround does
not enable simultaneous mobile internet on both SIMs.

Reference implementation:
[RadioConfig](https://github.com/LineageOS/android_frameworks_opt_telephony/blob/lineage-18.1/src/java/com/android/internal/telephony/RadioConfig.java)
and [PhoneSwitcher](https://github.com/LineageOS/android_frameworks_opt_telephony/blob/lineage-18.1/src/java/com/android/internal/telephony/PhoneSwitcher.java).
