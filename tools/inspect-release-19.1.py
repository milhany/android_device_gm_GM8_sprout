#!/usr/bin/env python3
"""Read signing metadata from a GM8 SDK 32 target-files archive; never sign or flash."""
import argparse
from pathlib import Path
import zipfile


def properties(text):
    result = {}
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def metadata(archive, name, required=True):
    try:
        entry = archive.getinfo(name)
    except KeyError:
        if required:
            raise ValueError(f'Missing required target-files metadata: {name}')
        return '(not present)\n'
    if entry.file_size > 2 * 1024 * 1024:
        raise ValueError(f'Unexpectedly large metadata entry: {name}')
    return archive.read(entry).decode('utf-8')


def inspect(target, variant):
    with zipfile.ZipFile(target) as archive:
        build = metadata(archive, 'SYSTEM/build.prop')
        props = properties(build)
        if props.get('ro.build.version.sdk') != '32':
            raise ValueError('Expected Android 12.1 / SDK 32 target-files')
        if props.get('ro.build.type') != variant:
            raise ValueError(f'Expected {variant}; archive reports {props.get("ro.build.type")}')
        selected = '\n'.join(f'{key}={props[key]}' for key in sorted(props)
                             if key.startswith(('ro.build.', 'ro.product.')))
        sections = [('SYSTEM/build.prop (build/product properties)', selected)]
        for name in ('META/misc_info.txt', 'META/apkcerts.txt', 'META/apexkeys.txt'):
            sections.append((name, metadata(archive, name)))
        sections.append(('META/otakeys.txt', metadata(archive, 'META/otakeys.txt', required=False)))
    return ('GM8 Android 12.1 signing inputs (read-only inventory)\n'
            f'Target files: {target.resolve()}\nExpected variant: {variant}\n'
            'This report contains metadata/key paths, not private key contents.\n'
            'This archive is not declared release-signed or safe to dirty-flash.\n\n'
            + '\n\n'.join(f'===== {name} =====\n{text.rstrip()}' for name, text in sections) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--target-files', type=Path)
    source.add_argument('--product-out', type=Path)
    parser.add_argument('--variant', choices=('user', 'userdebug'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        target = args.target_files
        if target is None:
            candidates = sorted((args.product_out / 'obj/PACKAGING/target_files_intermediates')
                                .glob('*target_files*.zip'))
            if len(candidates) != 1:
                raise ValueError('Expected exactly one target-files archive; use --target-files '
                                 f'to select explicitly. Candidates: {[str(p) for p in candidates]}')
            target = candidates[0]
        if args.output.resolve() == target.resolve():
            raise ValueError('Report must not overwrite the target-files archive')
        report = inspect(target, args.variant)
        args.output.write_text(report)
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile) as error:
        parser.exit(1, f'ERROR: {error}\n')
    print(f'Signing metadata: {args.output.resolve()}')
    print(f'Target files: {target.resolve()}')
    print('No keys generated, no signing performed, no device data modified.')


if __name__ == '__main__':
    main()
