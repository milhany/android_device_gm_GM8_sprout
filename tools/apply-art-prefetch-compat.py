#!/usr/bin/env python3
"""SDK 32 GM8 experiment: bound ODEX/VDEX startup prefetch, preserving demand paging."""
import argparse
from pathlib import Path
import re

STOCK = 104857600
BOUNDED = 16777216
PROPERTIES = ('dalvik.vm.madvise.vdexfile.size', 'dalvik.vm.madvise.odexfile.size')


def update(top, check=False, restore=False):
    top = Path(top).resolve()
    version = top / 'build/core/version_defaults.mk'
    if not version.is_file() or not re.search(
            r'^\s*PLATFORM_SDK_VERSION\s*:?=\s*32\s*$', version.read_text(), re.M):
        raise ValueError('GM8 ART prefetch trial requires Android 12.1 / SDK 32')
    source = top / 'build/make/target/product/runtime_libart.mk'
    original = source.read_text()
    changed = original
    desired = STOCK if restore else BOUNDED
    for name in PROPERTIES:
        pattern = re.compile(r'^(\s*' + re.escape(name) + r'=)(\d+)([ \t]*(?:\\)?[ \t]*)$', re.M)
        matches = list(pattern.finditer(changed))
        if len(matches) != 1 or int(matches[0][2]) not in (STOCK, BOUNDED):
            raise ValueError(f'Unexpected ART property definition; preserving the entire file: {name}')
        changed = pattern.sub(lambda m: m[1] + str(desired) + m[3], changed)
    if check and changed != original:
        raise ValueError('GM8 ART prefetch trial is not applied; run apply-art-prefetch-compat.py')
    if not check and changed != original:
        source.write_text(changed)
    print(f'GM8 ODEX/VDEX prefetch: {desired // 1048576} MiB per file; '
          'ART image limit, heap, compilation and demand paging unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, default=Path(__file__).resolve().parents[4])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--restore', action='store_true', help='restore only these two platform defaults')
    args = parser.parse_args()
    try:
        update(args.top, args.check, args.restore)
    except (OSError, ValueError) as error:
        parser.exit(1, f'ERROR: {error}\n')
