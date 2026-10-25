#!/usr/bin/env python3
"""Host checks of the actual touch selector/FT identification and compiled DT.

GPIO, pinctrl and I2C are substituted. No physical touch or suspend/wake test
is performed, and no controller firmware is loaded or programmed.
"""
import argparse
import re
from pathlib import Path
import subprocess
import tempfile


def extract(text, name):
    match = re.search(r"(?:static )?(?:enum gm8_touch_vendor|int) " + name + r"\([^;]+?\n\{", text)
    if not match:
        raise ValueError(f"Function missing: {name}")
    end, depth = match.end(), 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[match.start():end]


def compile_run(text, includes=()):
    with tempfile.TemporaryDirectory(prefix="gm8-touch-test-") as directory:
        source = Path(directory) / "test.c"
        binary = Path(directory) / "test"
        source.write_text(text)
        subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Werror", *includes,
                        str(source), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


def selector(kernel):
    root = kernel / "drivers/input/touchscreen/gm8"
    header = (root / "gm8-touch-board.h").read_text()
    enums = re.search(r"enum gm8_touch_vendor\s*\{[^}]+\};", header).group()
    actual = (root / "gm8-touch-board.c").read_text()
    funcs = extract(actual, "gm8_touch_from_panel_ids") + "\n" + extract(actual, "gm8_touch_prepare")
    harness = r'''
#include <assert.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#define EPROBE_DEFER 517
#define GPIOD_IN 0
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define dev_info(...) ((void)0)
ENUMS
struct device {};
struct gpio_desc { int index; };
struct pinctrl {};
struct pinctrl_state {};
static int lock, gm8_panel_id_lock;
static int values[2], fail_get, gets, puts_count, selects;
static struct gpio_desc descriptors[2] = {{0}, {1}};
static struct pinctrl controller;
static struct pinctrl_state state;
static void mutex_lock(int *p) { assert(!lock); lock = 1; }
static void mutex_unlock(int *p) { assert(lock); lock = 0; }
static struct gpio_desc *gpiod_get_index(struct device *d, const char *name, int index, int mode) {
    assert(!strcmp(name, "panel-id") && mode == GPIOD_IN);
    gets++;
    return fail_get == index ? (void *)(intptr_t)-EPROBE_DEFER : &descriptors[index];
}
static int gpiod_get_value_cansleep(struct gpio_desc *d) { return values[d->index]; }
static void gpiod_put(struct gpio_desc *d) { puts_count++; }
static struct pinctrl *devm_pinctrl_get(struct device *d) { return &controller; }
static struct pinctrl_state *pinctrl_lookup_state(struct pinctrl *p, const char *name) {
    assert(!strcmp(name, "pmx_ts_active")); return &state;
}
static int pinctrl_select_state(struct pinctrl *p, struct pinctrl_state *s) { selects++; return 0; }
FUNCS
static void reset(int id0, int id1) {
    values[0] = id0; values[1] = id1; fail_get = -1; gets = puts_count = selects = 0;
}
int main(void) {
    struct device dev;
    for (int id0 = 0; id0 < 2; id0++) for (int id1 = 0; id1 < 2; id1++) {
        enum gm8_touch_vendor vendor = id0 && id1 ? GM8_TOUCH_FOCALTECH :
            id0 || id1 ? GM8_TOUCH_HIMAX : GM8_TOUCH_UNKNOWN;
        for (int requested = GM8_TOUCH_FOCALTECH; requested <= GM8_TOUCH_HIMAX; requested++) {
            reset(id0, id1);
            int ret = gm8_touch_prepare(&dev, requested);
            assert(ret == (requested == vendor ? 0 : -ENODEV));
            assert(gets == 2 && puts_count == 2 && !lock);
            assert(selects == (requested == vendor));
        }
    }
    reset(1,1); fail_get = 0;
    assert(gm8_touch_prepare(&dev, GM8_TOUCH_FOCALTECH) == -EPROBE_DEFER);
    assert(gets == 1 && !puts_count && !selects && !lock);
    reset(1,1); fail_get = 1;
    assert(gm8_touch_prepare(&dev, GM8_TOUCH_FOCALTECH) == -EPROBE_DEFER);
    assert(gets == 2 && puts_count == 1 && !selects && !lock);
    reset(-EIO,1);
    assert(gm8_touch_prepare(&dev, GM8_TOUCH_FOCALTECH) == -EIO);
    assert(puts_count == 2 && !selects && !lock);
    puts("PASS: actual panel-ID gating, GPIO release, deferred providers and read errors");
}
'''.replace("ENUMS", enums).replace("FUNCS", funcs)
    compile_run(harness)


def focaltech(kernel):
    root = kernel / "drivers/input/touchscreen/gm8/ft8006m"
    source = (root / "focaltech_core.c").read_text()
    defines = "\n".join(re.findall(r"^#define (?:INTERVAL_READ_REG|TIMEOUT_READ_REG)[^\n]+", source, re.M))
    funcs = extract(source, "fts_get_chip_types") + "\n" + extract(source, "fts_get_ic_information")
    harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#define KERN_INFO ""
