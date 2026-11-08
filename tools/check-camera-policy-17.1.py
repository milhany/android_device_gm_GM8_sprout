#!/usr/bin/env python3
"""Verify the exact AE property label and its existing Q userdebug permission."""
import argparse
from pathlib import Path
import subprocess


def check_contexts(text):
    rows = [line.split('#', 1)[0].split() for line in text.splitlines()]
    rows = [row for row in rows if row and row[0] == 'persist.vendor.camera.aeinfo']
    expected = ['persist.vendor.camera.aeinfo', 'u:object_r:camera_prop:s0', 'exact', 'string']
    if rows != [expected]:
        raise ValueError('AE telemetry must have one exact string camera_prop label')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    top = args.top.resolve()
    product = top / 'out/target/product/GM8_sprout'
    host = top / 'out/host/linux-x86'
    try:
        check_contexts((product / 'vendor/etc/selinux/vendor_property_contexts').read_text())
        policy = product / 'obj/ETC/sepolicy_intermediates/sepolicy'
        result = subprocess.run([
            str(host / 'bin/searchpolicy'), str(policy), '--libpath',
            str(host / 'lib64/libsepolwrap.so'), '--allow', '-s', 'mm-qcamerad',
            '-t', 'camera_prop', '-c', 'property_service', '-p', 'set'],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if not any(line.startswith('allow ') for line in result.stdout.splitlines()):
            raise ValueError('Compiled policy lacks the existing Q camera_prop setter; '
                             'this candidate targets userdebug, not user')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Camera policy check failed: {error}\n{getattr(error, "stderr", "") or ""}')
    print('PASS: compiled exact AE telemetry label and camera_prop set permission')
    print('This check does not establish camera image quality or sensor operation.')


if __name__ == '__main__':
    main()
