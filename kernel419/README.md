# GM8 4.19 board-port checkpoint

Status: **compiles; selected legacy vendor UAPIs audited; not boot-tested or flash-ready**. This is a separate
standalone port experiment. The normal ROM still selects its working 3.18
kernel, defconfig, compiler and compatibility matrix.

## Pinned sources

* Base: LineageOS/android_kernel_xiaomi_msm8937, `lineage-22.2`,
  `e24963ba7e7376ad052179723a22b316e73af7d9`, Linux **4.19.325**.
* GM8 board reference: milhany/android_kernel_gm_msm8937,
  `lineage-19.1-qsee-diag`, `44e09019575c012ad5b332250261d162ea5835d5`.
* `board-provenance.json` records the original hashes of imported board/panel
  files before adaptation and whitespace cleanup. Existing copyright and
  licensing notices remain in the patch.

The Xiaomi `lineage-19.1` branch is 4.9, not 4.19. Do not substitute it or
the current default branch for the pinned base.

## Implemented

* Separate `CONFIG_MACH_GM_GM8`, normalized `gm8_defconfig` and GM8 DTB target.
* Imported the real MSM8940 / L2300 GM8 board, panel and peripheral wiring,
  retaining the 4.19 SoC/PMIC definitions. This is not an unmodified Xiaomi DTB.
* Preserved selectors: MSM ID `<313 0>`, board `<8 0>`, PMIC `<0x10019 0 0 0>`.
* Restored BLSP1 QUP1 at **0x78b5000** for the TPS65132 panel-bias chip.
  Moving it to QUP2 would address a different physical controller.
* Converted GCC/RPM clock and analog/digital codec references. The obsolete
  board-level sound platform/CPU overrides now inherit the 4.19 graph.
  This only resolves the graph; it does not validate sound or TAS2560.
* Retained stock display command sequences and BQ charger/gauge DT settings.
* Preserved GM8's external-firmware reservation at **0x84a00000 / 30 MiB**;
  the base tree otherwise reserves only 13 MiB at 0x85b00000. Checked modem,
  ADSP and WCNSS fixed regions against the original board.
* Added native DT-based ramoops at the existing diagnostic reservation
  **0x9ff00000 / 1 MiB**, with console, pmsg and record areas.
* Removed the unused exported `__init` CPR initialization symbol to resolve
  the build's section mismatch. Its `arch_initcall` remains in place.
* Disabled the generic reference FPC driver, whose matching compatible alone
  does not implement the GM8 power/detection and userspace contract.
* Enabled `CONFIG_ION_LEGACY` for the old allocation/share/import/free ABI and
  its 32-bit compat handler. This is a partial compatibility layer: the base
  implementation does not implement old `ION_IOC_SYNC` / `ION_IOC_CUSTOM`.
* Selected `CONFIG_MSMB_CAMERA_LEGACY` and disabled the modern camera build.
  The modern sensor-info structure grows `SUB_MODULE_MAX`, changing sensor
  config ioctl numbers and offsets. The legacy stack preserves the GM8 ABI.
* Preserved pre-4.12 ION allocation/fd fields inside legacy `msm_frame` using
  camera-local layouts copied from the pinned GM8 ION header. These fields
  must not inherit the current fd-based allocator's different structure.

## Remaining hardware gates

