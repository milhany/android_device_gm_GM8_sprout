#!/usr/bin/env python3
"""Pair SDK33 Java permission routing with the reviewed native socket backend."""
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
    if not version.is_file() or not re.search(r'^\s*PLATFORM_SDK_VERSION\s*:?=\s*33\s*$', version.read_text(), re.M):
        print('Expected Android 13 / SDK33; no files changed.', file=sys.stderr)
        return 1
    device = Path(__file__).resolve().parents[1]
    native = subprocess.run([sys.executable, str(device / 'tools/apply-socket-20.0.py'),
                             '--top', str(top), '--check'], text=True, capture_output=True)
    if native.returncode:
        print('Reviewed native socket backend is required; no files changed.\n' + native.stderr, file=sys.stderr)
        return 1
    policy = subprocess.run([sys.executable, str(device / 'tools/apply-network-policy-20.0.py'),
                             '--top', str(top), '--check'], text=True, capture_output=True)
    if policy.returncode:
        print('Reviewed Java/native policy baseline is required; no files changed.\n' + policy.stderr, file=sys.stderr)
        return 1
    source = top / 'packages/modules/Connectivity'
    patch = device / 'patches/sdk33/Connectivity/0003-gm8-legacy-permission-routing.patch'
    if not source.is_dir() or not patch.is_file():
        print('Missing SDK33 permission source/patch; no files changed.', file=sys.stderr)
        return 1

    def apply(*flags):
        return subprocess.run(['git', 'apply', *flags, str(patch)], cwd=source,
                              text=True, capture_output=True)

    if apply('--reverse', '--check').returncode == 0:
        print('SDK33 Java-to-native legacy permission routing is already applied.')
        return 0
    checked = apply('--check')
    if checked.returncode:
        print('SDK33 permission source differs; no files changed.\n' + checked.stderr, file=sys.stderr)
        return 1
    if args.check:
        print('SDK33 Java permission route is not applied; no files changed.', file=sys.stderr)
        return 1
    result = apply()
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    print('SDK33 Java permission updates route to the native legacy appId table.')
    print('BPF startup, persistent accounting and real network/permission enforcement remain pending.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
