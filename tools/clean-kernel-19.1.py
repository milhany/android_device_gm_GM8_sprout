#!/usr/bin/env python3
"""Remove only allowlisted GM8 build outputs, never kernel sources or ccache."""
import argparse
from pathlib import Path
import shutil

OUTPUTS = (
    'obj/KERNEL_OBJ', 'obj/RECOVERY_KERNEL_OBJ', 'obj/DTB_OBJ', 'obj/DTBO_OBJ',
    'obj/PACKAGING/kernel_modules_intermediates',
    'obj/PACKAGING/target_files_intermediates',
    'kernel', 'recovery-kernel', 'boot.img', 'recovery.img', 'dtb.img', 'dtbo.img',
)


def clean(top):
    top = Path(top).resolve(strict=True)
    if not (top / 'build/envsetup.sh').is_file() or not (top / 'kernel/gm/msm8937').is_dir():
        raise ValueError('Expected the GM8 Android source root')
    product = top / 'out/target/product/GM8_sprout'
    targets = [product / name for name in OUTPUTS]
    # Validate the entire deletion set before removing anything. Do not follow
    # symlinks in out/, product/, obj/ or the allowlisted targets themselves.
    for target in targets:
        for path in (target, *target.parents):
            if path == top:
                break
            if path.is_symlink():
                raise ValueError(f'Refusing symlink in build output path: {path}')
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        print(f'Clean kernel/package output: {target.relative_to(top)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    try:
        clean(args.top)
    except (OSError, ValueError) as error:
        parser.exit(1, f'ERROR: {error}\n')
