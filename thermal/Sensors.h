// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <array>
#include <string>

namespace gm8 {

enum class SensorKind { Unknown, Battery, Skin };
struct Temperature {
    const char* name;
    SensorKind kind;
    float celsius;
};

// Stable inventory from GM8's reported thermal-zone types. TSENS locations
// have not been mapped to individual CPU/GPU blocks, so retain Unknown.
using Temperatures = std::array<Temperature, 18>;
Temperatures ReadTemperatures(const std::string& root = "/sys/class/thermal");

}  // namespace gm8
