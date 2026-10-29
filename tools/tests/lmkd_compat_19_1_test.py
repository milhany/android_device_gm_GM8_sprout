#!/usr/bin/env python3
"""Reject incompatible source mixes using a temporary copy of the real candidate."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    parser.add_argument('--kernel-config', type=Path, required=True)
    args = parser.parse_args()
    helper = args.top / 'device/gm/GM8_sprout/tools/check-lmkd-compat.py'
    spec = importlib.util.spec_from_file_location('compat', helper)
    compat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compat)
    paths = [
        'kernel/gm/msm8937/arch/arm64/configs/msm8937-perf_defconfig',
        'vendor/gm/GM8_sprout/proprietary/vendor/bin/init.qcom.post_boot.sh',
    ] + ['device/gm/GM8_sprout/' + p for p in (
        'system.prop', 'configs/cgroups-gm8.json', 'configs/task-profiles-gm8.json',
        'rootdir/etc/init.qcom.rc', 'device.mk', 'BoardConfig.mk')]
    with tempfile.TemporaryDirectory() as directory:
        top = Path(directory)
        for name in paths:
            target = top / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.top / name, target)
        generated = top / 'out/target/product/GM8_sprout/obj/KERNEL_OBJ/.config'
        generated.parent.mkdir(parents=True)
        shutil.copyfile(args.kernel_config, generated)
        assert not compat.check(top, built=True, platform=False)

        def rejects(path, change):
            original = path.read_text()
            try:
                path.write_text(change(original))
                assert compat.check(top, built=True, platform=False), str(path)
            finally:
                path.write_text(original)

        rejects(generated, lambda s: s.replace('CONFIG_MEMCG=y', '# CONFIG_MEMCG is not set'))
        rejects(top / paths[0], lambda s: s.replace('# CONFIG_ANDROID_LOW_MEMORY_KILLER is not set',
                                                    'CONFIG_ANDROID_LOW_MEMORY_KILLER=y'))
        device = top / 'device/gm/GM8_sprout'
        rejects(device / 'system.prop', lambda s: s.replace('ro.lmk.use_psi=false', 'ro.lmk.use_psi=true'))
        rejects(device / 'configs/cgroups-gm8.json', lambda s: s.replace('"Optional": false', '"Optional": true'))

        def add_shared_limit(text):
            obj = json.loads(text)
            obj['Profiles'][-1]['Actions'] = [{'Name': 'SetAttribute', 'Params': {
                'Name': 'MemSoftLimit', 'Value': '16777216'}}]
            return json.dumps(obj)
        rejects(device / 'configs/task-profiles-gm8.json', add_shared_limit)
        rejects(top / paths[1], lambda s: s.replace('echo 0 > /sys/module/process_reclaim/parameters/enable_process_reclaim',
                                                   'echo 1 > /sys/module/process_reclaim/parameters/enable_process_reclaim'))
        generated.unlink()
        try:
            compat.check(top, built=True, platform=False)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Missing generated kernel config accepted')
    print('PASS: real candidate accepted; seven mixed/missing kernel, policy and vendor cases rejected')


if __name__ == '__main__':
    main()
