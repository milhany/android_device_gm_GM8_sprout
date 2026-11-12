# SDK33 userdebug first-boot package

The full runtime source candidate compiled successfully on the build host on
2026-11-12. The owner's target-files inspection identifies SDK33 userdebug,
flattened APEXes, explicit unencrypted F2FS userdata and a 45,916,160-byte boot
image. The current build-tree kernel reports the expected qtaguid/classic-BPF,
cpuacct/cgroup-v1 and F2FS configuration. Those local kernel files are not proof
of every packaged kernel option or hardware operation.

The existing target-files archive is an input to signing, not an installation
ZIP. Build filenames containing `eng.builder` do not determine the variant;
the actual packaged `ro.build.type=userdebug` is checked. The inherited mata
fingerprint is retained; SDK/variant and certificate verification use the
actual build properties and cryptographic checks, not its text.

## Produce the test package

As builder in the existing Ubuntu 22.04 container, from the SDK33 checkout:

```sh
bash device/gm/GM8_sprout/tools/make-firstboot-20.0.sh \
  /absolute/path/to/the/new/target-files.zip
```

This command runs signing-helper host regressions, creates a new private output
directory, inventories the existing archive and signs it with the existing
`$HOME/android/gm8-signing/keys` key directory. `GM8_SIGNING_KEY_DIR` may select
another existing key directory. Missing keys, exposed private keys or changed
certificate identities stop the operation. No keys are generated, replaced or
uploaded. The original target-files archive remains unchanged. The original
key password is requested only for signing; a blank answer is appropriate only
for unencrypted PK8 keys. Passwords are never passed as command-line arguments.

There is no Android source build or kernel rebuild. The SDK33 signing tools
regenerate images after resigning APKs, rewriting MAC policy certificate
references and replacing OTA trust stores. That image packaging takes time and
disk space. JDK selection uses the existing validated checkout-JDK resolver.
Only flattened APEX inputs are accepted: every actual APK inside flattened
directories is inventoried and checked. Unused metadata for nonexistent packed
APEX containers is marked unused for signing; no actual APEX is skipped.

Output lives in a fresh `$HOME/android/gm8-20.0-firstboot/<UTC>-<suffix>/` folder:

* `signed-target_files.zip`: signed build archive, not an installation ZIP.
* `gm8-20.0-userdebug-firstboot.zip`: verified full A/B hardware-test OTA.
* `gm8-20.0-userdebug-firstboot-boot.img`: matching signed recovery-as-boot image.
* `verification.json`: artifact hashes, checks and explicit untested status.

No `latest` pointer is updated and no verification record is written on failure.
Partial outputs are retained for diagnosis and must not be treated as verified
packages. Repeating a failed operation uses a new output folder.

## Verification before reporting success

The helper validates SDK33/userdebug, fixed A/B boot/system/vendor partitions,
the current unencrypted F2FS policy, flattened APEX inventory and the absence
of an unplanned AVB/verity or virtual/dynamic partition signing configuration.
It preserves and checks every PRESIGNED APK byte-for-byte and verifies the
signing certificate of each resigned APK with the actual host apksigner.

Every signed target-files OTA trust store must contain the planned release
certificate. The actual signed boot image is parsed too: its gzip/raw newc
ramdisk trust store and `ro.debuggable=1` are checked, its kernel must match the
compiled input, and its v0/2048 layout must fit the 64 MiB boot partition.

The actual OTA whole-file CMS signature is verified with OpenSSL. The v2 payload
manifest must be a full update of exactly boot/system/vendor, with no old source
partition information, dynamic partition update or extra firmware partition.
Its boot size/hash must match the extracted signed boot image. FILE_HASH,
FILE_SIZE and metadata hash properties are checked. Finally the real SDK33
delta_generator verifies the payload signature using the planned public key.
No payload application is requested. The OTA must not request an automatic
wipe, downgrade or incremental update and must retain SDK33 and the signed
build fingerprint.

SDK33 source contracts reviewed: LineageOS android_build
`f3bb11d8739b84a311a40a3069dc4cfca688be22` signing/OTA/common utilities,
and the LineageOS android_system_update_engine lineage-20.0 payload generator
and update_metadata.proto. Generic OpenSSL/APK/CMS utility functions are shared
with release-19.1.py; its SDK32 signing gates and key-generation entry point are
never used. A bounded metadata reader is used only to validate the payload's
partition inventory; cryptographic payload validation uses delta_generator.

## Acceptance boundary

The helper's host fixtures use real OpenSSL keys and whole-OTA signatures.
Android APK/image signing and delta_generator are explicitly simulated there;
the owner's command must run the real checkout binaries and finish all checks.
Passing those checks establishes signed artifact consistency, not bootability.
The output remains userdebug and is not a public stable release.

Before a phone test, plan a backup and a clean F2FS installation using suitable
recovery, with a known working recovery/boot restoration path. Do not assume an
existing encrypted or older Android userdata installation can be reused. The
command itself never accesses a phone, selects a slot, formats userdata,
rewrites the partition table or flashes firmware.