#define KERN_ERR ""
#define printk(...) ((void)0)
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
#include "focaltech_common.h"
_Static_assert(FTS_AUTO_UPGRADE_EN == 0 && FTS_AUTO_LIC_UPGRADE_EN == 0, "firmware updates disabled");
_Static_assert(FTS_APK_NODE_EN == 0 && FTS_SYSFS_NODE_EN == 0 && FTS_TEST_EN == 0, "factory endpoints disabled");
DEFINES
struct i2c_client {};
struct fts_ts_data { struct ts_ic_info ic_info; struct i2c_client *client; };
static int high_id, low_id, read_error, writes;
static void msleep(int ms) {}
static int fts_i2c_read_reg(struct i2c_client *c, int reg, u8 *value) {
    *value = reg == FTS_REG_CHIP_ID ? high_id : low_id;
    return read_error;
}
static int __attribute__((unused)) fts_i2c_write(struct i2c_client *c, u8 *data, int count) {
    writes++; return 0;
}
static int __attribute__((unused)) fts_i2c_read(struct i2c_client *c, u8 *cmd, int count, u8 *out, int length) {
    writes++; return 0;
}
FUNCS
int main(void) {
    struct fts_ts_data data = {0};
    high_id = 0x80; low_id = 0x06;
    assert(!fts_get_ic_information(&data));
    assert(data.ic_info.ids.chip_idh == 0x80 && data.ic_info.ids.chip_idl == 0x06);
    assert(fts_get_chip_types(&data, 0x87, 0x16, VALID) == -ENODATA);
    assert(fts_get_chip_types(&data, 0, 0x06, VALID) == -EINVAL);
    high_id = 0x80; low_id = 0xC6;
    assert(fts_get_ic_information(&data) == -ENODEV && !writes);
    high_id = low_id = 0;
    assert(fts_get_ic_information(&data) == -ENODEV && !writes);
    read_error = -EIO;
    assert(fts_get_ic_information(&data) == -ENODEV && !writes);
    puts("PASS: actual FT8006M identification and invalid-firmware path without bootloader writes");
}
'''.replace("DEFINES", defines).replace("FUNCS", funcs)
    compile_run(harness, ["-I", str(root)])


def fdt(dtb, node, prop, kind="x"):
    value = subprocess.check_output(["fdtget", "-t", kind, str(dtb), node, prop], text=True).strip()
    return value.split() if kind == "s" else [int(cell, 16) for cell in value.split()]


def wiring(dtb):
    tlmm = fdt(dtb, "/soc/pinctrl@1000000", "phandle")[0]
    base = "/soc/i2c@78b7000/"
    for node, address, vendor in [("focaltech@38", 0x38, "focaltech"), ("himax@48", 0x48, "himax")]:
        path = base + node
        assert fdt(dtb, path, "reg") == [address]
        assert fdt(dtb, path, "panel-id-gpios") == [tlmm, 59, 0, tlmm, 27, 0]
        prop = "reset-gpio" if vendor == "focaltech" else "rst-gpio"
        assert fdt(dtb, path, vendor + "," + prop)[0:2] == [tlmm, 64]
        assert fdt(dtb, path, vendor + ",irq-gpio")[0:2] == [tlmm, 65]
        assert fdt(dtb, path, "pinctrl-names", "s")[0] == "pmx_ts_active"
    assert fdt(dtb, base + "focaltech@38", "focaltech,display-coords") == [0, 0, 720, 1440]
    assert fdt(dtb, base + "himax@48", "himax,panel-coords") == [0, 720, 0, 1440]
    print("PASS: compiled touch addresses, stock ID/reset/IRQ pins and display geometry")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--dtb", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    kernel = args.kernel.resolve()
    config = args.config.read_text().splitlines()
    for name in ("INPUT_TOUCHSCREEN", "GM8_TOUCH", "GM8_TOUCH_FOCALTECH", "GM8_TOUCH_HIMAX"):
        assert f"CONFIG_{name}=y" in config
    selector(kernel)
    focaltech(kernel)
    wiring(args.dtb.resolve())
    header = (kernel / "drivers/input/touchscreen/gm8/himax/himax_common.h").read_text()
    header = re.sub(r"/\*.*?\*/|//[^\n]*", "", header, flags=re.S)
    assert not re.search(r"^\s*#define\s+HX_AUTO_UPDATE_FW\b", header, re.M)
    assert "CONFIG_GM8_TOUCH_HIMAX_DEBUG=y" not in config
    assert not (kernel / "drivers/input/touchscreen/gm8/himax/himax_debug.c").exists()
    assert not (kernel / "drivers/input/touchscreen/gm8/ft8006m/focaltech_flash.c").exists()
    print("PASS: both touch variants enabled; automatic firmware and factory channels omitted")


if __name__ == "__main__":
    main()
