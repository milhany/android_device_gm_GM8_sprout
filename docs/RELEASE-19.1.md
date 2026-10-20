# GM8 Android 12.1 user build and signing transition

The user variant is already in AndroidProducts.mk. The build helper now accepts
an optional second argument, preserving userdebug as its default, and a
target-files stage that builds target-files-package plus otatools. It retains
all compatibility preparation and build gates. This stage does not install,
sign, generate keys or change any device data.

```sh
set -o pipefail
cd ~/android/lineage-19.1
bash device/gm/GM8_sprout/tools/build-19.1.sh target-files user 2>&1 | tee ~/android/gm8-19-user-targetfiles.log
```

The final output identifies the target-files ZIP and the signing-inputs.txt
report in that build's sibling gm8-19.1-records directory. The read-only report
contains build properties, misc_info, APK certificate mappings, APEX key
mappings and OTA key names. It reads no private key file. If stale archives
make automatic selection ambiguous, it refuses to guess; rerun the inspector
with --target-files pointing to the intended ZIP. Do not flash target-files
or treat a user-variant bacon ZIP as release-signed.

## Data-preserving upgrade plan

Changing userdebug to user does not itself replace the signing keys. With
compatible keys and an otherwise compatible ROM, a variant change is not a
reason to format userdata. A user build disables ordinary adb root, so obtain
any required root diagnostics/migration while still on the working userdebug
build. Validate the current Bluetooth and fingerprint repairs on hardware;
their host tests are not hardware sign-off.

Moving the installed test-key build to custom release keys is a separate
certificate transition. System APK/shared-UID signature checks can reject a
direct dirty flash. Lineage's documented one-time migration rewrites the
stored package certificate mappings using the target release certificates.
The stock migration.sh `official` mode embeds Lineage's official certificates,
not this project's future custom certificates; do not run it unchanged for
this ROM. Its Android 12 path also uses ABX conversion for packages.xml.
No permanent package-signature bypass is part of this device tree.

Before installation, finish these steps using the actual target-files metadata:

1. Inventory the installed build's certificates and installed/updatable APEX
   state; keep a recoverable data backup and the working build.
2. Generate or reuse a stable set of private release keys outside all source
   repositories. Back them up; subsequent updates must use the same keys.
3. Re-sign target files with Android 12.1 releasetools, mapping the APK keys
   and both APEX container and payload keys. Preserve PRESIGNED Google/vendor
   components. Merely replacing ro.build.tags does not perform signing.
4. Generate the full A/B OTA from the signed target-files, verify its signatures
   and metadata, and check the installed recovery/update-engine acceptance
   path for the changed OTA/payload key.
5. Prepare and review a one-time migration with the project's actual public
   certificates, including any additional changed package keys found in the
   inventory. Do not assume the four-key legacy script covers every APK/APEX
   mapping. Perform migration on the old rooted userdebug build immediately
   before installing the signed build, with a rollback plan. Do not reboot the
   old Android after changing its stored certificates.

Format-free installation is the goal, not a guarantee made before the current
certificates, generated package and migration have been checked. Key creation,
signing, on-device migration and release installation are still pending.
Neither the helper nor the inventory script changes signature enforcement,
sets ro.debuggable on user builds, or publishes any private keys.

Primary references: LineageOS signing-builds documentation; LineageOS/scripts
key-migration/migration.sh and export-keys.sh; LineageOS/android_build
lineage-19.1 tools/releasetools/sign_target_files_apks.py. The latter maps APK
keys with -d/-k, APEX container keys with --extra_apks and payload keys with
--extra_apex_payload_key; -o also replaces OTA/payload verification keys.
