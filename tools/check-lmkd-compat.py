#!/usr/bin/env python3
"""Check the paired GM8 3.18 memcg/vmpressure candidate; never changes files."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ENABLED = ('CONFIG_CGROUPS', 'CONFIG_RESOURCE_COUNTERS', 'CONFIG_MEMCG',
           'CONFIG_MEMCG_SWAP', 'CONFIG_MEMCG_SWAP_ENABLED')
DISABLED = ('CONFIG_ANDROID_LOW_MEMORY_KILLER', 'CONFIG_MEMCG_KMEM')
PROPERTIES = {'ro.lmk.use_psi': 'false', 'ro.lmk.use_minfree_levels': 'true',
              'ro.config.per_app_memcg': 'false'}
LMKD_SHA256 = '85a4ebd8c8ccba17805db11de5657fabc8cc9f4faaa98bec636757368f979c1d'


def check_config(text, label, generated=False):
    errors = []
    for name in ENABLED + (('CONFIG_SWAP', 'CONFIG_EVENTFD') if generated else ()):
        if re.findall(r'^' + name + r'=(.*)$', text, re.M) != ['y']:
            errors.append(f'{label}: {name} must be built in')
    for name in DISABLED:
        if (re.findall(r'^# ' + name + r' is not set$', text, re.M) !=
                [f'# {name} is not set'] or
                re.search(r'^' + name + r'=', text, re.M)):
            errors.append(f'{label}: {name} must be explicitly disabled')
    return errors


def check(top, built=False, platform=True):
    errors = []
    device = top / 'device/gm/GM8_sprout'
    kernel = top / 'kernel/gm/msm8937'
    vendor = top / 'vendor/gm/GM8_sprout'
    config = kernel / 'arch/arm64/configs/msm8937-perf_defconfig'
    errors += check_config(config.read_text(), 'kernel defconfig')
    if built:
        generated = top / 'out/target/product/GM8_sprout/obj/KERNEL_OBJ/.config'
        errors += check_config(generated.read_text(), 'generated kernel .config', True)
    props = (device / 'system.prop').read_text()
    for name, value in PROPERTIES.items():
        if re.findall(r'^' + re.escape(name) + r'=(.*)$', props, re.M) != [value]:
            errors.append(f'Expected exactly one {name}={value}')
    cgroups = json.loads((device / 'configs/cgroups-gm8.json').read_text())['Cgroups']
    memory = [c for c in cgroups if c['Controller'] == 'memory']
    expected = {'Controller': 'memory', 'Path': '/dev/memcg', 'Mode': '0700',
                'UID': 'root', 'GID': 'system', 'Optional': False}
    if memory != [expected]:
        errors.append('Memory controller must be required at /dev/memcg')
    profiles = json.loads((device / 'configs/task-profiles-gm8.json').read_text())['Profiles']
    for name in ('LowMemoryUsage', 'HighMemoryUsage'):
        if [p for p in profiles if p['Name'] == name] != [{'Name': name, 'Actions': []}]:
            errors.append(f'{name} must not set shared memory-group limits/swappiness')
    init = (device / 'rootdir/etc/init.qcom.rc').read_text()
    if '/sys/fs/cgroup/memory/' in init:
        errors.append('Stale second memory hierarchy in vendor init')
    board = (device / 'BoardConfig.mk').read_text()
    if re.search(r'cgroup_disable=\S*memory|swapaccount=0', board):
        errors.append('Kernel command line disables memory/swap accounting')
    if 'configs/heap-gm8-pie.mk' in (device / 'device.mk').read_text():
        errors.append('Keep the stock-heap experiment separate from this candidate')
    postboot = (vendor / 'proprietary/vendor/bin/init.qcom.post_boot.sh').read_text()
    function = postboot.split('function configure_memory_parameters() {', 1)[1].split(
        'function enable_memory_features()', 1)[0]
    # The early return must precede the legacy KLMK/ALMK branches. Exact
    # function digests are recorded below after testing the paired vendor.
    if hashlib.sha256(function.encode()).hexdigest() != VENDOR_MEMORY_SHA256:
        errors.append('Vendor memory setup differs from the tested LMKD candidate')
    if platform:
        lmkd = top / 'system/memory/lmkd/lmkd.cpp'
        if hashlib.sha256(lmkd.read_bytes()).hexdigest() != LMKD_SHA256:
            errors.append('Expected unmodified AOSP android-12.1.0_r22 lmkd.cpp; review before mixing')
        runtime = (top / 'build/make/target/product/runtime_libart.mk').read_text()
        for name in ('dalvik.vm.madvise.vdexfile.size', 'dalvik.vm.madvise.odexfile.size'):
            if re.findall(re.escape(name) + r'=(\d+)', runtime) != ['104857600']:
                errors.append('Restore the separate ART prefetch experiment before this test')
    return errors


# Filled from the actual vendor function, not the whole proprietary file.
VENDOR_MEMORY_SHA256 = '4527229c20c1ab1f4185b72df42429f1a7a24f7ef3d33f89f5122404fe06350a'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--built', action='store_true', help='also require generated KERNEL_OBJ/.config')
    parser.add_argument('--source-only', action='store_true', help='skip platform source identity checks')
    args = parser.parse_args()
    try:
        errors = check(args.top.resolve(), args.built, not args.source_only)
    except (OSError, KeyError, ValueError, IndexError) as error:
        errors = [str(error)]
    if errors:
        parser.exit(1, '\n'.join('ERROR: ' + e for e in errors) + '\n')
    print('PASS: paired GM8 memcg/vmpressure sources' + (' and generated kernel config' if args.built else ''))
    print('This does not prove boot, pressure event delivery or acceptable performance on hardware.')


if __name__ == '__main__':
    main()
