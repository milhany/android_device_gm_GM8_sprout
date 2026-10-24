# Experimental mata Android 8.1 fingerprint

At the owner's request, lineage_GM8_sprout.mk sets BUILD_FINGERPRINT to:

```text
essential/mata/mata:8.1.0/OPM1.180104.267/399:user/release-keys
```

The historical source is MagiskHidePropsConf common/prints.sh at commit
65630c9588f5d661944e6846ea48869ad5acd2f5 (file blob
dbddef20bea59e12290b936eb751ed74d38456b0), whose Essential PH-1 entry lists this
Android 8.1 fingerprint with the original 2018-07-05 patch date:
https://github.com/Magisk-Modules-Repo/MagiskHidePropsConf/blob/65630c9588f5d661944e6846ea48869ad5acd2f5/common/prints.sh

The historical fingerprint record does not establish current server acceptance.
The ROM's own security patch property is not changed to that historical date.

Use the build system's fingerprint variable, following the conventional device
makefile approach, so generated partition fingerprints use the selected value.
Avoid adding a duplicate ro.build.fingerprint property in system.prop. Android
remains 12.1 / SDK 32; product/device, manufacturer/model, build ID, actual
security patch properties and signing keys retain their existing configuration.
The firmware is still built for GM8_sprout, not for mata.

This tests an alternate reported build identity. Google certification is a
server-side result and also depends on device/security state; no certification
or Play Integrity verdict is guaranteed by changing a fingerprint. Reference:
https://support.google.com/googleplay/answer/7165974

Rebuild and sign the complete ROM using the existing release keys, install the
normal update and reboot. A kernel/boot-only update cannot install the new
system build properties. No Format Data is required solely for this change
when updating the existing same-key release installation.

After installation, check:

```bat
adb shell getprop ro.build.fingerprint
adb shell getprop ro.system.build.fingerprint
adb shell getprop ro.build.version.sdk
adb shell getprop ro.product.device
```

The SDK must remain 32 and the product device GM8_sprout. Check the actual
signed target-files and OTA metadata as well as the runtime values; a successful
Make evaluation alone is not a full Android build or phone validation. Keep
each release's unique build number and timestamp and verify OTA behavior, since
the borrowed fingerprint itself is fixed across builds. To revert, remove the
single BUILD_FINGERPRINT assignment and rebuild/sign another normal update.
