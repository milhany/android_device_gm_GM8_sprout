# GM8 LineageOS 19.1 stability port — 2026-11-08

Paired branch: `lineage-19.1-stability-20261108` in the device, kernel and
vendor repositories. This is an experimental source candidate, not a
hardware-validated or measured battery-life improvement.

## Port selection

| 17.1 candidate | 19.1 treatment |
| --- | --- |
| Legacy QSEE final listener close | Port the reviewed kernel change and actual-C regression tests; the base driver is byte-identical |
| FT8006 gesture/IRQ wake ownership | Port the per-device serialization, checked I2C retries and owned wake cleanup; the base drivers are byte-identical |
| GNSS init HIDL interface | Add the same missing `IGnss/default` mapping to the existing 2.0 init service |
| Android 10 camera_prop mapping | Do not port: 19.1 already has exact device-owned AE/debug property labels and its own camera policy |
| Build/test helpers | Integrate portable gesture/QSEE tests and fresh kernel/module rebuilding into the SDK32 helper; keep SDK32 variants, compatibility patches and signing tools |
| Android 10 framework/ART/LMKD/settings | Do not transplant across platform versions |

The paired kernel starts from `b0555eee97c41a59830d94134b4c882c75027220`.
Only the QSEE/touch files and documentation change. Existing 19.1 kernel
configuration and low-power/thermal behavior are retained. No 4.19 kernel
port, frequency/voltage change or blanket SELinux permission is included.

QSEE's observed close/wait cycle can leave native secure services stuck
across framework restarts. This candidate addresses final-close progress
in non-reentrant mode; it does not establish why the daemon exited or
modify explicit UNREGISTER ioctl/reentrant behavior. Real TZ acceptance
still needs a phone test. GNSS interface registration fixes init lookup,
not satellite reception, XTRA transfer or position accuracy.

## Battery source review

The existing PowerHAL already cancels interaction, launch and expensive
rendering hints when the screen becomes noninteractive, handles LOW_POWER,
and bounds launch hints to 750 ms. Configuration does not request forced
GPU rails/clocks or a 10-second GPU timer during launch. The high-priority
CPU/GPU defaults and their supported frequency tables are not changed by
this port.

FileNode closes the held PM-QoS descriptor when returning to the default
value. A `HoldFd=true` entry alone therefore does not prove a permanent
idle-latency request. The boot command line already omits the explicit
`lpm_levels.sleep_disabled=1` setting. These are source observations; they
do not prove that a particular installed build sleeps or consumes less.

The current thermal HAL reports sensors, and the absent thermal-engine
mitigation policy remains an open hardware verification item. Kernel and
firmware protection must not be inferred from a sensor-reporting HAL.
Neither lowering thermal limits nor suppressing warnings is used as a
battery fix.

The first comparison after a complete build/install should distinguish
screen-off residency and persistent wake requests from screen-on CPU/GPU,
modem/network and application activity. Keep brightness, SIM/network,
applications and charging conditions comparable. Application optimization
and first-boot work can distort an initial battery reading. No percentage
or battery-life gain is claimed before this comparison.

## Build and validation

Select all three paired sources in a separate SDK32 checkout. The existing
helper now runs the portable gesture and QSEE tests plus the existing
Power.cpp/InteractionHandler.cpp policy regression before Android build
generation, and records relevant source/configuration hashes. Non-check
stages rebuild KERNEL_OBJ and boot/kernel outputs after `m nothing` passes;
other Android outputs and previous release/signing files are preserved.
This workflow requires the standard out/ directory.

```sh
bash device/gm/GM8_sprout/tools/build-19.1.sh target-files user
```

This prepares target-files and matching otatools; it is not release signing
or installation. Use the existing 19.1 signing workflow and signing
identities after successful compilation. The 17.1 release helper is not
compatible with SDK32 and must not be copied into this checkout.

Host C fault-injection tests, strict compilation and ASAN/UBSAN checks
passed for the ported drivers. The existing actual-C++ power policy tests
also passed. Leak scanning was disabled in ASAN because LeakSanitizer is
incompatible with the preparation runtime's ptrace setup. Full Android/
ARM64 compilation, signing, boot, secure key operations, touch/suspend,
GPS and battery acceptance have not been performed here.

The fresh-kernel helper was exercised with disposable build/tool fixtures
for check, boot, ROM and target-files stages, failed source/build-generation
gates and custom-output refusal. Only the kernel cache/boot outputs were
cleaned after successful gates; unrelated outputs and fixture key/release
files were preserved. Those fixtures do not establish an Android build.
