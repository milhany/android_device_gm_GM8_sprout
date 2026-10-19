# GM8 temperature reporting

The stock `thermal.msm8937.so` identifies itself as a Default Thermal HAL. The
phone's Android 11 wrapper returns an empty sensor list and logs that its
temperature callback is not implemented, although sysfs reports 18 zones.

`thermal.gm8` supplies real readings to the existing Thermal HAL 1.0 wrapper.
`ro.hardware.thermal=gm8` selects it through libhardware's class-specific module
lookup. The wrapper/service and VINTF interface remain version 1.0; both module
ABIs are built. No vendor blobs, boot image, charging limits or thermal-engine
configuration are replaced by this reporting module.

The inventory is fixed by sensor **type name**, not thermal-zone number. Names
and order remain stable if a sensor is missing or unreadable. GM8 TSENS, XO,
case and PA ADC values are degrees C; PMIC/bms/battery values are millidegrees C.
Units are specified per type, not guessed from value magnitude. Missing,
malformed, non-finite or implausible readings are UNKNOWN_TEMPERATURE, never an
invented zero. If all readings fail, the module returns ENODATA.

Battery and case thermistors are reported as BATTERY and SKIN. Individual TSENS
locations have not been verified against CPU/GPU blocks; their actual names
are retained with UNKNOWN type. No CPU/GPU placement or throttle/shutdown
thresholds are fabricated. The version 1.0 cooling interface represents fan
RPM; GM8 has no fans, so it returns an empty list. CPU usage reporting is not
implemented by this module.

This fixes **sensor reporting**, not the whole mitigation stack. The empty
thermal-engine configuration warning is retained. Existing kernel/firmware
protection still needs hardware validation; no unverified cut-off temperatures
or new periodic polling/wakelocks are introduced.

The selected Qualcomm legacy-um policy already labels
`/devices/virtual/thermal` as sysfs_thermal. Device policy adds read-only access
for hal_thermal_default and sysfs directory/symlink traversal. It adds no write
permissions and does not duplicate the dependency's genfs label or daemon rules.

## Checks

```sh
g++ -std=c++17 -Wall -Wextra -Werror -Idevice/gm/GM8_sprout/thermal \
  device/gm/GM8_sprout/thermal/Sensors.cpp \
  device/gm/GM8_sprout/thermal/tests/sensors_test.cpp -o /tmp/gm8-sensors
/tmp/gm8-sensors
m thermal.gm8 -j32
```

Sensor fixtures cover captured GM8 units, renumbered zones, missing input,
malformed readings, stable inventory and real zero degrees. The legacy module
adapter was host-compiled/tested against Android 11 libhardware headers (including
bounded output arrays, unknown thresholds and all-sensor failure). Read-only
rules compile with neverallows enabled in an Android 11 policy reference; this
does not replace a full GM8 policy/Android build.

On the matching ROM, `adb shell dumpsys thermalservice` should show temperature
entries. Compare battery/case/TSENS values to sysfs. Check logcat for module-load
errors and AVCs; a permission failure requires the exact denied path/context.
An empty list or wrong conversion is a failed test, not a successful deployment.
