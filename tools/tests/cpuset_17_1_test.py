#!/usr/bin/env python3
"""Reject reversed/all-core background placement in source and target-files."""
import importlib.util
import io
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('runtime', ROOT / 'tools/check-runtime-17.1.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
source = (ROOT / 'rootdir/etc/init.gm.rc').read_text()


def packaged(text):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('VENDOR/etc/init/init.gm.rc', text)
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as archive:
        runtime.check_packaged_cpusets(archive)


runtime.check_cpuset_text(source)
packaged(source)
for bad in (
        source.replace('/background/cpus 4-7', '/background/cpus 0-7'),
        source.replace('/system-background/cpus 4-7', '/system-background/cpus 0-3'),
        source.replace('/top-app/cpus 0-7', '/top-app/cpus 4-7'),
        source.replace('on boot', 'on post-fs-data'),
        source + '\non boot\n    write /dev/cpuset/background/cpus 0-7\n'):
    for check in (runtime.check_cpuset_text, packaged):
        try:
            check(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Unsafe or ineffective CPU placement accepted')
print('PASS: source and packaged cpusets reject reversed clusters, restricted top app and overrides')
