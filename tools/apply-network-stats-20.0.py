#!/usr/bin/env python3
"""Apply/check the SDK33 TrafficStats qtaguid read-side port without resetting local work."""
import argparse
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    top = args.top.resolve()
    version = top / 'build/core/version_defaults.mk'
    if not version.is_file() or not re.search(
            r'^\s*PLATFORM_SDK_VERSION\s*:?=\s*33\s*$', version.read_text(), re.M):
        print('Expected Android 13 / SDK33; no files changed.', file=sys.stderr)
        return 1
    project = top / 'packages/modules/Connectivity'
    source = project / 'service-t/jni/com_android_server_net_NetworkStatsService.cpp'
    patch = Path(__file__).resolve().parents[1] / 'patches/sdk33/Connectivity/0001-gm8-legacy-traffic-stats-readers.patch'
    if not source.is_file() or not patch.is_file():
        print('Missing SDK33 TrafficStats source or patch; no files changed.', file=sys.stderr)
        return 1

    def apply(*flags):
        return subprocess.run(['git', 'apply', *flags, str(patch)], cwd=project,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if apply('--reverse', '--check').returncode == 0:
        print('SDK33 GM8 TrafficStats read-side port is already applied.')
        return 0
    if args.check:
        print('SDK33 TrafficStats read-side port is missing or differs.', file=sys.stderr)
        return 1
    result = apply('--check')
    if result.returncode:
        print('Connectivity source differs; no files changed.\n' + result.stderr, file=sys.stderr)
        return 1
    result = apply()
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    print('Applied SDK33 GM8 TrafficStats readers; preserve this local Connectivity change across syncs.')
    print('Read-side only: BPF startup, accounting hooks, firewall, socket tagging and tethering ports remain open.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
