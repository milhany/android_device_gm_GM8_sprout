# GM8 Android 10 stock thermal HAL selection

The vendor tree supplies thermal.msm8937.so for both lib and lib64. The Q
hardware/qcom-caf/thermal/Android.mk also defines a source module installing
the same name/path. Even an unselected source module can define an install
rule, so removing a PRODUCT_PACKAGES entry is not the fix.

Use the existing Lineage Q device-specific path mechanism:
USE_DEVICE_SPECIFIC_THERMAL=true and DEVICE_SPECIFIC_THERMAL_PATH pointing
to device/gm/GM8_sprout/thermal. vendor/lineage/build/core/qcom_target.mk maps
qcom-thermal to that device path. The generic QCOM Android.mk's path guard
then skips its module definition. The device path documents that the provider
is the paired stock vendor copy list, not a second source module.

This deliberately preserves the stock HAL: the inspected generic Q
thermal_target.c table has no SoC ID 313. Silently replacing the stock HAL
with that implementation could yield an unsupported target and no sensors.

The two stock HAL copy entries, HIDL 1.0 wrapper/service, thermal-engine
binary/config and kernel thermal controls are retained. No sensor scaling,
trip point, throttle policy, charger policy or thermal-engine setting changes.
This does not prove a working mitigation policy; the existing empty-policy
preflight warning remains and hardware verification is still needed.

Host GNU Make fixtures used the real Q pathmap, selection helper and QCOM
thermal Android.mk: baseline selected the generic module, candidate skipped
it, and the entire inherited vendor copy list matched before/after. Exactly
one copy remained for each thermal ABI and for the engine/config. Python
syntax passed. A full Android build and actual temperature reporting are
not validated by this host test.
