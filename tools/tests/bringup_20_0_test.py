#!/usr/bin/env python3
"""Exercise real SDK33 audit and bootstrap validation with local fixtures."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gm8_audit20', ROOT / 'tools/preflight-20.0.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.STDOUT)


with tempfile.TemporaryDirectory(prefix='gm8-audit20-') as tmp:
    top = Path(tmp)
    inputs = [
        'build/core/version_defaults.mk', 'build/envsetup.sh',
        'vendor/lineage/config/common_full_phone.mk', 'device/qcom/sepolicy-legacy-um/SEPolicy.mk',
        'hardware/qcom-caf/bootctrl/Android.bp', 'hardware/qcom-caf/msm8996/audio/Android.mk',
        'tools/extract-utils/extract_utils.sh', 'vendor/gapps/arm64/arm64-vendor.mk',
        'device/gm/GM8_sprout/lineage_GM8_sprout.mk', 'vendor/gm/GM8_sprout/GM8_sprout-vendor.mk',
        'kernel/gm/msm8937/Makefile', 'packages/modules/Connectivity/netd/BpfHandler.cpp',
        'packages/modules/Connectivity/service/native/TrafficController.cpp',
        'frameworks/opt/telephony/src/java/com/android/internal/telephony/RadioConfig.java',
        'frameworks/opt/telephony/src/java/com/android/internal/telephony/data/PhoneSwitcher.java',
        'system/core/libprocessgroup/processgroup.cpp', 'system/netd/fixture.txt',
    ]
    for name in inputs:
        p = top / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('fixture\n')
    version = top / 'build/core/version_defaults.mk'
    version.write_text('PLATFORM_SDK_VERSION := 33\n')
    for n in (28, 29, 30, 31): (top / f'prebuilts/vndk/v{n}').mkdir(parents=True)
    webview = top / 'external/chromium-webview/prebuilt/arm64/webview.apk'
    webview.parent.mkdir(parents=True)
    with zipfile.ZipFile(webview, 'w') as z: z.writestr('AndroidManifest.xml', 'fixture')
    repo_paths = ['device/gm/GM8_sprout', 'vendor/gm/GM8_sprout', 'kernel/gm/msm8937',
                  'vendor/gapps', 'packages/modules/Connectivity', 'frameworks/opt/telephony',
                  'system/core', 'system/netd']
    for name in repo_paths:
        p = top / name
        git(p, 'init', '-q'); git(p, 'config', 'user.name', 'GM8 test')
        git(p, 'config', 'user.email', 'test@example.invalid')
        git(p, 'add', '.'); git(p, 'commit', '-qm', 'fixture')
    probe = top / 'frameworks/opt/telephony/probe.txt'
    probe.write_text('before\n')
    patch = top / 'device/gm/GM8_sprout/patches/frameworks_opt_telephony/probe.patch'
    patch.parent.mkdir(parents=True)
    patch.write_text('--- a/probe.txt\n+++ b/probe.txt\n@@ -1 +1 @@\n-before\n+after\n')
    r = module.audit(top)
    assert r['source_inputs_complete'] and r['runtime_blockers']
    assert not r['ready_for_boot_image'] and not r['ready_for_ota']
    assert r['sdk32_patch_context_checks'][0]['context_applies']
    assert not r['sdk32_patch_context_checks'][0]['sdk33_reviewed']
    assert probe.read_text() == 'before\n'
    print('PASS: complete inventory retains runtime blockers and never applies an applicable patch')
    version.write_text('PLATFORM_SDK_VERSION := 32\n')
    assert not module.audit(top)['source_inputs_complete']
    version.write_text('PLATFORM_SDK_VERSION := 33\n')
    good = webview.read_bytes()
    webview.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:fixture\n')
    assert any('LFS pointer' in e for e in module.audit(top)['errors'])
    webview.write_bytes(good)
    required = top / 'packages/modules/Connectivity/netd/BpfHandler.cpp'
    required.unlink()
    assert any('BpfHandler' in e for e in module.audit(top)['errors'])
    print('PASS: wrong SDK, unresolved LFS pointer and incomplete Connectivity source are rejected')

bootstrap = (ROOT / 'tools/bootstrap-20.0.sh').read_text()
validation = bootstrap.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
for name in ('fresh', 'interrupted-init', 'unknown-metadata', 'wrong-sdk',
             'old-manifest', 'nonempty', 'bad-remote', 'low-space'):
    with tempfile.TemporaryDirectory(prefix='gm8-bootstrap20-') as tmp:
        parent = Path(tmp); target = parent / 'lineage-20.0'
        manifest = parent / 'local.xml'
        source = (ROOT / 'docs/local_manifest.xml').read_text()
        if name == 'bad-remote': source = source.replace('https://github.com/', 'http://example.invalid/')
        manifest.write_text(source)
        if name in ('wrong-sdk', 'old-manifest'):
            p = target / '.repo/manifests/default.xml'; p.parent.mkdir(parents=True)
            p.write_text('<manifest><default revision="' + ('lineage-19.1' if name == 'old-manifest' else 'lineage-20.0') + '" /></manifest>')
            if name == 'wrong-sdk':
                p = target / 'build/core/version_defaults.mk'; p.parent.mkdir(parents=True)
                p.write_text('PLATFORM_SDK_VERSION := 32\n')
        if name == 'nonempty':
            target.mkdir(); (target / 'keep.txt').write_text('private work\n')
        if name in ('interrupted-init', 'unknown-metadata'):
            p = target / '.repo/repo/keep.txt'; p.parent.mkdir(parents=True)
            p.write_text('existing repo launcher\n')
            if name == 'unknown-metadata':
                (target / '.repo/unknown-project').mkdir()
        before = {str(p.relative_to(parent)): p.read_bytes() for p in parent.rglob('*') if p.is_file()}
        free = (20 if name == 'low-space' else 1000) * 1024**3
        with mock.patch.object(sys, 'argv', ['bootstrap', str(target), str(manifest)]), \
             mock.patch('shutil.disk_usage', return_value=SimpleNamespace(free=free)), \
             mock.patch.dict('os.environ', {'GM8_MIN_FREE_GIB': '400'}), \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                exec(compile(validation, 'actual-bootstrap-validation', 'exec'), {})
                success = True
            except SystemExit:
                success = False
        assert success == (name in ('fresh', 'interrupted-init')), name
        after = {str(p.relative_to(parent)): p.read_bytes() for p in parent.rglob('*') if p.is_file()}
        assert before == after
        print('PASS:', name, '— actual bootstrap validator preserves existing files')

# Run the actual repo-init capability choice and LFS project command. No
# Android sync/server is involved; the LFS payload is transferred between
# local fixture repositories, including a detached checkout and remote
# whose name is not origin.
init_choice = bootstrap.split('repo_init_args=', 1)[1].split('\nmkdir -p .repo/local_manifests', 1)[0]
init_choice = 'repo_init_args=' + init_choice
lfs_command = bootstrap.split("repo forall -e -c '\n", 1)[1].split("\n    '\n", 1)[0]
with tempfile.TemporaryDirectory(prefix='gm8-repo-lfs20-') as tmp:
    fixture = Path(tmp)
    bin_dir = fixture / 'bin'; bin_dir.mkdir()
    calls = fixture / 'repo-calls.jsonl'
    repo_stub = bin_dir / 'repo'
    repo_stub.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if args == ['init', '-h']:
    print('Usage: repo init' + (' --git-lfs' if os.environ['GM8_TEST_NATIVE_LFS'] == '1' else ''))
else:
    with Path(os.environ['GM8_TEST_REPO_CALLS']).open('a') as f:
        f.write(json.dumps(args) + '\\n')
''')
    repo_stub.chmod(0o755)
    env = {**os.environ, 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
           'GM8_TEST_REPO_CALLS': str(calls), 'GIT_CONFIG_GLOBAL': os.devnull,
           'GIT_CONFIG_NOSYSTEM': '1'}
    for native in ('0', '1'):
        calls.unlink(missing_ok=True)
        choice = subprocess.run(['bash', '-euc', init_choice + '\n' +
                                 'test "$repo_native_lfs" = "$GM8_TEST_EXPECTED"'],
                                env={**env, 'GM8_TEST_NATIVE_LFS': native,
                                     'GM8_TEST_EXPECTED': 'true' if native == '1' else 'false'},
                                text=True, capture_output=True)
        assert choice.returncode == 0, choice.stdout + choice.stderr
        call = json.loads(calls.read_text().strip())
        assert ('--git-lfs' in call) == (native == '1'), call
        assert call[:2] == ['init', '-u'], call
    print('PASS: old repo init omits unsupported option; native repo keeps Git LFS enabled')

    def run(*args, cwd=None, checked=True, extra_env=None):
        result = subprocess.run(args, cwd=cwd, env={**env, **(extra_env or {})},
                                text=True, capture_output=True)
        if checked:
            assert result.returncode == 0, result.stdout + result.stderr
        return result

    remote = fixture / 'remote.git'; seed = fixture / 'seed'; client = fixture / 'client'
    run('git', 'init', '--bare', str(remote))
    run('git', 'init', str(seed))
    run('git', 'config', 'user.name', 'GM8 test', cwd=seed)
    run('git', 'config', 'user.email', 'test@example.invalid', cwd=seed)
    run('git', 'lfs', 'install', '--local', cwd=seed)
    run('git', 'lfs', 'track', '*.apk', cwd=seed)
    payload = b'GM8 fixture APK payload\n' * 100
    (seed / 'webview.apk').write_bytes(payload)
    run('git', 'add', '.', cwd=seed)
    run('git', 'commit', '-m', 'fixture LFS payload', cwd=seed)
    run('git', 'remote', 'add', 'fixture-lfs', str(remote), cwd=seed)
    run('git', 'push', 'fixture-lfs', 'HEAD', cwd=seed)
    run('git', 'clone', '--origin', 'fixture-lfs', str(remote), str(client),
        extra_env={'GIT_LFS_SKIP_SMUDGE': '1'})
    run('git', 'checkout', '--detach', cwd=client)
    pointer = (client / 'webview.apk').read_bytes()
    assert pointer.startswith(b'version https://git-lfs.github.com/spec/v1\n')
    project_env = {'REPO_PATH': 'external/chromium-webview', 'REPO_REMOTE': 'fixture-lfs'}
    run('sh', '-c', lfs_command, cwd=client, extra_env=project_env)
    assert (client / 'webview.apk').read_bytes() == payload
    print('PASS: legacy path downloads and verifies real LFS bytes using the manifest remote')

    plain = fixture / 'plain'; run('git', 'init', str(plain))
    run('git', 'config', 'user.name', 'GM8 test', cwd=plain)
    run('git', 'config', 'user.email', 'test@example.invalid', cwd=plain)
    (plain / 'keep.txt').write_text('plain repository\n')
    run('git', 'add', '.', cwd=plain); run('git', 'commit', '-m', 'plain', cwd=plain)
    run('git', 'config', 'gm8.keep', 'preserved', cwd=plain)
    run('sh', '-c', lfs_command, cwd=plain, extra_env=project_env)
    assert run('git', 'config', '--local', 'gm8.keep', cwd=plain).stdout.strip() == 'preserved'
    assert run('git', 'config', '--local', '--get', 'filter.lfs.clean', cwd=plain,
               checked=False).returncode == 1
    assert not (plain / '.git/hooks/pre-push').exists()
    print('PASS: non-LFS projects preserve existing settings and gain no LFS filter or hook')

    broken = fixture / 'broken'
    run('git', 'clone', '--origin', 'fixture-lfs', str(remote), str(broken),
        extra_env={'GIT_LFS_SKIP_SMUDGE': '1'})
    run('git', 'config', 'lfs.url', (fixture / 'missing-lfs-server').as_uri(), cwd=broken)
    failed = run('sh', '-c', lfs_command, cwd=broken, checked=False, extra_env=project_env)
    assert failed.returncode != 0
    assert (broken / 'webview.apk').read_bytes() == pointer
    print('PASS: missing LFS payload propagates failure instead of accepting a pointer')
