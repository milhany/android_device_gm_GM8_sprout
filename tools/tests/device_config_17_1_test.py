#!/usr/bin/env python3
"""Regress old heap, unsupported scheduler and Q policy/build mistakes."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('device_check', ROOT / 'tools/check-device-config-17.1.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.check(ROOT)


with tempfile.TemporaryDirectory(prefix='gm8-q-config-') as name:
    device = Path(name) / 'device'
    shutil.copytree(ROOT, device, ignore=shutil.ignore_patterns(
        '.git', 'checks', '__pycache__', 'bootanimation.zip'))

    def reject(path, change):
        target = device / path
        original = target.read_text()
        target.write_text(change(original))
        try:
            module.check(device)
        except ValueError:
            pass
        else:
            raise AssertionError('Bad config accepted: ' + path)
        finally:
            target.write_text(original)

    reject('configs/gm8-dalvik-heap.mk', lambda s: s.replace('heapmaxfree=8m', 'heapmaxfree=16m'))
    reject('device.mk', lambda s: s.replace('product_launched_with_o.mk)', 'product_launched_with_o_mr1.mk)'))
    reject('sepolicy/vendor/gm8_dolby_app.te', lambda s: s + '\nallow gm8_dolby_app window_service:service_manager find;\n')
    reject('hidl/perf/1.0/Android.bp', lambda s: s.replace('    gen_java:', '    vendor_available: true,\n    gen_java:'))
    reject('configs/powerhint.json', lambda s: s.replace('1401000', '9999999'))
    def reset_unowned_boost(source):
        data = json.loads(source)
        next(node for node in data['Nodes'] if node['Name'] == 'SchedBoost')['ResetOnInit'] = True
        return json.dumps(data)
    reject('configs/powerhint.json', reset_unowned_boost)
    reject('configs/task_profiles.json', lambda s: s.replace('HighPerformance', 'ProcessCapacityHigh'))
    reject('configs/task_profiles.json', lambda s: s.replace('"Actions": []', '"Actions": [{"Name":"JoinCgroup"}]', 1))
    reject('system.prop', lambda s: s + '\npm.dexopt.install=speed\n')
    module.check(device)

print('PASS: old heap/launch, forbidden window lookup, unsupported HIDL/frequency, task overrides and full-AOT regression checks')
