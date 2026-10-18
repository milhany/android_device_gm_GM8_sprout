// SPDX-License-Identifier: Apache-2.0
// Host-link with Thermal.cpp (not Sensors.cpp) and Android 11 libhardware headers.
#include <hardware/thermal.h>
#include "Sensors.h"
#include <cassert>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <limits>

namespace gm8 {
Temperatures snapshot{};
Temperatures ReadTemperatures(const std::string&) { return snapshot; }
}
extern "C" thermal_module_t HAL_MODULE_INFO_SYM;
int main() {
    auto& module = HAL_MODULE_INFO_SYM;
    assert(module.common.tag == HARDWARE_MODULE_TAG);
    assert(std::strcmp(module.common.id, THERMAL_HARDWARE_MODULE_ID) == 0);
    assert(module.common.methods && !module.common.methods->open);
    const ssize_t count = module.getTemperatures(&module, nullptr, 0);
    assert(count == 18);
    for (auto& t : gm8::snapshot)
        t = {"missing", gm8::SensorKind::Unknown, std::numeric_limits<float>::quiet_NaN()};
    gm8::snapshot[0] = {"battery", gm8::SensorKind::Battery, 32.9f};
    gm8::snapshot[1] = {"case_therm", gm8::SensorKind::Skin, 34};
    temperature_t result[19]{};
    result[1].current_value = 777;
    assert(module.getTemperatures(&module, result, 1) == 18);
    assert(result[1].current_value == 777); // honor caller capacity
    assert(module.getTemperatures(&module, result, 19) == 18);
    assert(result[0].type == DEVICE_TEMPERATURE_BATTERY);
    assert(result[1].type == DEVICE_TEMPERATURE_SKIN);
    assert(result[2].type == DEVICE_TEMPERATURE_UNKNOWN);
    assert(result[2].current_value == UNKNOWN_TEMPERATURE);
    for (int i = 0; i < 18; ++i) {
        assert(result[i].throttling_threshold == UNKNOWN_TEMPERATURE);
        assert(result[i].shutdown_threshold == UNKNOWN_TEMPERATURE);
    }
    for (auto& t : gm8::snapshot) t.celsius = std::numeric_limits<float>::quiet_NaN();
    assert(module.getTemperatures(&module, result, 18) == -ENODATA);
    assert(module.getCoolingDevices(&module, nullptr, 0) == 0);
}