| Area | Required before a phone boot candidate |
| --- | --- |
| Charger / fuel gauge | Source port and host tests now pass for GM8 BQ2560x/BQ27426 plus USB supply. Hardware must still validate battery-ID voltage, temperature, charge limits, unplug/replug, suspend and regulator/IRQ behavior. Profile programming remains disabled. |
| Touch | GM8 FT8006M and Himax source ports now compile and pass host checks. Actual touch events, selected variant, cold boot, screen blank/resume and gesture wake still need phone validation. Firmware loading/programming is disabled. |
| Fingerprint | Port GM8 FPC and Sunwave GPIO/power/detection behavior, sysfs/proc ABI and wakeup handling. |
| GPU / memory | Common KGSL header layouts match; verify actual V415 driver behavior, heap availability, cache maintenance and the legacy ION operations used by the vendor binaries. |
| Audio / camera | Legacy camera header ABI now matches the audited GM8 structures. Still port/review sensor-specific changes and TAS2560, then validate actual camera/audio operation. |
| Video | Two metadata structures have appended fields; test the old codec libraries' handling of payload sizes before declaring compatibility. |
| Wi-Fi | Build the appropriate 4.19 WLAN driver/module and validate firmware, module signing and vendor HAL compatibility. A 3.18 module cannot be reused. |
| Other board devices | Review GPIO vibrator, AW LED variants and device-info dependencies. |
| ROM integration | Separate experimental BoardConfig/compiler/matrix selection; review boot arguments, FCM kernel requirements, DT selection and 64 MiB boot partition limit. |
| Hardware | Initial boot/pstore, charging and temperature protections, panel, touch, storage, suspend, modem, camera, audio, Wi-Fi and fingerprint tests. |

4.19 is itself an old kernel branch. A successful build does not establish
current security coverage, improved application speed or blob compatibility.
This checkpoint deliberately does not package an Android boot image or OTA.

## Validation on 2026-10-24

This section and `validation-20261024.json` describe the **initial** checkpoint,
whose patch hash is intentionally different from the current patch. The latest
source and build record are described below.

* Full ARM64 `Image.gz`, native GM8 `dtbs` and appended `Image.gz-dtb` builds
  passed with LLVM 18.1.3 and GNU cross-binutils. Build hashes are recorded in
  `validation-20261024.json`; generated kernel keys/timestamps can make a
  subsequent build's binary hashes differ.
* Defconfig was resolved by real Kconfig and normalized with `savedefconfig`.
* Patch replay against a clean index at the pinned base reproduced the exact
  complete candidate tree. `git diff --check` passed for the kernel changes.
* All 27 imported source hashes matched the pinned GM8 reference. Compiled old
  and new DTBs matched FT8006M command arrays, dimensions and reset timing,
  as well as checked charger voltage/current/thermal settings.
* The DTB checker passed the new DTB and rejected the old DTB. `prepare` rejected
  a checkout at the wrong upstream revision. The appended image was checked
  byte-for-byte against the built `Image.gz` plus the GM8 DTB.
* A verbose standalone modpost check passed after the CPR export fix. Some
  inherited upstream C compiler warnings remain; no warning suppression was
  added to hide them.
* The Docker recipe is provided for reproducing the LLVM 18 host packages;
  it has not itself been built here. Validation used those tools in a local
  Ubuntu 24.04 environment. No phone, Android boot-image or full-ROM validation
  has been performed for 4.19.

## Vendor ABI work and validation on 2026-10-25

`validation-20261025.json` records the preceding vendor-ABI patch, candidate tree,
full kernel/DTB build hashes and ABI audit. `abi-modern-baseline-20261025.json`
records the original modern camera stack; `abi-audit-20261025.json` records the
selected legacy stack after the ION field fix.

The audit compiles actual UAPI declarations with LLVM 18 for **ARMv7 and
AArch64**. It compares common ioctl values, named structure sizes/alignment
and named non-bitfield member offsets. It records missing requests/structures
and added/removed probes instead of silently treating them as compatible.
No driver is loaded. Compiler annotations are treated like exported UAPI;
the freestanding time structures come from kernel UAPI, not Android libc.
Pointer widths are asserted for both targets. A deliberately modified QSEE
header was detected through changed ioctl values, structure size and offsets
on both targets.

Results for the selected stack:

* KGSL: 456 common probes per target, no differences.
* QSEECom: 159 per target, no differences.
* Legacy camera v1, sensor, SDK, ISP, subdevice and postprocessing: 1783
  common probes per target, no differences and no removed probe fields.
* Supported legacy ION: 19 probes per target, no differences. Old sync/custom
  requests and `ion_custom_data` remain absent; binary usage must be checked.
* Video metadata: 172 per target, two size differences. Frame-QP payload grows
  4 to 20 bytes; output-crop payload grows 36 to 80 bytes. Existing member
  offsets are unchanged and fields are appended, which may be compatible for
  prefix readers but is not proof that the old codec libraries accept them.

