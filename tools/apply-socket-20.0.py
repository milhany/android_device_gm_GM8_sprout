#!/usr/bin/env python3
"""Apply the SDK33 native GM8 socket backend without discarding local edits."""
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
    source = top / 'system/netd'
    folder = device / 'patches/sdk33/system_netd'

    def apply(patch, *flags):
        return subprocess.run(['git', 'apply', *flags, str(patch)], cwd=source,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if not source.is_dir():
        print('Missing SDK33 netd source; no files changed.', file=sys.stderr)
        return 1
    for name in ('0001-gm8-legacy-uid-firewall.patch', '0002-gm8-legacy-bandwidth-policy.patch'):
        prior = folder / name
        if not prior.is_file() or apply(prior, '--reverse', '--check').returncode:
            print('Apply/check the reviewed SDK33 UID/bandwidth prerequisites first; no files changed.', file=sys.stderr)
            return 1
    patch = folder / '0003-gm8-legacy-socket-tagging.patch'
    if not patch.is_file():
        print('Missing SDK33 socket patch; no files changed.', file=sys.stderr)
        return 1
    if apply(patch, '--reverse', '--check').returncode == 0:
        print('SDK33 native legacy socket backend is already applied.')
        return 0
    checked = apply(patch, '--check')
    if checked.returncode:
        print('SDK33 netd differs; no files changed.\n' + checked.stderr, file=sys.stderr)
        return 1
    if args.check:
        print('SDK33 native socket backend is not applied; no files changed.', file=sys.stderr)
        return 1
    result = apply(patch)
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    print('SDK33 native appId permission table and qtaguid socket backend applied.')
    print('Java permission routing, BPF startup and real kernel/SELinux acceptance remain pending.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
