// SPDX-License-Identifier: Apache-2.0
#include "Sensors.h"

#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <dirent.h>
#include <fstream>
#include <limits>
#include <map>
#include <string>

namespace gm8 {
namespace {
struct Descriptor {
    const char* name;
    SensorKind kind;
    float divisor;
};

// This legacy kernel exposes TSENS/ADC values in degrees, but PMIC and
// battery sensors in millidegrees. Never infer units from the magnitude.
constexpr std::array<Descriptor, 18> kSensors = {{
    {"xo_therm", SensorKind::Unknown, 1},
    {"xo_therm_buf", SensorKind::Unknown, 1},
    {"case_therm", SensorKind::Skin, 1},
    {"tsens_tz_sensor0", SensorKind::Unknown, 1},
    {"tsens_tz_sensor1", SensorKind::Unknown, 1},
    {"tsens_tz_sensor2", SensorKind::Unknown, 1},
    {"tsens_tz_sensor3", SensorKind::Unknown, 1},
    {"tsens_tz_sensor4", SensorKind::Unknown, 1},
    {"tsens_tz_sensor5", SensorKind::Unknown, 1},
    {"tsens_tz_sensor6", SensorKind::Unknown, 1},
    {"tsens_tz_sensor7", SensorKind::Unknown, 1},
    {"tsens_tz_sensor8", SensorKind::Unknown, 1},
    {"tsens_tz_sensor9", SensorKind::Unknown, 1},
    {"tsens_tz_sensor10", SensorKind::Unknown, 1},
    {"pm8937_tz", SensorKind::Unknown, 1000},
    {"pa_therm0", SensorKind::Unknown, 1},
    {"bms", SensorKind::Battery, 1000},
    {"battery", SensorKind::Battery, 1000},
}};

std::string ReadLine(const std::string& path) {
    std::ifstream stream(path);
    std::string line;
    std::getline(stream, line);
    const auto end = line.find_last_not_of(" \t\r\n");
    return end == std::string::npos ? "" : line.substr(0, end + 1);
}

float ReadValue(const std::string& path, float divisor) {
    const std::string raw = ReadLine(path);
    char* end = nullptr;
    errno = 0;
    const float value = std::strtof(raw.c_str(), &end) / divisor;
    if (raw.empty() || end == raw.c_str() || *end != '\0' || errno ||
            !std::isfinite(value) || value < -40 || value > 150) {
        return std::numeric_limits<float>::quiet_NaN();
    }
    return value;
}
}  // namespace

Temperatures ReadTemperatures(const std::string& root) {
    std::map<std::string, std::string> zones;
    DIR* directory = opendir(root.c_str());
    if (directory) {
        while (dirent* entry = readdir(directory)) {
            const std::string name(entry->d_name);
            constexpr size_t prefix = sizeof("thermal_zone") - 1;
            if (name.compare(0, prefix, "thermal_zone") != 0 ||
                    name.size() == prefix ||
                    name.find_first_not_of("0123456789", prefix) != std::string::npos)
                continue;
            const std::string path = root + "/" + name;
            zones.emplace(ReadLine(path + "/type"), path + "/temp");
        }
        closedir(directory);
    }
    Temperatures result{};
    for (size_t i = 0; i < kSensors.size(); ++i) {
        const auto& sensor = kSensors[i];
        const auto found = zones.find(sensor.name);
        result[i] = {sensor.name, sensor.kind,
                     found == zones.end() ? std::numeric_limits<float>::quiet_NaN()
                                          : ReadValue(found->second, sensor.divisor)};
    }
    return result;
}
}  // namespace gm8
