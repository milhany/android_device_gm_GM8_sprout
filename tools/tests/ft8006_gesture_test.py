#!/usr/bin/env python3
"""Compile and exercise the candidate's actual gesture functions with mocked I/O.

This is a host fault-injection test, not a kernel or hardware boot test.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def function(source, name):
    match = re.search(r'^(?:static )?int ' + re.escape(name) + r'\([^;]*?\)\n\{', source, re.M)
    if not match:
        raise ValueError('Function not found: ' + name)
    start = match.start()
    pos = match.end()
    depth = 1
    while depth:
        if source[pos] == '{':
            depth += 1
        elif source[pos] == '}':
            depth -= 1
        pos += 1
    return source[start:pos]


PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
typedef unsigned char u8;
#define ENABLE 1
#define DISABLE 0
#define FTS_REG_GESTURE_EN 0xd0
#define ARRAY_SIZE(a) ((int)(sizeof(a) / sizeof((a)[0])))
#define FTS_ERROR(...) ((void)0)
#define FTS_FUNC_ENTER() ((void)0)
#define FTS_FUNC_EXIT() ((void)0)
struct mutex { int locked; };
struct fts_ts_data { struct mutex gesture_mutex; bool gesture_irq_wake; };
struct i2c_client { int irq; struct { struct { int unused; } kobj; } dev;
                    struct fts_ts_data *data; };
static int fts_gesture_group;
static int enables, disables, depth, write_fail, read_fail, stale_reads;
static int enable_fail, disable_fail, write_attempts, read_attempts, removed;
static int fail_reg = -1;
static u8 reg_value;
static void mutex_lock(struct mutex *m) { assert(!m->locked); m->locked=1; }
static void mutex_unlock(struct mutex *m) { assert(m->locked); m->locked=0; }
static void msleep(int ms) { (void)ms; }
static struct fts_ts_data *i2c_get_clientdata(struct i2c_client *c) { return c->data; }
static int fts_i2c_write_reg(struct i2c_client *c, u8 reg, u8 value) {
    assert(c->data->gesture_mutex.locked); write_attempts++;
    if (write_fail || reg == fail_reg) return -EREMOTEIO;
    if (reg == FTS_REG_GESTURE_EN) reg_value=value;
    return 1;
}
static int fts_i2c_read_reg(struct i2c_client *c, u8 reg, u8 *value) {
    assert(c->data->gesture_mutex.locked); (void)reg; read_attempts++;
    if (read_fail) return -EREMOTEIO; /* Do not fill value on failure. */
    *value=stale_reads ? !reg_value : reg_value;
    if (stale_reads > 0) stale_reads--;
    return 2;
}
static int enable_irq_wake(int irq) {
    assert(irq == 72); enables++;
    if (enable_fail) return -EIO;
    depth++; return 0;
}
static int disable_irq_wake(int irq) {
    assert(irq == 72); disables++;
    assert(depth == 1); /* Detect the original unbalanced-disable defect. */
    if (disable_fail) return -EIO;
    depth--; return 0;
}
static void sysfs_remove_group(void *kobj, void *group) {
    (void)kobj; (void)group; removed++;
}
static void reset(struct fts_ts_data *data) {
    assert(!data->gesture_mutex.locked);
    *data=(struct fts_ts_data){0};
    enables=disables=depth=write_fail=read_fail=stale_reads=0;
    enable_fail=disable_fail=write_attempts=read_attempts=removed=0;
    fail_reg=-1; reg_value=0;
}
'''

CASES = r'''
int main(void) {
    struct fts_ts_data data={0};
    struct i2c_client c={.irq=72, .data=&data};
    int reg;
    /* Normal suspend/resume; repeated resume and repeated suspend. */
    assert(fts_gesture_resume(&c)==0 && disables==0);
    assert(fts_gesture_suspend(&c)==0 && depth==1 && data.gesture_irq_wake);
    assert(fts_gesture_suspend(&c)==0 && enables==1 && depth==1);
    assert(fts_gesture_resume(&c)==0 && depth==0 && !data.gesture_irq_wake);
    assert(fts_gesture_resume(&c)==0 && disables==1);
    puts("PASS: normal and repeated suspend/resume balance IRQ wake ownership");

    reset(&data); read_fail=1;
    assert(fts_gesture_suspend(&c)==-EREMOTEIO && enables==0 && read_attempts==5);
    read_fail=0;
    assert(fts_gesture_resume(&c)==0 && disables==0);
    reset(&data); write_fail=1;
    assert(fts_gesture_suspend(&c)==-EREMOTEIO && enables==0 && write_attempts==5);
    assert(read_attempts==0);
    /* Each mask register and the mode register must propagate failure. */
    for (reg=0; reg<7; reg++) {
        int regs[]={0xd1,0xd2,0xd5,0xd6,0xd7,0xd8,0xd0};
        reset(&data); fail_reg=regs[reg];
        assert(fts_gesture_suspend(&c)==-EREMOTEIO && enables==0);
    }
    puts("PASS: read/write faults never become false success or acquire wake");

    reset(&data); stale_reads=4;
    assert(fts_gesture_suspend(&c)==0 && read_attempts==5 && enables==1);
    assert(fts_gesture_resume(&c)==0);
    reset(&data); stale_reads=5;
    assert(fts_gesture_suspend(&c)==-EIO && enables==0);
    puts("PASS: last retry succeeds; exhausted register mismatch fails");

    reset(&data); enable_fail=1;
    assert(fts_gesture_suspend(&c)==-EIO && !data.gesture_irq_wake && reg_value==0);
    assert(fts_gesture_resume(&c)==0 && disables==0);
    reset(&data);
    assert(fts_gesture_suspend(&c)==0);
    disable_fail=1;
    assert(fts_gesture_resume(&c)==-EIO && data.gesture_irq_wake && depth==1);
    assert(fts_gesture_suspend(&c)==0 && enables==1);
    disable_fail=0;
    assert(fts_gesture_resume(&c)==0 && depth==0);
    puts("PASS: failed IRQ operations preserve the actual reference ownership");

    reset(&data); assert(fts_gesture_suspend(&c)==0); read_fail=1;
    assert(fts_gesture_resume(&c)==-EREMOTEIO && depth==0 && disables==1);
    reset(&data); assert(fts_gesture_suspend(&c)==0); write_fail=1;
    assert(fts_gesture_resume(&c)==-EREMOTEIO && depth==0 && disables==1);
    puts("PASS: resume releases wake even when touch I2C is unavailable");

    reset(&data); assert(fts_gesture_exit(&c)==0 && disables==0 && removed==1);
    reset(&data); assert(fts_gesture_suspend(&c)==0);
    assert(fts_gesture_exit(&c)==0 && depth==0 && removed==1);
    assert(fts_gesture_exit(&c)==0 && disables==1);
    reset(&data); assert(fts_gesture_suspend(&c)==0); disable_fail=1;
    assert(fts_gesture_exit(&c)==-EIO && data.gesture_irq_wake);
    disable_fail=0; assert(fts_gesture_exit(&c)==0 && depth==0);
    puts("PASS: remove cleanup balances only an owned wake reference");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    args = parser.parse_args()
    root = args.kernel / 'drivers/input/touchscreen/ft8006'
    source = (root / 'focaltech_gesture.c').read_text()
    names = ('fts_gesture_set_state', 'fts_gesture_release_wake',
             'fts_gesture_suspend', 'fts_gesture_resume', 'fts_gesture_exit')
    code = PRELUDE + '\n'.join(function(source, name) for name in names) + CASES
    # Check integration outside the extracted functions, without compiling a fake driver.
    core = (root / 'focaltech_core.c').read_text()
    remove = function(core, 'fts_ts_remove')
    assert remove.index('fb_unregister_client') < remove.index('fts_gesture_exit(client)')
    assert remove.index('fts_gesture_exit(client)') < remove.index('free_irq(')
    assert 'mutex_init(&ts_data->gesture_mutex);' in core
    header = (root / 'focaltech_core.h').read_text()
    assert 'struct mutex gesture_mutex;' in header and 'bool gesture_irq_wake;' in header
    with tempfile.TemporaryDirectory(prefix='gm8-ft8006-') as tmp:
        unit = Path(tmp) / 'gesture_test.c'
        executable = Path(tmp) / 'gesture_test'
        unit.write_text(code)
        subprocess.run(['cc', '-std=gnu89', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-g', str(unit), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
    print('PASS: actual function bodies compiled with warnings as errors and UBSan')
    print('Hardware wake/touch/display behavior still requires the consolidated device test.')


if __name__ == '__main__':
    main()