These checks do **not** validate ioctl handler behavior, general enum values,
bitfield/anonymous layouts, proprietary binary call usage, secure firmware or
hardware operation. Matching KGSL/QSEECom headers is not a vendor certification.
Kernel, appended image and native GM8 DTB were rebuilt with the selected legacy
camera stack and 32-bit ION handler. Inherited legacy-camera VLA warnings remain.

## GM8 power port on 2026-10-25

The preceding power checkpoint is recorded in `validation-power-20261025.json`.
`power-provenance-20261025.json` identifies every imported power source and the
three byte-identical GM8 gauge calibration images. This is a **source port with
compile/host checks**, not confirmation that charging works on the phone.

Implemented:

* GM8-specific BQ2560x charger and BQ27426 gauge, independent of Xiaomi machine
  detection. The original charger policy, JEITA thresholds, adapter fallback
  and monotonically decreasing thermal mitigation are retained.
* Converted power-supply descriptors/callbacks, regulator registration, wakeup
  sources, alarm API and managed provider references to their 4.19 interfaces.
  IRQ/work lifetime is handled before power supplies and locks are removed.
* Replaced the removed `qpnp_get_vadc` API with the existing PM8937 IIO voltage
  channel `VADC_P_MUX2_1_1` (0x11). Removed the duplicate legacy ADC child node;
  the 4.19 ratiometric channel and its 1:1 prescaling are retained. Voltage is
  interpreted in microvolts, matching this QCOM VADC provider.
* Resolved the charge-enable pin through the TLMM phandle/GPIO 25 rather than
  assuming a global Linux GPIO number. Physical low enables the chip.
* Added the legacy `usb` power-supply/EXTCON bridge needed by `phy-msm-usb`,
  retaining deferred DP/DM regulator initialization to avoid a provider cycle.
  Charger/gauge continue to expose the `battery`/`bms` names used by userspace.
* Hold charging disabled at initialization until a valid temperature is read;
  sensor read failure disables charging instead of continuing with stale data.
  A userspace charging-enable request cannot clear temperature/JEITA blockers.
* Corrected power-supply reporting to microamp/microvolt/microamp-hour units.
  Charge-counter reporting uses measured remaining capacity instead of `1`.

The original driver chooses SCUD/NVT/Sunwoda images from measured resistance;
the legacy DT battery-type A/B strings did not select these images. That
mapping is preserved. `CONFIG_GM8_BQ27426_PROFILE_WRITE` defaults to **off**:
automatic gauge profile updates return without programming and the manual
update attribute returns `-EOPNOTSUPP`. Existing gauge calibration is kept.
The build helper also checks that profile programming remains disabled.

`tools/tests/test-gm8-power419.py` compiles the **actual** JEITA and battery-ID
functions in a host harness. I/O/notifications are substituted. Tests cover
hot/cold boundaries and hysteresis, warm/cool limits, read failure/recovery,
charging-enable blockers, 30/100/330 kOhm profile mapping and invalid ADC values.
It also checks compiled DT GPIO/ADC/USB phandles, the unique battery-ID channel,
unchanged thermal limits, calibration hashes and the disabled programming flag.
The full kernel, appended image and DTB build passed; a verbose modpost check
passed. These tests do not measure a real sensor, exercise I2C/register writes
or establish actual charging safety. Those remain hardware gates.

### Upgrade the already-built v2 checkout

`prepare` can upgrade the **exact d06c76c checkpoint** in place using
`upgrades/d06c76c-power.patch`. It reconstructs and checks that baseline before
changing source files, checks the patch against both index and working tree,
and verifies the final cumulative patch. Unrecognized/conflicting modifications
are rejected without a reset. Fresh preparation still applies the cumulative
patch directly. Exact upgrade, repeat preparation and rejection of a modified
checkout were tested. Existing output can be reused for an incremental build.

After updating the tools checkout to this branch, run on the Ubuntu host:

