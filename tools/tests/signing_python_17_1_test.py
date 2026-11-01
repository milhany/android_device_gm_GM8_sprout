#!/usr/bin/env python3
"""Interpreter selection and private child-tool aliases (host fixture)."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile

script = Path(__file__).resolve().parents[1] / 'release-17.1.py'
spec = importlib.util.spec_from_file_location('gm8qpython', script)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

with tempfile.TemporaryDirectory(prefix='gm8-q-python-test-') as temporary:
    root = Path(temporary)
    top = root / 'android'
    top.mkdir()
    bad = root / 'incomplete-python2'
    bad.write_text('#!/bin/sh\necho "ImportError: No module named zlib" >&2\nexit 1\n')
    bad.chmod(0o755)
    full = root / 'complete-python2'
    # The real Python 2 import probe runs on the owner's build server.
    # This stub proves selection, environment isolation and alias dispatch.
    full.write_text('''#!/bin/sh
test -z "${PYTHONHOME+x}" || exit 71
test -z "${PYTHONPATH+x}" || exit 72
case "$2" in
  *"import sys,zlib,gzip,bz2,ssl,hashlib,zipfile,ctypes"*) exit 0 ;;
  *) echo complete-python-selected ;;
esac
''')
    full.chmod(0o755)
    release.signing_python_candidates = lambda top: [root / 'missing', bad, full]
    saved = dict(os.environ)
    try:
        os.environ['PYTHONHOME'] = '/incompatible-old-home'
        os.environ['PYTHONPATH'] = '/incompatible-old-modules'
        assert release.signing_python(top) == full
        host = top / 'out/host/linux-x86'
        (host / 'bin').mkdir(parents=True)
        for name in ('avbtool', 'apksigner'):
            (host / 'bin' / name).touch()
        sources = top / 'build/make/tools/releasetools'
        sources.mkdir(parents=True)
        for name in ('sign_target_files_apks', 'ota_from_target_files'):
            (sources / (name + '.py')).touch()
        alias = root / 'private-python-bin'
        alias.mkdir()
        assert release.host_tools(top, alias) == host
        for name in ('python', 'python2'):
            assert (alias / name).resolve() == full
            output = subprocess.check_output([name, '-c', 'print("alias")'], text=True)
            assert output.strip() == 'complete-python-selected'
        assert release.releasetool(host, 'sign_target_files_apks') == [
            full, sources / 'sign_target_files_apks.py']
        release.signing_python_candidates = lambda top: [bad]
        try:
            release.signing_python(top)
        except ValueError as error:
            assert 'zlib' in str(error) and 'libpython2.7-stdlib' in str(error)
        else:
            raise AssertionError('Incomplete signing Python must be rejected')
    finally:
        os.environ.clear()
        os.environ.update(saved)

print('PASS: reject incomplete Python, select full interpreter, isolate PYTHONHOME/PYTHONPATH '
      'and route Q child tools through private aliases')
