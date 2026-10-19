// SPDX-License-Identifier: Apache-2.0
#include "Sensors.h"

#include <cassert>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>

namespace fs = std::filesystem;
int main() {
    char directory[] = "/tmp/gm8-thermal-XXXXXX";
    assert(mkdtemp(directory));
    const fs::path root(directory);
    auto zone = [&](int id, const std::string& type, const std::string& value) {
        const auto p = root / ("thermal_zone" + std::to_string(id));
        fs::create_directories(p);
        std::ofstream(p / "type") << type << '\n';
        std::ofstream(p / "temp") << value << '\n';
    };
    // Deliberately use different numbers from GM8's captured zone inventory.
    zone(91, "tsens_tz_sensor0", "43");
    zone(4, "battery", "32900");
    zone(22, "pm8937_tz", "41793");
    zone(0, "case_therm", "34");
    auto values = gm8::ReadTemperatures(root);
    assert(values.size() == 18);
    auto find = [&](const gm8::Temperatures& ts, const std::string& name) {
        for (const auto& t : ts) if (t.name == name) return t.celsius;
        std::abort();
    };
    assert(find(values, "tsens_tz_sensor0") == 43);
    assert(std::abs(find(values, "battery") - 32.9f) < .001f);
    assert(std::abs(find(values, "pm8937_tz") - 41.793f) < .001f);
    assert(find(values, "case_therm") == 34);
    assert(std::isnan(find(values, "tsens_tz_sensor10")));
    for (const auto* raw : {"", "nan", "inf", "41 garbage", "32767", "-273"}) {
        zone(91, "tsens_tz_sensor0", raw);
        auto next = gm8::ReadTemperatures(root);
        assert(std::isnan(find(next, "tsens_tz_sensor0")));
        for (size_t i = 0; i < values.size(); ++i)
            assert(std::string(values[i].name) == next[i].name);
    }
    zone(91, "tsens_tz_sensor0", "0");
    assert(find(gm8::ReadTemperatures(root), "tsens_tz_sensor0") == 0);
    fs::remove(root / "thermal_zone4" / "temp");
    assert(std::isnan(find(gm8::ReadTemperatures(root), "battery")));
    auto missing = gm8::ReadTemperatures(root / "missing");
    for (const auto& t : missing) assert(std::isnan(t.celsius));
    fs::remove_all(root);
}
