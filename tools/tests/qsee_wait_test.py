#!/usr/bin/env python3
"""Run actual QSEE C functions with host lock/wait/TZ shims, not phone firmware."""
import argparse
from pathlib import Path
import subprocess
import tempfile


NAMES = [
    '__qseecom_abort_legacy_listener',
    'qseecom_unregister_listener',
    '__qseecom_listener_has_sent_rsp',
    '__qseecom_reentrancy_listener_has_sent_rsp',
    '__qseecom_clean_listener_sglistinfo',
    '__qseecom_process_incomplete_cmd',
    'qseecom_release',
]


def function(source, name):
    import re
    pattern = r'^static (?:int|void) ' + re.escape(name) + r'\('
    match = re.search(pattern, source, re.M)
    if match is None:
        raise ValueError('Function not found: ' + name)
    # These selected functions have an unindented closing brace only at the end.
    end = source.index('\n}', match.start()) + 2
    return source[match.start():end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    source = args.source.read_text()
    names = NAMES[1:] if args.baseline else NAMES
    actual = '\n\n'.join(function(source, name) for name in names)
    with tempfile.TemporaryDirectory(prefix='gm8-qsee-test-') as tmp:
        tmp = Path(tmp)
        (tmp / 'actual.c').write_text(actual + '\n')
        binary = tmp / 'qsee-test'
        cmd = ['cc', '-std=gnu89', '-Wall', '-Wextra', '-Werror',
               '-Wno-unused-parameter', '-Wno-unused-function', '-pthread',
               '-g', '-O1', '-I', str(tmp)]
        if args.sanitize:
            cmd += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie']
        if args.baseline:
            cmd += ['-DBASELINE=1']
        cmd += [str(Path(__file__).with_name('qsee_host.c')), '-o', str(binary)]
        subprocess.run(cmd, check=True)
        subprocess.run([str(binary)], check=True, timeout=30)


if __name__ == '__main__':
    main()
