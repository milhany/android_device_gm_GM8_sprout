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

The implementation uses this checkout's Android 10 source releasetools with a complete Python 2.7, native host tools,
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

## Signing interpreter and resuming a prepared run

The old kernel-tool Python 2.7.5 can execute the GCC wrapper while lacking
`zlib`. It is not sufficient evidence that it can run releasetools.
Before building, `check-python` probes Python 2.7 plus zlib, gzip, bz2, SSL,
hashlib, zipfile, ctypes and ElementTree. Prefer `/usr/bin/python2.7` or
`/usr/bin/python2`; accept the bundled interpreter only if the same probe passes.
In the Ubuntu 22.04 container install `python2 libpython2.7-stdlib` as root
if needed. Installing a similarly named package on the Ubuntu 26 host does
not change the container or add extensions to the bundled interpreter.

Only signing's child processes receive temporary `python`/`python2` aliases
for the selected interpreter. The directory is removed on exit. System links
and the kernel wrapper's interpreter remain unchanged. Inherited PYTHONHOME
and PYTHONPATH are cleared for the probe and signing subprocesses.

If preparation succeeded but signing failed before producing output files:

```bash
bash device/gm/GM8_sprout/tools/build-release-17.1.sh --resume /home/builder/android/gm8-17.1-release/RUN_DIRECTORY
```

Resume requires an existing signing plan in a direct child of the release root.
It skips compilation and key preparation, verifies the recorded source ZIP hash
and key identities, signs, verifies, writes checksums and publishes `latest`.
The old log is appended to, not erased. Existing signed target-files are fully reverified and reused before generating
an OTA. Invalid/incomplete signed archives fail verification and are preserved.
Existing OTA or exported boot outputs are refused to prevent overwrites. The normal command without arguments continues to build and sign.


## Main and recovery OTA certificates

Q's `ReplaceOtaKeys` writes the release certificate to the system OTA trust
store, and also appends `META/misc_info.txt:extra_recovery_keys` to the
recovery trust store. Lineage's common configuration declares its Lineage
recovery certificate this way. These are intentionally different trust stores.

Verification requires the system store and the correct recovery-as-boot (or
recovery) store. System certificates must match the release identity exactly.
Recovery certificates must match the release identity plus only the explicitly
declared extras, following the signing plan's mappings where present, otherwise
using the corresponding source public certificates. Extra/missing/replaced
certificates fail verification; arbitrary output certificates are never trusted.
The final OTA's whole-file signature remains pinned to the release key.
