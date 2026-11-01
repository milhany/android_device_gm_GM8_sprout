#!/usr/bin/env python3
"""Wrapper integration: real shell/filesystem, Android build/signing as fixtures."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

source = Path(__file__).resolve().parents[1] / 'build-release-17.1.sh'
with tempfile.TemporaryDirectory(prefix='gm8-q-wrapper-') as temporary:
    root = Path(temporary)
    top = root / 'lineage-17.1'
    tools = top / 'device/gm/GM8_sprout/tools'
    tools.mkdir(parents=True)
    shutil.copyfile(source, tools / source.name)
    version = top / 'build/core/version_defaults.mk'
    version.parent.mkdir(parents=True)
    version.write_text('PLATFORM_SDK_VERSION := 29\n')
    shim = root / 'bin'
    shim.mkdir()
    (shim / 'repo').write_text('#!/bin/sh\nexit 0\n')
    (shim / 'repo').chmod(0o755)
    # Dispatch the test's Python regardless of the machine's default interpreter.
    (shim / 'python3').symlink_to(sys.executable)
    build = tools / 'build-17.1.sh'
    build.write_text('''#!/bin/bash
set -e
test "$1" = target-files
echo built >> fixture-builds
mkdir -p out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates
printf fixture > out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates/lineage_GM8_sprout-target_files-eng.builder.zip
''')
    (tools / 'release-17.1.py').write_text('''import os,sys
from pathlib import Path
args=sys.argv
output=Path(args[args.index('--output-dir')+1])
if args[1]=='prepare':
    assert args[args.index('--install-mode')+1]=='clean'
    (output/'prepared').touch()
else:
    assert (output/'prepared').exists()
    if os.getenv('GM8_FIXTURE_FAIL'):
        sys.exit(3)
    (output/'gm8-17.1-userdebug-release.zip').write_bytes(b'fixture-verified-zip')
    (output/'gm8-17.1-userdebug-release-boot.img').write_bytes(b'fixture-verified-boot')
''')
    keys = root / 'gm8-signing/keys'
    keys.mkdir(parents=True)
    for role in ('releasekey', 'platform', 'shared', 'media', 'networkstack'):
        for suffix in ('pk8', 'x509.pem'):
            (keys / f'{role}.{suffix}').write_text('fixture')
    release = root / 'gm8-17.1-release'
    previous = root / 'previous'
    previous.mkdir()
    release.mkdir()
    latest = release / 'latest'
    latest.symlink_to(previous)
    env = dict(os.environ, PATH=str(shim) + os.pathsep + os.environ['PATH'])
    env.pop('OUT_DIR', None)
    env.pop('OUT_DIR_COMMON_BASE', None)

    def run(**extra):
        return subprocess.run(['bash', str(tools / source.name)], cwd=top,
                              env=dict(env, **extra), capture_output=True, text=True)

    # Wrong branch and missing original key both fail before building.
    version.write_text('PLATFORM_SDK_VERSION := 32\n')
    assert run().returncode != 0 and not (top / 'fixture-builds').exists()
    version.write_text('PLATFORM_SDK_VERSION := 29\n')
    original = keys / 'releasekey.pk8'
    original.rename(keys / 'saved.pk8')
    assert run().returncode != 0 and not (top / 'fixture-builds').exists()
    (keys / 'saved.pk8').rename(original)
    before = {p.name: p.read_bytes() for p in keys.iterdir()}
    failed = run(GM8_FIXTURE_FAIL='1')
    assert failed.returncode != 0 and latest.resolve() == previous
    assert 'release incomplete' in failed.stdout
    succeeded = run()
    assert succeeded.returncode == 0, succeeded.stdout + succeeded.stderr
    assert latest.resolve() != previous
    assert (latest / 'SHA256SUMS').is_file()
    assert 'SIGNED ZIP:' in succeeded.stdout
    assert before == {p.name: p.read_bytes() for p in keys.iterdir()}
    current = latest.resolve()
    with (release / '.build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert run().returncode != 0 and latest.resolve() == current

print('PASS: Q wrapper rejects wrong SDK/missing original keys, preserves latest '
      'on signing failure, publishes successful output/checksums and blocks concurrent builds')
