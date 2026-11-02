#!/usr/bin/env python3
"""Reject a GM8 Q boot build that lacks Android's cgroup controllers."""
import argparse
from pathlib import Path
import re


REQUIRED = (
    'ARM64', 'CGROUPS', 'CGROUP_CPUACCT', 'CGROUP_SCHED',
    'CPUSETS', 'PROC_PID_CPUSET', 'RESOURCE_COUNTERS',
    'MEMCG', 'MEMCG_SWAP', 'MEMCG_SWAP_ENABLED',
    'BLK_CGROUP', 'CFQ_GROUP_IOSCHED',
    'ANDROID_LOW_MEMORY_KILLER', 'SWAP', 'ZRAM',
)


def check(config):
    values = dict(re.findall(r'^CONFIG_(\w+)=(.*)$', config, re.M))
    missing = [name for name in REQUIRED if values.get(name) != 'y']
    if missing:
        raise ValueError('Required built-in kernel options missing: ' + ', '.join(missing))
    if values.get('MEMCG_KMEM', 'n') != 'n':
        raise ValueError('Keep legacy MEMCG_KMEM disabled')
    if any(values.get(name, 'n') != 'n' for name in ('SCHED_TUNE', 'CGROUP_SCHEDTUNE')):
        raise ValueError('SchedTune is not integrated with this kernel\'s QHMP scheduler')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    try:
        check(args.config.read_text())
    except (OSError, ValueError) as error:
        parser.exit(1, f'Kernel controller check failed: {error}\n')
    print('PASS: built kernel config supports Q task, memory and I/O groups; legacy LMK retained')
    print('Bootability, mounted controllers and runtime performance still need device testing.')


if __name__ == '__main__':
    main()
