# GM8 Android 10 signed installation ZIP

Run inside `gm8-build` as `builder`, from the separate SDK 29 checkout:

```bash
cd ~/android/lineage-17.1
bash device/gm/GM8_sprout/tools/build-release-17.1.sh
```

The workflow runs the existing incremental userdebug target-files/otatools
build, prepares a Q-specific signing plan, signs target files and creates a
full A/B installation ZIP. Signing keeps `userdebug` for initial bring-up
and changes the signing tags to `release-keys`; it does not switch to `user`.
It does not sync repositories, delete build outputs or flash a phone.

The original `releasekey`, `platform`, `shared`, `media`, and `networkstack`
key pairs must already exist under `~/android/gm8-signing/keys`. These pairs
are reused, never overwritten. Q APEX payload/custom-certificate identities
not present in this directory are generated once and reused subsequently.
Key passwords are read from the controlling terminal. Use the password of
the existing keys; press Enter for unencrypted PK8 keys. Preparation asks for
confirmation and signing asks again. Passwords are never command arguments;
the temporary private password file is removed after signing.

The implementation uses this checkout's Android 10 source releasetools with bundled Python 2.7, native host tools,
and JDK 9. The target-files build also builds `apksigner`, which Q does not
include in the `otatools` dependency list.
It maps installed APK certificates, preserves PRESIGNED components and
certificate aliases, and signs APEX containers and payloads. Q's APEX signer
preserves the payload filesystem, including any embedded APKs; this workflow
does not apply the Android 12 embedded-APK repacking algorithm. Compressed
APEXes are rejected. Active partition AVB/verity settings are rejected until
an explicit partition key plan is supplied; nothing is disabled to bypass it.

Before publishing `latest`, checks cover installed APK certificate identities,
APEX container certificates and payload AVB signatures, OTA trust stores,
release tags/SDK/device/variant, matching boot image size/header, and the OTA
whole-file CMS signature pinned to the original release certificate.
OTA metadata must assert GM8, contain an A/B payload, and request neither
a wipe nor downgrade. An incomplete run preserves the previous `latest`.

Outputs:

- `~/android/gm8-17.1-release/latest/gm8-17.1-userdebug-release.zip`
- `~/android/gm8-17.1-release/latest/gm8-17.1-userdebug-release-boot.img`
- `~/android/gm8-17.1-release/latest/SHA256SUMS`
- Per-run build log, public signing plan and verification report.

Only the installation ZIP and optional matching boot image/checksums should
be shared; keep the private signing directory backed up separately. No keys
or phone logs belong in the public repository.

This is the first 17.1 clean installation. Back up the phone and manually
Format Data in the appropriate recovery when changing from stock Pie/19.1.
The OTA itself does not force a wipe. Signing does not establish that the
ROM boots, that recovery accepts it, or that peripherals function.
