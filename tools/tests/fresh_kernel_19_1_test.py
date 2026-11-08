#!/usr/bin/env python3
"""Run the SDK32 build helper against disposable tool/build fixtures."""
import os
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[1] / 'build-19.1.sh'


def case(stage, fault=''):
    with tempfile.TemporaryDirectory(prefix='gm8-fresh19-') as temp:
        top = Path(temp) / 'lineage-19.1'
        tools = top / 'device/gm/GM8_sprout/tools'
        tools.mkdir(parents=True)
        # Replace only the external depmod-presence fixture path; retain the
        # real stage, cleanup, failure and build-order logic verbatim.
        source = SOURCE.read_text().replace('/sbin/depmod', str(top / 'mock-depmod'))
        (tools / 'build-19.1.sh').write_text(source)
        for rel in ['build/core/version_defaults.mk', 'device/gm/GM8_sprout/setup-gapps.sh',
                    'device/gm/GM8_sprout/configs/powerhint.json',
                    'device/gm/GM8_sprout/power-libperfmgr/hidl/Power.cpp',
                    'device/gm/GM8_sprout/tools/tests/ft8006_gesture_test.py',
                    'device/gm/GM8_sprout/tools/tests/qsee_wait_test.py',
                    'device/gm/GM8_sprout/tools/tests/qsee_host.c',
                    'kernel/gm/msm8937/drivers/misc/qseecom.c',
                    'kernel/gm/msm8937/drivers/input/touchscreen/ft8006/focaltech_core.c',
                    'kernel/gm/msm8937/drivers/input/touchscreen/ft8006/focaltech_core.h',
                    'kernel/gm/msm8937/drivers/input/touchscreen/ft8006/focaltech_gesture.c',
                    'vendor/gm/GM8_sprout/proprietary/vendor/etc/init/android.hardware.gnss@2.0-service-qti.rc']:
            p = top / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('fixture\n')
        (top / 'build/core/version_defaults.mk').write_text('PLATFORM_SDK_VERSION := 32\n')
        (top / 'device/gm/GM8_sprout/setup-gapps.sh').write_text('exit 0\n')
        (top / 'mock-depmod').write_text('#!/bin/sh\nexit 0\n')
        (top / 'mock-depmod').chmod(0o755)
        out = top / 'out/target/product/GM8_sprout'
        cache = out / 'obj/KERNEL_OBJ'
        cache.mkdir(parents=True)
        (cache / 'old-object').write_text('old cache\n')
        for name in ('kernel', 'boot.img', 'keep-android-output'):
            (out / name).write_text('original\n')
        keys = top.parent / 'gm8-signing/keys'
        keys.mkdir(parents=True)
        (keys / 'fixture-private-key').write_text('do not touch\n')
        previous = top.parent / 'previous-release.zip'
        previous.write_text('keep previous release\n')
        commands = top / 'mock-bin'
        commands.mkdir()
        bodies = {
            'repo': '#!/bin/sh\nexit 0\n',
            'git': '#!/bin/sh\nexit 0\n',
            'python3': '#!/bin/sh\ncase "$*" in *ft8006_gesture_test.py*) [ "$GM8_TEST_FAULT" != host ] || exit 1;; esac\nexit 0\n',
        }
        for name, body in bodies.items():
            p = commands / name
            p.write_text(body)
            p.chmod(0o755)
        (top / 'build/envsetup.sh').write_text(r'''
lunch() { return 0; }
get_build_var() { echo out/target/product/GM8_sprout; }
m() {
    echo "$*" >> "$GM8_TEST_CALLS"
    if [[ "$1" == nothing && "$GM8_TEST_FAULT" == nothing ]]; then return 1; fi
    if [[ "$1" == bootimage ]]; then
        mkdir -p out/target/product/GM8_sprout/obj/KERNEL_OBJ
        touch out/target/product/GM8_sprout/obj/KERNEL_OBJ/new-object
    fi
}
''')
        calls = top / 'calls.txt'
        env = dict(os.environ, PATH=str(commands) + ':' + os.environ['PATH'],
                   GM8_TEST_CALLS=str(calls), GM8_TEST_FAULT=fault,
                   OUT_DIR='custom-out' if fault == 'out' else 'out',
                   OUT_DIR_COMMON_BASE='')
        result = subprocess.run(['bash', str(tools / 'build-19.1.sh'), stage, 'user'],
                                env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert (result.returncode == 0) == (not fault), result.stdout
        logs = calls.read_text().splitlines() if calls.exists() else []
        rebuilt = not fault and stage != 'check'
        assert (cache / 'old-object').exists() != rebuilt, result.stdout
        assert (cache / 'new-object').exists() == rebuilt, result.stdout
        assert (out / 'keep-android-output').read_text() == 'original\n'
        assert (keys / 'fixture-private-key').read_text() == 'do not touch\n'
        assert previous.read_text() == 'keep previous release\n'
        if rebuilt:
            assert logs[0] == 'nothing -j32' and logs[1] == 'bootimage -j32', logs
        elif stage == 'check' or fault:
            assert not any(x.startswith('bootimage') for x in logs), logs
        print('PASS:', stage, fault or 'success', '— kernel cleanup gate and unrelated outputs/keys preserved')


for stage, fault in [('check', ''), ('boot', ''), ('rom', ''), ('target-files', ''),
                     ('target-files', 'nothing'), ('target-files', 'host'), ('target-files', 'out')]:
    case(stage, fault)
