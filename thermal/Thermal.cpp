// SPDX-License-Identifier: Apache-2.0
#include <hardware/thermal.h>

#include <algorithm>
#include <cerrno>
#include <cmath>

#include "Sensors.h"

namespace {
ssize_t GetTemperatures(thermal_module_t*, temperature_t* list, size_t size) {
    if (!list) return gm8::Temperatures{}.size();
    const auto temperatures = gm8::ReadTemperatures();
    bool valid = false;
    for (size_t i = 0; i < temperatures.size(); ++i) {
        valid |= std::isfinite(temperatures[i].celsius);
        if (i >= size) continue;
        const auto& sensor = temperatures[i];
        auto& output = list[i];
        output = {};
        output.name = sensor.name;
        switch (sensor.kind) {
            case gm8::SensorKind::Battery: output.type = DEVICE_TEMPERATURE_BATTERY; break;
            case gm8::SensorKind::Skin: output.type = DEVICE_TEMPERATURE_SKIN; break;
            default: output.type = DEVICE_TEMPERATURE_UNKNOWN; break;
        }
        output.current_value = std::isfinite(sensor.celsius)
                                       ? sensor.celsius : UNKNOWN_TEMPERATURE;
        // GM8's actual throttle/shutdown thresholds have not been verified.
        output.throttling_threshold = UNKNOWN_TEMPERATURE;
        output.shutdown_threshold = UNKNOWN_TEMPERATURE;
        output.vr_throttling_threshold = UNKNOWN_TEMPERATURE;
    }
    return valid ? static_cast<ssize_t>(temperatures.size()) : -ENODATA;
}

ssize_t GetCoolingDevices(thermal_module_t*, cooling_device_t*, size_t) {
    // Thermal HAL 1.0 represents fans (RPM), not CPU frequency cooling states.
    return 0;
}
hw_module_methods_t kMethods = {};
}  // namespace

extern "C" {
thermal_module_t HAL_MODULE_INFO_SYM = {
    .common = {
        .tag = HARDWARE_MODULE_TAG,
        .module_api_version = THERMAL_HARDWARE_MODULE_API_VERSION_0_1,
        .hal_api_version = HARDWARE_HAL_API_VERSION,
        .id = THERMAL_HARDWARE_MODULE_ID,
        .name = "GM8 thermal sensor reporting",
        .author = "GM8 maintainers",
        .methods = &kMethods,
        .dso = nullptr,
        .reserved = {},
    },
    .getTemperatures = GetTemperatures,
    .getCpuUsages = nullptr,
    .getCoolingDevices = GetCoolingDevices,
};
}
