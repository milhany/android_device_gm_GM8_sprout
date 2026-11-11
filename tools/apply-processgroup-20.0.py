#!/usr/bin/env python3
"""Apply/check the reviewed SDK33 cgroup-v1 process-tracking port, preserving local edits."""
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
    repo = top / 'system/core'
    patch = Path(__file__).resolve().parents[1] / 'patches/sdk33/system_core/0001-gm8-cgroup-v1-process-tracking.patch'
    if not (repo / 'libprocessgroup/processgroup.cpp').is_file():
        print('Missing SDK33 processgroup source; no files changed.', file=sys.stderr)
        return 1

    def apply(*flags):
        return subprocess.run(['git', 'apply', *flags, str(patch)], cwd=repo,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if apply('--reverse', '--check').returncode == 0:
        print('SDK33 GM8 cgroup-v1 process-tracking port is already applied.')
        return 0
    if args.check:
        print('SDK33 GM8 processgroup port is missing or differs.', file=sys.stderr)
        return 1
    result = apply('--check')
    if result.returncode:
        print('SDK33 source differs; no files changed.\n' + result.stderr, file=sys.stderr)
        return 1
    result = apply()
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    print('Applied reviewed SDK33 GM8 processgroup port; preserve this local framework change across syncs.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
