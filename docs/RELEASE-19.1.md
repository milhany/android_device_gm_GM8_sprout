# GM8 Android 12.1 user release: clean installation

The selected transition is a clean installation with a manual Format Data.
No package-certificate migration or packages.xml rewrite is needed. The
already-built SDK 32 user target-files can be signed without rebuilding Android.
The unsigned input stays unchanged.

## Existing build and signing metadata

The 2026-10-20 report confirms ro.build.type=user, ro.build.tags=test-keys,
A/B updates and recovery-as-boot. Its APK table has 2681 rows (2673 unique
names) and its APEX table has 40 rows. These are global module tables, not an
installed-package inventory. META/otakeys.txt is empty; Android 12.1
ReplaceOtaKeys explicitly falls back to the mapped default system certificate.

If target-files are needed again, the preparation command is:

```sh
bash device/gm/GM8_sprout/tools/build-19.1.sh target-files user
```

## Generate or reuse keys and sign the existing archive

Update the device checkout first, then run inside the existing build container:

```sh
cd ~/android/lineage-19.1
python3 device/gm/GM8_sprout/tools/release-19.1.py prepare \
  --top . \
  --target-files out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates/lineage_GM8_sprout-target_files-eng.builder.zip \
  --key-dir ../gm8-signing/keys \
  --output-dir ../gm8-signing/release-20261020

python3 device/gm/GM8_sprout/tools/release-19.1.py sign \
  --top . --output-dir ../gm8-signing/release-20261020
```

Prepare inspects actual ZIP entries and uses deapexer/debugfs to inspect APKs
inside installed APEXes, including compressed wrappers. It ignores uninstalled
test modules. Old certificate aliases share a new certificate, preserving
existing signature relationships. PRESIGNED Google/vendor packages remain
byte-identical. APK/OTA/container keys use RSA4096; APEX payload keys keep the
original supported RSA size and AVB algorithm.

Prepare asks twice for a password without echo. Reuse it at sign. A blank
password deliberately creates unencrypted PK8 keys. Nonblank passwords use the
Android make_key-compatible encrypted PK8 container; APEX payload PEM keys
remain unencrypted for avbtool. Key files/directories use umask 077, the key root
must be owned by the builder with mode 0700, and keys stay outside the checkout.
The example key directory is in the persistent Android bind mount. Back it up
separately and keep it for subsequent updates. Never publish private key files.
The helper reuses valid keys, refuses incomplete pairs and changed key identities,
and does not overwrite completed output. A temporary mode-0600 password file is
removed after signing; passwords never appear in command-line arguments.

The sign stage uses the matching built Android 12.1 sign_target_files_apks and
ota_from_target_files. It checks real APK/APEX container signer digests,
embedded APKs, APEX public keys and AVB payload signatures, user/release-keys
properties, and otacerts.zip stores. It verifies the detached whole-file OTA
CMS signature against the expected custom certificate and rejects wipe,
downgrade or another device's metadata. No automatic wipe, downgrade,
compatibility-skip or signature-bypass option is passed to releasetools.

Outputs in ../gm8-signing/release-20261020:

- gm8-19.1-user-release.zip: signed full A/B install package.
- gm8-19.1-user-release-boot.img: boot/recovery-as-boot from signed target-files,
  checked against the GM8 64 MiB boot partition limit and Android image header.
- signed-target_files.zip: archive to retain for future update generation.
- release-verification.json and public-key-map.json: shareable verification and
  certificate fingerprints; neither contains private key material.

The verification report records install_mode=clean, requires_format_data=true,
migration_required=false and device_tested=false. Signing success does not prove
hardware functions or the old recovery's trust configuration. Use the matching
new boot/recovery image for installation with the custom OTA certificate.

## Clean installation

Wait for successful signing and verification before wiping the phone. Back up
needed files first: Format Data deletes installed applications, their data and
internal storage. Transfer the signed ZIP and matching boot image to the ADB/
fastboot computer, so they remain available after the phone is formatted.

Check the active A/B slot in fastboot. Flash the matching boot image to that
slot's boot partition (the unsuffixed fastboot flash boot command normally
selects the active slot), then enter recovery. Do not boot the old Android
between formatting and installation. In the matching Lineage Recovery choose
Factory reset / Format data, then Apply update / Apply from ADB and sideload the
signed release ZIP. Reboot to system after successful installation. If bootloader
reboot-to-recovery is unsupported, use the device's recovery key sequence.
Do not erase persist, modem calibration or other unrelated partitions.

No phone is connected to this helper. It never flashes, formats data, rewrites
package certificates, clears fingerprint templates separately or changes
signature enforcement. User builds disable ordinary adb root. Verify Bluetooth,
fingerprint enrollment/unlock, SIM/data, camera, Wi-Fi and charging on the phone.

## Validation and sources

```sh
python3 device/gm/GM8_sprout/tools/tests/release_19_1_test.py
```

Host tests perform real OpenSSL key generation/reuse, encrypted-key validation,
CMS signing and signature-pinning/tamper tests. Synthetic archives and mock Android
binaries cover real/embedded inventory, certificate aliases, PRESIGNED retention,
CLI mappings, password cleanup, clean-install boot extraction and non-wipe guards.
Full Android signing/repacking still runs on the owner's target-files/otatools;
no signed GM8 firmware has been produced in the assistant workspace.

Primary references: LineageOS/android_build lineage-19.1 releasetools
sign_target_files_apks.py, apex_utils.py, common.py and ota_from_target_files.py.
The -o switch rewrites OTA trust stores in this branch; replacement of legacy
update-payload-key.pub.pem was explicitly removed. The matching new recovery,
rather than an assumed change to that legacy file, supplies the installation
trust path.
