#!/usr/bin/env python3
"""Host tests of the actual GM8 JEITA decision function and compiled DT wiring.

The harness substitutes I/O and power-supply notifications. It tests decisions,
not charger register writes, ADC measurements or actual temperature protection.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile


def function(text, name):
    match = re.search(r"static (?:void|int) " + name + r"\([^;]+?\n\{", text)
    if not match:
        raise ValueError(f"Function not found: {name}")
    depth = 1
    end = match.end()
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[match.start():end]


def jeita(kernel):
    source = (kernel / "drivers/power/supply/gm8/bq2560x_charger.c").read_text()
    actual = function(source, "bq2560x_check_jeita") + "\n" + function(source, "bq2560x_charger_set_property")
    members = sorted(set(re.findall(r"bq->(\w+)", actual)))
    definitions = "\n".join(("void *" if name in {"dev", "batt_psy", "usb_psy"} else "int ") + name + ";"
                            for name in members)
    harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#define JEITA (1U << 1)
#define USER (1U << 0)
#define TEMP_FAULT (1U << 5)
#define POWER_SUPPLY_PROP_TEMP 0
#define POWER_SUPPLY_PROP_CHARGING_ENABLED 1
#define POWER_SUPPLY_PROP_SYSTEM_TEMP_LEVEL 2
#define dev_warn_ratelimited(...) ((void)0)
#define pr_info(...) ((void)0)
enum power_supply_property { unused_property = 0, charging_property = 1, system_temp_property = 2 };
struct power_supply {};
union power_supply_propval { int intval; };
struct bq2560x { MEMBERS };
static int temperature, read_error, Trickle_charge;
static void *power_supply_get_drvdata(struct power_supply *psy) { return psy; }
static int bq2560x_exit_hiz_mode(struct bq2560x *bq) { return 0; }
static int bq2560x_enter_hiz_mode(struct bq2560x *bq) { return 0; }
static int gm8_psy_set_online(void *psy, bool online) { return 0; }
static int bq2560x_system_temp_level_set(struct bq2560x *bq, int value) { return 0; }
static int bq2560x_get_batt_property(struct bq2560x *bq, int prop,
                                    union power_supply_propval *value) {
    value->intval = temperature;
    return read_error;
}
static void power_supply_changed(void *psy) {}
static int bq2560x_update_charging_profile(struct bq2560x *bq) { return 0; }
static int bq2560x_charging_disable(struct bq2560x *bq, int reason, int disable) {
    if (disable) bq->charging_disabled_status |= reason;
    else bq->charging_disabled_status &= ~reason;
    return 0;
}
ACTUAL
static struct bq2560x initial(void) {
    return (struct bq2560x) {
        .batt_temp = -EINVAL, .batt_hot_degc = 550, .batt_warm_degc = 450,
        .batt_cool_degc = 100, .batt_cool_xiaomi_degc = 100, .batt_cold_degc = 0,
        .hot_temp_hysteresis = 50, .cold_temp_hysteresis = 0,
        .batt_warm_ma = 900, .batt_cool_ma = 900, .batt_cool_xiaomi_ma = 900,
        .batt_warm_mv = 4400, .batt_cool_mv = 4400,
        .charging_disabled_status = TEMP_FAULT,
    };
}
static void sample(struct bq2560x *bq, int temp, int error) {
    temperature = temp; read_error = error; bq2560x_check_jeita(bq);
}
int main(void) {
    struct bq2560x bq = initial();
    sample(&bq, 250, 0);
    assert(!bq.jeita_active && !bq.charging_disabled_status);
    sample(&bq, 450, 0);
    assert(bq.batt_warm && bq.jeita_ma == 900 && bq.jeita_mv == 4400);
    sample(&bq, 550, 0);
    assert(bq.batt_hot && (bq.charging_disabled_status & JEITA));
    assert(!bq.jeita_ma && !bq.jeita_mv);
    sample(&bq, 520, 0);
    assert(bq.batt_hot && (bq.charging_disabled_status & JEITA));
    sample(&bq, 499, 0);
    assert(bq.batt_warm && !bq.batt_hot && !bq.charging_disabled_status);
    sample(&bq, -1, 0);
    assert(bq.batt_cold && (bq.charging_disabled_status & JEITA));
    sample(&bq, 0, 0);
    assert(bq.batt_cold && (bq.charging_disabled_status & JEITA));
    sample(&bq, 1, 0);
    assert(bq.batt_cool_xiaomi && !bq.batt_cold && bq.jeita_ma == 900);
    sample(&bq, 250, 0);
    assert(!bq.charging_disabled_status);
    sample(&bq, 250, -EIO);
    assert(bq.charging_disabled_status & TEMP_FAULT);
    sample(&bq, 250, 0);
    assert(!bq.charging_disabled_status);
    sample(&bq, 550, 0);
    sample(&bq, 550, -EIO);
    assert((bq.charging_disabled_status & (JEITA | TEMP_FAULT)) == (JEITA | TEMP_FAULT));
    sample(&bq, 550, 0);
    assert(bq.charging_disabled_status == JEITA);
    union power_supply_propval value = {.intval = 1};
    bq.charging_disabled_status |= TEMP_FAULT;
    assert(!bq2560x_charger_set_property((void *)&bq, POWER_SUPPLY_PROP_CHARGING_ENABLED, &value));
    assert(bq.charging_disabled_status == (JEITA | TEMP_FAULT));
    value.intval = 0;
    assert(!bq2560x_charger_set_property((void *)&bq, POWER_SUPPLY_PROP_CHARGING_ENABLED, &value));
    sample(&bq, 250, 0);
    assert(bq.charging_disabled_status == USER);
    value.intval = 1;
    assert(!bq2560x_charger_set_property((void *)&bq, POWER_SUPPLY_PROP_CHARGING_ENABLED, &value));
    assert(!bq.charging_disabled_status);
    puts("PASS: actual JEITA decisions, hot/cold hysteresis, temperature errors and recovery");
}
'''.replace("MEMBERS", definitions).replace("ACTUAL", actual)
    with tempfile.TemporaryDirectory(prefix="gm8-jeita-") as directory:
        code = Path(directory) / "test.c"
        executable = Path(directory) / "test"
        code.write_text(harness)
        subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Werror",
                        str(code), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)


def fdt(dtb, node, prop):
    return [int(value, 16) for value in subprocess.check_output(
        ["fdtget", "-t", "x", str(dtb), node, prop], text=True).split()]


def battery_id(kernel):
    source = (kernel / "drivers/power/supply/gm8/bq27426_fg.c").read_text()
    actual = function(source, "convert_rid2battid") + "\n" + function(source, "fg_parse_batt_id")
    harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
#define SMB_VTG_MIN_UV 1800000
#define SMB_VTG_MAX_UV 1800000
#define pr_err(...) ((void)0)
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define PTR_ERR(p) ((int)(intptr_t)(p))
struct device_node {};
struct device { struct device_node *of_node; };
struct bq_fg_chip {
    struct device *dev; void *vdd, *batt_id_chan;
    uint32_t connected_rid; int batt_id;
};
static int adc_uv, adc_error;
static void *devm_regulator_get(struct device *dev, const char *name) { return (void *)1; }
static int regulator_count_voltages(void *r) { return 1; }
static int regulator_set_voltage(void *r, int lo, int hi) { return 0; }
static int regulator_enable(void *r) { return 0; }
static void fg_disable_vdd(void *r) {}
static int devm_add_action_or_reset(struct device *d, void (*fn)(void *), void *p) { return 0; }
static int of_property_read_u32(struct device_node *node, const char *name, void *out) {
    *(int *)out = strstr(name, "vref") ? 1800000 : 68;
    return 0;
}
static int iio_read_channel_processed(void *channel, int *uv) { *uv = adc_uv; return adc_error; }
static int64_t div64_s64(int64_t a, int64_t b) { return a / b; }
ACTUAL
int main(void) {
    struct device dev = {0};
    struct bq_fg_chip bq = {.dev = &dev};
    adc_uv = 551020;
    assert(!fg_parse_batt_id(&bq) && bq.connected_rid == 30 && bq.batt_id == 0);
    adc_uv = 1071429;
    assert(!fg_parse_batt_id(&bq) && bq.connected_rid == 100 && bq.batt_id == 1);
    adc_uv = 1492462;
    assert(!fg_parse_batt_id(&bq) && bq.connected_rid == 330 && bq.batt_id == 2);
    adc_uv = 0;
    assert(fg_parse_batt_id(&bq) == -EINVAL);
    adc_uv = 1800000;
    assert(fg_parse_batt_id(&bq) == -EINVAL);
    adc_uv = -1;
    assert(fg_parse_batt_id(&bq) == -EINVAL);
    adc_uv = 551020; adc_error = -EIO;
    assert(fg_parse_batt_id(&bq) == -EIO);
    puts("PASS: actual battery-ID microvolt conversion, GM8 profile selection and ADC errors");
}
'''.replace("ACTUAL", actual)
    with tempfile.TemporaryDirectory(prefix="gm8-battery-id-") as directory:
        code = Path(directory) / "test.c"
        executable = Path(directory) / "test"
        code.write_text(harness)
        subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Werror",
                        str(code), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)


def dtb_checks(dtb):
    charger = "/soc/i2c@7af5000/bq2560x@6B"
    gauge = "/soc/i2c@7af5000/bq27426@55"
    tlmm = "/soc/pinctrl@1000000"
    bridge = "/soc/gm8-usb-power-supply"
    usb = "/soc/usb@78db000"
    adc = "/soc/qcom,spmi@200f000/qcom,pm8937@0/vadc@3100"
    assert fdt(dtb, charger, "ti,bq2560x,chip-enable-gpio") == [*fdt(dtb, tlmm, "phandle"), 25, 0]
    assert fdt(dtb, gauge, "io-channels") == [*fdt(dtb, adc, "phandle"), 0x11]
    assert fdt(dtb, usb, "extcon") == fdt(dtb, bridge, "phandle")
    assert fdt(dtb, bridge, "dpdm-supply") == fdt(dtb, usb, "phandle")
    children = subprocess.check_output(["fdtget", "-l", str(dtb), adc], text=True).split()
    assert sum(fdt(dtb, adc + "/" + node, "reg") == [0x11] for node in children) == 1
    assert fdt(dtb, charger, "qcom,thermal-mitigation") == [1980, 1500, 1000, 500, 0]
    print("PASS: compiled GPIO/ADC/USB links, unique battery-ID channel and stock thermal limits")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--dtb", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    jeita(args.kernel.resolve())
    battery_id(args.kernel.resolve())
    dtb_checks(args.dtb.resolve())
    config = args.config.read_text().splitlines()
    assert "CONFIG_GM8_POWER=y" in config
    assert "# CONFIG_GM8_BQ27426_PROFILE_WRITE is not set" in config
    metadata = Path(__file__).resolve().parents[2] / "kernel419/power-provenance-20261025.json"
    provenance = json.loads(metadata.read_text())
    for entry in provenance["files"]:
        if "bq27426_gmfs_" in entry["target"]:
            assert hashlib.sha256((args.kernel / entry["target"]).read_bytes()).hexdigest() == entry["source_sha256"]
    print("PASS: power enabled, profile programming disabled, GM8 calibration images byte-identical")


if __name__ == "__main__":
    main()
