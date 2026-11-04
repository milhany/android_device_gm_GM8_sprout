#!/usr/bin/env python3
"""Read-only checks for GM8-specific Q memory, power and policy source settings."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def check(device):
    spec = importlib.util.spec_from_file_location(
        'gm8_runtime_config', device / 'tools/check-runtime-17.1.py')
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    make = (device / 'device.mk').read_text()
    if ('product_launched_with_o.mk)' not in make or
            'phone-xhdpi-4096-dalvik-heap.mk' in make or
            'device/gm/GM8_sprout/configs/gm8-dalvik-heap.mk)' not in make):
        raise ValueError('GM8 requires its stock API-26 launch and 3 GiB heap profile')
    heap = (device / 'configs/gm8-dalvik-heap.mk').read_text()
    pairs = re.findall(r'\b(dalvik\.vm\.[\w.]+)=([^\s\\]+)', heap)
    expected = {k: v for k, v in runtime.HEAP_PROPERTIES.items() if k.startswith('dalvik.')}
    if len(pairs) != len(expected) or dict(pairs) != expected:
        raise ValueError('Heap settings differ from the captured GM8 stock policy')
    runtime.check_legacy_profiles(json.loads((device / 'configs/task_profiles.json').read_text()))
    framework = ET.parse(device / 'overlay/frameworks/base/core/res/res/values/config.xml').getroot()
    for tag, name, expected in (
            ('bool', 'config_dynamic_bind_ims', 'true'),
            ('string', 'config_ims_package', 'org.codeaurora.ims'),
            ('string', 'config_deviceConfiguratorPackageName', 'com.google.android.gms')):
        entries = framework.findall(f"{tag}[@name='{name}']")
        if len(entries) != 1 or (entries[0].text or '').strip() != expected:
            raise ValueError(f'GM8 framework override must set {name}={expected}')
    if 'configs/task_profiles.json:$(TARGET_COPY_OUT_VENDOR)/etc/task_profiles.json' not in make:
        raise ValueError('The legacy task-profile overrides are not installed')
    policy = (device / 'sepolicy/vendor/gm8_dolby_app.te').read_text()
    policy = '\n'.join(line.split('#', 1)[0] for line in policy.splitlines())
    if re.search(r'allow\s+gm8_dolby_app\s+window_service:service_manager', policy):
        raise ValueError('Direct window_service discovery violates the Q vendor-app neverallow')
    for path in device.rglob('Android.bp'):
        if re.search(r'\bsystem_ext_specific\s*:', path.read_text()):
            raise ValueError('Android 11-only system_ext_specific in ' + str(path))
    perf = (device / 'hidl/perf/1.0/Android.bp').read_text()
    if re.search(r'\bvendor_available\s*:', perf):
        raise ValueError('Q hidl_interface generates vendor variants without vendor_available input')
    for name in ('system.prop', 'vendor.prop'):
        for line in (device / name).read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                if key in runtime.HEAP_PROPERTIES and value != runtime.HEAP_PROPERTIES[key]:
                    raise ValueError('Conflicting GM8 ART setting: ' + line)
    boot_filters = re.findall(r'^pm\.dexopt\.boot=([^\s]+)$',
                              (device / 'system.prop').read_text(), re.MULTILINE)
    if boot_filters != ['quicken']:
        raise ValueError('GM8 Q update dexopt requires exactly one boot=quicken override')
    power = json.loads((device / 'configs/powerhint.json').read_text())
    nodes = {n['Name']: n for n in power['Nodes']}
    if len(nodes) != len(power['Nodes']):
        raise ValueError('Duplicate power-hint node')
    boost = nodes['SchedBoost']
    if (boost['Path'] != '/proc/sys/kernel/sched_boost' or
            boost['Values'] != ['1', '0'] or
            boost.get('DefaultIndex', 1) != 1 or boost.get('ResetOnInit') is not False):
        raise ValueError('QHMP boost is reference-counted: do not release an unowned boost on init')
    frequencies = {
        'cpu0': {'960000', '1094400', '1209600', '1248000', '1344000', '1401000'},
        'cpu4': {'768000', '902400', '998400', '1094400'},
    }
    for node in nodes.values():
        values = node['Values']
        if not values or not 0 <= node.get('DefaultIndex', len(values) - 1) < len(values):
            raise ValueError('Invalid power-hint default: ' + node['Name'])
        for cpu, supported in frequencies.items():
            if f'/{cpu}/cpufreq/scaling_' in node['Path'] and not set(values) <= supported:
                raise ValueError('Unsupported captured CPU frequency request: ' + node['Name'])
    for action in power['Actions']:
        if action['Value'] not in nodes[action['Node']]['Values'] or action['Duration'] < 0:
            raise ValueError('Invalid power-hint action: ' + str(action))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        check(args.device.resolve())
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        parser.exit(1, f'GM8 Q configuration check failed: {error}\n')
    print('PASS: GM8 Q stock heap/launch, dynamic IMS selection, legacy task profiles, CPU requests and policy/build constraints')
    print('Source checks do not establish hardware operation or measured performance.')


if __name__ == '__main__':
    main()