```sh
set -o pipefail
sudo docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$HOME/android:/work" \
  -v "$HOME/android/gm8-kernel419-tools-v2:/port:ro" \
  gm8-kernel419-host prepare --source /work/gm8-kernel419-v2

sudo docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$HOME/android:/work" \
  -v "$HOME/android/gm8-kernel419-tools-v2:/port:ro" \
  gm8-kernel419-host build --source /work/gm8-kernel419-v2 \
  --out /work/out-gm8-kernel419-v2 --jobs 32 \
  2>&1 | tee "$HOME/android/gm8-kernel419-v2-power-build.log"
```

The existing host image already contains the host test dependencies. `build`
runs these tests after DTB verification and writes a new build record only
after they pass. No Android boot image is produced; Android boot-image
integration and hardware gates still remain before a phone candidate.

## GM8 touch port on 2026-10-25

The latest source/build record is `validation-touch-20261025.json`. Original
source hashes and the stock panel-ID reference are in
`touch-provenance-20261025.json`. Both actual GM8 variants are enabled:
FT8006M at I2C 0x38 and Himax at 0x48, with the original 720x1440 geometry,
TLMM reset 64 and IRQ 65. This is a **compile/host checkpoint**, not a report
that either panel has worked on a phone with 4.19.

The 3.18 MDSS driver read the panel-ID straps from TLMM **59 / 27**. Its
globals gated the touch drivers: 1/1 selected FocalTech, 0/1 or 1/0 selected
Himax. The new shared helper reads those pins through GPIO descriptors and
releases them before continuing. Reads are serialized. Unknown IDs and
ineligible drivers return without selecting the shared reset/IRQ pin state;
provider deferral and read errors propagate. Only the eligible driver selects
`pmx_ts_active`, then verifies the controller itself. This removes the old
dependencies on MDSS globals and the factory device-info helper.

Port details:

* Preserved FT8006M input, gesture, ESD and point-report paths; firmware and
  LCD-configuration updates, APK/raw-register factory nodes and production
  tests are disabled. No FT firmware binary or flash implementation is
  imported. If the existing firmware is not ready, identification fails
  without entering the bootloader or loading a replacement.
* Preserved Himax input/gesture paths with native wakeup sources. Automatic
  firmware updates are disabled and no firmware images/factory debug driver
  are imported. Small no-op logging hooks replace the raw/proc diagnostics,
  avoiding the stock unconditional per-IRQ timing output.
* Kept normal packet metadata available with diagnostics disabled. Point
  counts are checked against the existing 10-entry finger buffer before
  input/report allocation to reject invalid controller information.
* Corrected GPIO/probe error propagation, registered-input cleanup, work/IRQ
  teardown and delayed framebuffer notifier cleanup. The FocalTech gesture
  control now uses proper kobject attributes and reference release.

The stock input/gesture code is retained, but screen power sequencing and
gesture behavior with the 4.19 display driver remain hardware tests. The
factory/proc diagnostics are intentionally unavailable in this input port.

`tools/tests/test-gm8-touch419.py` compiles the **actual** board selector and FT
identification functions with GPIO/pinctrl/I2C substitutes. It checks all stock
ID combinations, ineligible-driver exclusion, descriptor release, deferred
providers and read errors. It checks valid/invalid FT identities and that
unready firmware does not cause bootloader writes. Compiled DT address,
GPIO/strap/state/geometry links and build policy are also checked. These tests
do not measure the pins, generate real touch events or validate suspend/wake.

The full kernel, appended image and GM8 DTB compile passed with the touch
variants; all four power and four touch check groups passed. Existing VLA and
debug-disabled unused-variable warnings are not suppressed. Matching these
checks still does not establish phone bootability or vendor compatibility.

### Upgrade the already-built power checkpoint

The helper recognizes the exact **9530763** power checkpoint and applies
`upgrades/9530763-touch.patch` in place. It also supports a direct upgrade from
the exact **d06c76c** checkpoint by composing both deltas. The index must match
a recognized baseline and tracked working files must be unchanged. A private
index reconstructs the baseline, then one checked patch updates the real
checkout. Conflicts and unrecognized changes are rejected without a reset.
Both upgrade paths, repeat preparation and conflict rejection were tested.

