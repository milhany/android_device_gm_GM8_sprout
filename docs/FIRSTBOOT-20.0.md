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
directory and inventories the existing archive with the persistent
`$HOME/android/gm8-signing/keys` key directory. `GM8_SIGNING_KEY_DIR` may select
another existing key directory. Established release/platform/media/shared/
networkstack keys must already exist. Their missing, exposed, incomplete or
mismatched pairs stop the operation; they are never automatically regenerated.

The `package` stage inventories all installed APK signing identities before
signing, rather than stopping at the first fully absent new identity. It writes
`key-inventory.json` with source certificate paths, public certificate hashes,
the APKs requiring each identity and all absent key paths. This report contains
no private key material. Aliases of one source certificate share one identity;
a source certificate matching an already owned certificate reuses that pair.

Fully absent `sdk_sandbox` and `bluetooth` pairs may be created, along with new
APK-specific pairs stored as `certs/<source-certificate-DER-SHA256>`. These
additional identities must be required by actual installed APKs. The primary
OTA key and established named roles are never created or replaced by this stage.
Public-only OTA trust extras still do not require private keys. It first
validates the existing password and every current signing pair, then creates
distinct RSA-4096 identity keys. New PK8 encryption uses that same password;
blank means unencrypted PK8, matching the existing signing workflow. Existing
files remain unchanged. Private staging is under the protected key directory,
publication uses non-overwriting hard links and a preparation lock, and each
complete pair is validated before use. Partial pairs and concurrent preparations
are refused. Completed new pairs survive a later packaging failure and are
reused on retry. Include these new files in the private key backup; do not
regenerate them on later builds.

The wrapper now uses one `package` invocation and asks for the existing key
password once. Passwords are never command-line arguments. The explicit `plan`
stage remains read-only with respect to keys, and a separate `sign` stage accepts
an already prepared plan. The original target-files archive remains unchanged;
no key material is uploaded or included in the OTA.

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
* `key-inventory.json`: public identity discovery report, also retained if a
  later preparation/signing step fails.

No `latest` pointer is updated and no verification record is written on failure.
Partial outputs are retained for diagnosis and must not be treated as verified
packages. Repeating a failed operation uses a new output folder.

## Verification before reporting success

The helper validates SDK33/userdebug, fixed A/B boot/system/vendor partitions,
the current unencrypted F2FS policy, flattened APEX inventory and the absence
of an unplanned AVB/verity or virtual/dynamic partition signing configuration.
It preserves and checks every PRESIGNED APK byte-for-byte and verifies the
signing certificate of each resigned APK with the actual host apksigner.

Every signed target-files OTA trust store must match its explicit certificate
plan. SDK33 `extra_recovery_keys` are retained only in BOOT/RECOVERY/VENDOR_BOOT
stores; `extra_ota_keys` belong to ordinary system stores. An extra public trust
certificate does not require its private signing key. Existing APK/primary
signing identities are remapped consistently; other declared public trust
anchors are preserved and their DER hashes are pinned. All actual APK signing
and primary OTA mappings are passed explicitly rather than applying an implicit
`-d` mapping to unused SDK33 roles.

Each trust store is compared against its complete planned certificate multiset,
including any planned alias duplicates. Unexpected, missing, changed or leaked
recovery-only certificates fail verification. Every duplicate ZIP entry is read
through its own ZipInfo, so a later entry cannot hide an earlier certificate.
The actual signed boot image is parsed too: its gzip/raw newc ramdisk trust store
and `ro.debuggable=1` are checked, its kernel/load layout must match the compiled
input, and its v0/2048 layout must fit the 64 MiB boot partition. The OTA itself
and its payload are still signed/verified with the single planned primary key.

The plan format is version 2. Retry using the wrapper, which creates a fresh
output directory rather than reusing an older or failed plan. The host suite
now includes 21 cases covering public-only extras, scope separation, remapping,
changed public certificates, and exact duplicate handling in addition to the
original signing/boot/payload regressions. New cases verify multi-role discovery,
reuse, password validation/encryption, incomplete pairs, publication collisions,
preparation locking and the single-password package CLI. APK-specific cases
exercise combined standard/custom discovery, alias deduplication, existing
owned-certificate reuse, persistent retries, partial pairs, private directory
permissions, installed-APK proof and primary-key exclusion.

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
