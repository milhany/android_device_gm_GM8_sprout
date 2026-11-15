# GM8 SDK33 recovery boot loop

## Evidence from the supplied device archive

`gm8-after-recovery.tar.gz`, pstore `console-ramoops`, kernel
`3.18.124-perf-g8aa6f5c29fa9-dirty`:

- 3.801s: first stage mount skipped in recovery mode.
- 4.271s: `/vendor/etc/cgroups.json` does not exist; SetupCgroups fails.
- 4.278s onward: `createProcessGroup(0, ...)` fails for critical `ueventd`.
- 24.314s: critical process exited four times; InitFatalReboot signal 6.
- Reboot target is recovery, explaining the repeating loop.

The active boot partition dump has SHA256
`fef2239a6456e36cf3ac769d1b7331e6a1e65909f048b345e8b96b78315319b0`.
Its actual recovery ramdisk contains `ro.vendor.gm8.legacy_cgroups=true`,
but neither vendor cgroups nor task-profiles JSON. The SDK33 system/core
patch deliberately reads this authoritative pair when that property is true.
The normal vendor partition copies therefore cannot serve recovery's early
SetupCgroups action, which runs before any recovery init.rc workaround.

## Permanent source change

Install both existing source configs as selected ETC modules into
`$(TARGET_RECOVERY_ROOT_OUT)/vendor/etc`. Keep the normal vendor copies and
the existing cgroup-v1 process tracking. Do not alter critical-service handling,
SELinux, ADB authentication, credentials, partition layout or cgroup success
semantics. The firstboot verifier now checks the actual compressed boot
ramdisk for both regular policy files, exact source bytes and the v1 property.
An incomplete signed candidate cannot be published by that packaging path.

## Validation and remaining limits

- Firstboot/signing/payload fixture suite: 27 tests passed.
- Boot repair tests: preservation of existing file bytes, modes, links, kernel,
  load addresses and cmdline; correct boot ID; rejects wrong hash, corruption,
  nonzero signature/footer, truncation, existing-policy collision and parent
  symlink.
- Repaired the supplied actual boot dump by adding only `vendor/etc` and the
  paired JSON files. All 416 existing CPIO entries were preserved. Kernel
  SHA256 is `b9feda8e1f8a6cc5af79a7a05098d3b519279b2e735421fe111de40a301631ec`.
- Test image SHA256:
  `5977c2e30f8de04b0e7dc21a0fbb22ddae7726b6205868ab4db1f9a293ade142`.
- Recovery UI, mount/decryption and sideload still require physical-device
  testing. Passing host tests is not proof that every recovery feature works.

The new live capture also shows SyntheticPassword initialization, credential
verification/unlock completion and fingerprint authentication. Both patched
time IPC hashes match. No previous accept-error/importKey hang was found.
The qseecomd SIGTERM occurs during requested reboot, not the prior runtime
failure. This successful run does not establish long-term stability.

The WiFi missing `TS_DUTY_CYCLE` errors remain despite the property being true.
The active HAL/source path needs confirmation; it is not marked fixed.
The mm-pp-dpps/blank_screen failures at shutdown and Google TTS direct-boot
failure also remain separate findings; no speculative binary patch is applied.

## Test without a full Android build

Use `tools/make-recovery-cgroup-test.py INPUT OUTPUT --input-sha256 HASH` on
an unsigned v0/2048 GM8 dump with the missing policy pair. It refuses signed
or unknown tails and never writes a partition. The resulting image is for
`fastboot boot` testing, not a replacement OTA or an instruction to flash.
This uses exactly the policy content installed by the permanent source fix.

From manual fastboot, with the prepared test file in platform-tools:

```powershell
.\fastboot.exe devices
.\fastboot.exe boot .\gm8-recovery-cgroup-test-boot.img
```

Check for the recovery UI rather than the repeated logo. If Android opens,
that is a normal-mode boot and does not verify recovery. Once recovery is up,
Reboot System should return to Android without formatting anything. ADB is
only used after a recovery environment actually exposes it, never assumed
available in the early critical-service boot loop.

## Next complete build

```bash
sudo docker start gm8-build >/dev/null &&
sudo docker exec -it --user builder gm8-build bash -lc '
set -euo pipefail
cd /home/builder/android/lineage-20.0
git -C kernel/gm/msm8937 pull --ff-only https://github.com/milhany/android_kernel_gm_msm8937.git lineage-20.0-qsee-audit
git -C device/gm/GM8_sprout pull --ff-only https://github.com/milhany/android_device_gm_GM8_sprout.git lineage-20.0-qsee-audit
bash device/gm/GM8_sprout/tools/build-20.0.sh runtime
bash device/gm/GM8_sprout/tools/make-firstboot-20.0.sh "$PWD/out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates/lineage_GM8_sprout-target_files-eng.builder.zip"
'
```

Kernel/build/signing hardware validation is performed in the owner's build
container; no full Android build was available in this analysis workspace.