Update this tools checkout to the current branch and reuse the existing host
image, source and output paths:

```sh
set -o pipefail
sudo docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$HOME/android:/work" \
  -v "$HOME/android/gm8-kernel419-tools-v2:/port:ro" \
  gm8-kernel419-host prepare --source /work/gm8-kernel419-v2

sudo docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$HOME/android:/work" \
  -v "$HOME/android/gm8-kernel419-tools-v2:/port:ro" \
  gm8-kernel419-host build --source /work/gm8-kernel419-v2 \
  --out /work/out-gm8-kernel419-v2 --jobs 32 \
  2>&1 | tee "$HOME/android/gm8-kernel419-v2-touch-build.log"
```

Expect eight `PASS` groups after compilation. This still produces standalone
kernel/DTB artifacts. Android 12.1 boot-image/ramdisk/matrix integration is the
next step before a controlled first phone boot; no OTA or boot image is
packaged by this helper.

Reproduce the header audit in an environment with LLVM 18 and both kernel
source trees (including `include/uapi`, architecture UAPI and old staging ION
headers):

```sh
python3 tools/audit-kernel419-abi.py --old /path/to/gm8-kernel318 \
  --new ~/android/gm8-kernel419 --camera-stack legacy \
  --output /tmp/gm8-abi-audit.json
```

## Reproduce on the build server

Run these from the **Ubuntu host**, outside the existing Ubuntu 22.04 build
container. The separate Ubuntu 24.04 image supplies the tested LLVM 18 toolchain
and leaves the working ROM build environment intact.

```sh
git clone --single-branch --branch lineage-19.1-kernel419 \
  https://github.com/milhany/android_device_gm_GM8_sprout.git \
  "$HOME/android/gm8-kernel419-tools"

sudo docker build -t gm8-kernel419-host \
  "$HOME/android/gm8-kernel419-tools/kernel419"

sudo docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$HOME/android:/work" \
  -v "$HOME/android/gm8-kernel419-tools:/port:ro" \
  gm8-kernel419-host prepare --source /work/gm8-kernel419

set -o pipefail
sudo docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$HOME/android:/work" \
  -v "$HOME/android/gm8-kernel419-tools:/port:ro" \
  gm8-kernel419-host build \
  --source /work/gm8-kernel419 --out /work/out-gm8-kernel419 --jobs 32 \
  2>&1 | tee "$HOME/android/gm8-kernel419-build.log"
```

`prepare` clones the pinned base into a new directory and stages the patch for
inspection. It does not reset an existing checkout. An existing directory is
accepted if its HEAD matches the base and the cumulative patch can be reversed
cleanly, or if it matches a supported d06c76c/9530763 upgrade baseline.
Unrelated, conflicting or partially prepared checkouts fail instead of being
overwritten. For other older checkpoints, choose new source/output directories.

`build` uses out-of-tree output, checks host tools, applies the defconfig, builds
`Image.gz-dtb` and `dtbs`, validates board selectors and fixed firmware regions,
and writes `gm8-kernel419-build.json` with compiler and artifact hashes.
Compiler errors stop the command. This helper does not change Android sources,
create signing keys, package a boot image or access a phone.

On a host with the required LLVM 18 and cross-toolchain packages already
installed, the same operations are available directly:

```sh
python3 tools/kernel419.py prepare --source ~/android/gm8-kernel419
python3 tools/kernel419.py build --source ~/android/gm8-kernel419 \
  --out ~/android/out-gm8-kernel419 --llvm-bin /usr/lib/llvm-18/bin --jobs 32
```

Outputs on the host:

* `~/android/out-gm8-kernel419/arch/arm64/boot/Image.gz`
* `~/android/out-gm8-kernel419/arch/arm64/boot/Image.gz-dtb`
* `~/android/out-gm8-kernel419/arch/arm64/boot/dts/gm/gm8_sprout.dtb`
* `~/android/out-gm8-kernel419/gm8-kernel419-build.json`

Keep these as compile artifacts until the remaining hardware gates above are
implemented and reviewed. They are not an installable ROM.
