#!/usr/bin/env python3
"""Execute the real wrapper with fixture build/sign commands, never an Android build."""
import importlib.util
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

tools = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('clean_kernel', tools / 'clean-kernel-19.1.py')
cleaner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleaner)


def executable(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    path.chmod(0o755)


with tempfile.TemporaryDirectory(prefix='gm8-workflow-test-') as td:
    root = Path(td)
    top = root / 'android/lineage-19.1'
    device = top / 'device/gm/GM8_sprout/tools'
    device.mkdir(parents=True)
    (top / 'kernel/gm/msm8937').mkdir(parents=True)
    (top / 'build/core').mkdir(parents=True)
    (top / 'build/envsetup.sh').touch()
    (top / 'build/core/version_defaults.mk').write_text('PLATFORM_SDK_VERSION := 32\n')
    for name in ('build-release-19.1.sh', 'clean-kernel-19.1.py'):
        shutil.copyfile(tools / name, device / name)
    keys = root / 'android/gm8-signing/keys'
    keys.mkdir(parents=True)
    (keys / 'releasekey.pk8').write_bytes(b'key fixture')
    (keys / 'releasekey.x509.pem').write_bytes(b'public fixture')
    executable(device / 'build-19.1.sh', '''#!/bin/bash
set -e
test "$1 $2" = 'target-files user'
test ! -e out/target/product/GM8_sprout/obj/KERNEL_OBJ/old
if [[ ${GM8_FIXTURE_FAIL:-0} == 1 ]]; then exit 42; fi
mkdir -p out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates
echo fresh > out/target/product/GM8_sprout/obj/PACKAGING/target_files_intermediates/gm8-target_files-user.zip
''')
    executable(device / 'release-19.1.py', '''import json, pathlib, sys
args = sys.argv[1:]
out = pathlib.Path(args[args.index('--output-dir') + 1])
if args[0] == 'prepare':
    assert args[args.index('--install-mode') + 1] == 'update'
    target = pathlib.Path(args[args.index('--target-files') + 1])
    assert target.read_text() == 'fresh\\n'
    (out / 'release-plan.json').write_text('{}')
else:
    assert (out / 'release-plan.json').exists()
    import os
    if os.environ.get('GM8_FIXTURE_SIGN_FAIL') == '1':
        sys.exit(43)
    (out / 'gm8-19.1-user-release.zip').write_bytes(b'verified fixture')
    (out / 'gm8-19.1-user-release-boot.img').write_bytes(b'boot fixture')
''')
    bin_dir = root / 'bin'
    executable(bin_dir / 'repo', '#!/bin/sh\nexit 0\n')
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])
    env.pop('OUT_DIR', None)
    env.pop('OUT_DIR_COMMON_BASE', None)
    product = top / 'out/target/product/GM8_sprout'
    kernel = product / 'obj/KERNEL_OBJ'
    kernel.mkdir(parents=True)
    (kernel / 'old').touch()
    keep = product / 'system/app/keep.apk'
    keep.parent.mkdir(parents=True)
    keep.write_bytes(b'preserved')
    source = top / 'kernel/gm/msm8937/Makefile'
    source.write_text('source preserved')

    def invoke(extra=None):
        return subprocess.run(['bash', str(device / 'build-release-19.1.sh'), '--inside'],
                              env=dict(env, **(extra or {})), capture_output=True, text=True)

    result = invoke()
    assert result.returncode == 0, result.stdout + result.stderr
    latest = root / 'android/gm8-release/latest'
    first = latest.resolve()
    assert (first / 'gm8-19.1-user-release.zip').is_file()
    assert (first / 'SHA256SUMS').is_file() and (first / 'build.log').is_file()
    assert keep.read_bytes() == b'preserved'
    assert source.read_text() == 'source preserved'
    assert (keys / 'releasekey.pk8').read_bytes() == b'key fixture'
    kernel.mkdir()
    (kernel / 'old').touch()
    result = invoke()
    assert result.returncode == 0, result.stdout + result.stderr
    second = latest.resolve()
    assert second != first and first.is_dir()
    result = invoke({'GM8_FIXTURE_FAIL': '1'})
    assert result.returncode != 0, result.stdout + result.stderr
    assert latest.resolve() == second
    for failed in latest.parent.iterdir():
        if failed.is_dir() and not failed.is_symlink() and failed not in (first, second):
            assert not (failed / 'release-plan.json').exists(), 'Signed after a failed build'
    result = invoke({'GM8_FIXTURE_SIGN_FAIL': '1'})
    assert result.returncode != 0 and latest.resolve() == second
    with (latest.parent / '.build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = invoke()
        assert result.returncode != 0 and 'already running' in result.stderr

    # Reject a path escape before any removal, even if it points inside out/.
    outside = root / 'outside'
    outside.mkdir()
    sentinel = outside / 'sentinel'
    sentinel.touch()
    kernel.symlink_to(outside, target_is_directory=True)
    try:
        cleaner.clean(top)
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted symlinked kernel output')
    assert sentinel.exists() and keep.exists()
    kernel.unlink()
    result = invoke({'OUT_DIR': '/tmp/not-gm8'})
    assert result.returncode != 0 and latest.resolve() == second
    (keys / 'releasekey.pk8').unlink()
    kernel.mkdir()
    (kernel / 'old').touch()
    (bin_dir / 'repo').unlink()
    result = invoke()
    assert result.returncode != 0 and (kernel / 'old').exists()
    executable(bin_dir / 'repo', '#!/bin/sh\nexit 0\n')
    result = invoke()
    assert result.returncode != 0 and (kernel / 'old').exists()

    # Host dispatch enters the existing container with builder and a TTY.
    executable(bin_dir / 'id', '#!/bin/sh\necho ilhan\n')
    executable(bin_dir / 'sudo', '#!/bin/sh\nexec "$@"\n')
    docker_record = root / 'docker.jsonl'
    executable(bin_dir / 'docker', '''#!/usr/bin/env python3
import json, os, pathlib, sys
with pathlib.Path(os.environ['GM8_DOCKER_RECORD']).open('a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
''')
    result = subprocess.run(['bash', str(device / 'build-release-19.1.sh')],
                            env=dict(env, GM8_DOCKER_RECORD=str(docker_record)),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    start, enter = [json.loads(line) for line in docker_record.read_text().splitlines()]
    assert start == ['start', 'gm8-build']
    assert enter[:5] == ['exec', '-it', '--user', 'builder', '--workdir']
    assert enter[-1] == '--inside'

print('PASS: host/container dispatch, kernel-only cleanup boundaries, repeated releases, '
      'failed-build signing gate, latest preservation, existing-key and path-escape guards')
