# GM8 Q IMS service binding correction

Date: 2026-11-04. Reviewed baseline:
ab7acf4f1bbc0184286d113fc04b3c3529f15394.

## Confirmed mismatch

The supplied package dump confirms the installed product privileged app
org.codeaurora.ims targets/requires SDK 29, is direct-boot aware, runs under the
phone shared UID, declares .ImsService with the android.telephony.ims.ImsService
action, and protects binding with android.permission.BIND_IMS_SERVICE. Its three
required QTI/IMS shared Java libraries resolve. The APK is present, enabled and
not stopped. The private dump, signatures and unrelated package inventory are
not committed.

The read-only command cmd phone ims get-ims-service -s 0 -d reports
com.android.phone, not the configured org.codeaurora.ims. The earlier log binds
com.android.phone/com.android.internal.telephony.ims.ImsResolver.

In Q, PhoneFactory reads the framework resources config_dynamic_bind_ims and
config_ims_package. ImsResolver replaces the requested default package with
its static com.android.phone adapter when dynamic binding is false. Q's
framework default is false; the device selected org.codeaurora.ims but never
overrode that Boolean. This explains the selected static adapter without
requiring any claim about carrier registration.

Set config_dynamic_bind_ims=true in the existing framework overlay. Keep the
explicit package, original APK, permissions, radio/IMS binaries, subscriptions
and carrier policy. No network registration/provisioning state is fabricated.
The existing source gate now rejects a missing/false binding flag or another
default package. Its regression checks cover these failures.

## Hardware validation

Build/install the normal existing-key signed Q update. The resource change is
in the ROM framework; updating only boot.img does not include it. An update
does not require changing keys or formatting data.

First run, even without a SIM:

```bat
adb shell cmd phone ims get-ims-service -s 0 -d
```

The expected default is org.codeaurora.ims. This command reports configuration,
not a successful binding, IMS registration or a working call. Next verify the
actual service connection/log and its advertised MMTEL features.

Then test with the user's Turkcell SIM loaded and LTE coverage. The prior
capture and supplied command both show ABSENT,ABSENT; they cannot establish
Turkcell provisioning, an IMS APN/PDN, VoLTE registration or VoWiFi/ePDG success.
The user's earlier SIM test has no matching radio capture in this evidence.

Check LTE IMS registration and a regular call retaining LTE. For VoWiFi,
enable Wi-Fi calling where available and confirm actual registration/call over
Wi-Fi; do not infer it from a visible switch or debug availability property.
If registration fails, inspect the real vendor IMS/QMI/IWLAN services, radio log
and effective carrier settings before changing APNs, provisioning flags or
modem profiles. Stock-ROM success for this SIM is still an unanswered comparison.

Useful read-only state/capture commands (slot 0; adapt only if the SIM uses
another slot):

```bat
adb shell getprop gsm.sim.state
adb shell cmd phone ims get-ims-service -s 0 -d
adb logcat -b radio -d > gm8-ims-radio.txt
```

Keep the radio capture private; publish only source fixes and sanitized findings.

## Validation and source references

Source configuration regression checks and XML/Python parsing pass. Full Q
resource compilation, actual service binding, carrier registration, calls,
handover and emergency-call behavior remain hardware validation requirements.
No full Android build or hardware test was performed on the assistant host.

- LineageOS/android_frameworks_base lineage-17.1,
  core/res/res/values/config.xml: config_dynamic_bind_ims default.
- LineageOS/android_frameworks_opt_telephony lineage-17.1,
  src/java/com/android/internal/telephony/PhoneFactory.java and
  ims/ImsResolver.java: resource lookup and static-adapter selection.
- LineageOS/android_packages_services_Telephony lineage-17.1,
  src/com/android/phone/TelephonyShellCommand.java: read-only get-ims-service.
