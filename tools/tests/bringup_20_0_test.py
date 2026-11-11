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
        'device/gm/GM8_sprout/rootdir/etc/fstab.qcom',
        'kernel/gm/msm8937/Makefile', 'packages/modules/Connectivity/netd/BpfHandler.cpp',
        'packages/modules/Connectivity/service/native/TrafficController.cpp',
        'frameworks/opt/telephony/src/java/com/android/internal/telephony/RadioConfig.java',
        'frameworks/opt/telephony/src/java/com/android/internal/telephony/data/PhoneSwitcher.java',
        'system/core/libprocessgroup/processgroup.cpp', 'system/netd/fixture.txt',
        'system/netd/server/FirewallController.cpp', 'system/netd/server/FirewallController.h',
        'system/netd/server/NetdNativeService.cpp',
        'packages/modules/Connectivity/service-t/jni/com_android_server_net_NetworkStatsService.cpp',
        'packages/modules/Connectivity/service/Android.bp',
    ]
    for name in inputs:
        p = top / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('fixture\n')
    version = top / 'build/core/version_defaults.mk'
    version.write_text('PLATFORM_SDK_VERSION := 33\n')
    fstab = top / 'device/gm/GM8_sprout/rootdir/etc/fstab.qcom'
    good_fstab = (ROOT / 'rootdir/etc/fstab.qcom').read_text()
    fstab.write_text(good_fstab)
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
    sdk33_patch = top / 'device/gm/GM8_sprout/patches/sdk33/system_core/probe.patch'
    sdk33_patch.parent.mkdir(parents=True)
    sdk33_patch.write_text('--- a/libprocessgroup/processgroup.cpp\n+++ b/libprocessgroup/processgroup.cpp\n@@ -1 +1 @@\n-fixture\n+sdk33-fixture\n')
    stats_patch = top / 'device/gm/GM8_sprout/patches/sdk33/Connectivity/probe.patch'
    stats_patch.parent.mkdir(parents=True)
    stats_patch.write_text('--- a/service-t/jni/com_android_server_net_NetworkStatsService.cpp\n+++ b/service-t/jni/com_android_server_net_NetworkStatsService.cpp\n@@ -1 +1 @@\n-fixture\n+stats-fixture\n')
    firewall_patch = top / 'device/gm/GM8_sprout/patches/sdk33/system_netd/probe.patch'
    firewall_patch.parent.mkdir(parents=True)
    firewall_patch.write_text('--- a/server/FirewallController.cpp\n+++ b/server/FirewallController.cpp\n@@ -1 +1 @@\n-fixture\n+firewall-fixture\n')
    r = module.audit(top)
    assert len(r['sdk33_source_ports']) == 3
    assert r['sdk33_source_ports'][2]['project'] == 'system/netd'
    assert r['sdk33_source_ports'][2]['context_applies'] and not r['sdk33_source_ports'][2]['applied']
    assert r['sdk33_source_ports'][1]['project'] == 'packages/modules/Connectivity'
    assert r['sdk33_source_ports'][1]['context_applies'] and not r['sdk33_source_ports'][1]['applied']
    assert r['sdk33_source_ports'][0]['context_applies']
    assert not r['sdk33_source_ports'][0]['applied']
    assert not r['sdk33_source_ports'][0]['hardware_accepted']
    assert r['userdata_policy']['mode'] == 'unencrypted_f2fs_bringup'
    assert r['source_inputs_complete'] and r['runtime_blockers']
    assert not r['ready_for_boot_image'] and not r['ready_for_ota']
    assert r['sdk32_patch_context_checks'][0]['context_applies']
    assert not r['sdk32_patch_context_checks'][0]['sdk33_reviewed']
    assert probe.read_text() == 'before\n'
    print('PASS: complete inventory retains runtime blockers and never applies an applicable patch')
    core = top / 'system/core'
    assert (core / 'libprocessgroup/processgroup.cpp').read_text() == 'fixture\n'
    git(core, 'apply', str(sdk33_patch))
    applied_audit = module.audit(top)
    assert applied_audit['sdk33_source_ports'][0]['applied']
    assert not applied_audit['ready_for_boot_image']
    git(core, 'apply', '--reverse', str(sdk33_patch))
    for flags in ('wait,encryptable=footer', 'wait,fileencryption=aes-256-xts', 'wait,metadata_encryption=aes-256-xts'):
        fstab.write_text('/dev/block/by-name/userdata /data f2fs rw ' + flags + '\n')
        rejected = module.audit(top)
        assert any('unsupported FDE/FBE' in e for e in rejected['errors'])
    fstab.write_text('/dev/block/by-name/userdata /data ext4 rw wait\n')
    assert any('one explicit F2FS' in e for e in module.audit(top)['errors'])
    fstab.write_text(good_fstab)
    assert module.audit(top)['source_inputs_complete']
    print('PASS: SDK33 staged/applied source state is read-only; unsupported userdata policy is rejected')
    version.write_text('PLATFORM_SDK_VERSION := 32\n')
    assert not module.audit(top)['source_inputs_complete']
    version.write_text('PLATFORM_SDK_VERSION := 33\n')
    good = webview.read_bytes()
    webview.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:fixture\n')
    assert any('LFS pointer' in e for e in module.audit(top)['errors'])
    webview.write_bytes(b'not an APK archive\n')
    bad_zip_errors = module.audit(top)['errors']
    assert any('not a ZIP archive' in e for e in bad_zip_errors)
    assert not any('LFS pointer' in e for e in bad_zip_errors)
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
lfs_command = bootstrap.split("repo forall -e -c '\n", 1)[1].split("\n'\n", 1)[0]
with tempfile.TemporaryDirectory(prefix='gm8-repo-lfs20-') as tmp:
    fixture = Path(tmp)
    bin_dir = fixture / 'bin'; bin_dir.mkdir()
    calls = fixture / 'repo-calls.jsonl'
    repo_stub = bin_dir / 'repo'
    repo_stub.write_text('''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
if args == ['init', '-h']:
    print('Usage: repo init' + (' --git-lfs' if os.environ['GM8_TEST_NATIVE_LFS'] == '1' else ''))
else:
    with Path(os.environ['GM8_TEST_REPO_CALLS']).open('a') as f:
        f.write(json.dumps(args) + '\\n')
    if args[:3] == ['forall', '-e', '-c']:
        project_env = dict(os.environ, REPO_PATH='external/chromium-webview/prebuilt/arm64',
                           REPO_REMOTE='fixture-lfs')
        sys.exit(subprocess.run(['sh', '-c', args[3]],
                               cwd=os.environ['GM8_TEST_LFS_PROJECT'], env=project_env).returncode)
''')
    repo_stub.chmod(0o755)
    env = {**os.environ, 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
           'GM8_TEST_REPO_CALLS': str(calls), 'GIT_CONFIG_GLOBAL': os.devnull,
           'GIT_CONFIG_NOSYSTEM': '1'}
    for native in ('0', '1'):
        calls.unlink(missing_ok=True)
        choice = subprocess.run(['bash', '-euc', init_choice],
                                env={**env, 'GM8_TEST_NATIVE_LFS': native},
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

    # Exercise the complete real post-validation bootstrap control flow.
    # A native-capable repo may have left an earlier checkout as pointers;
    # capability detection must not skip materialization or audit gating.
    workflow = 'repo_init_args=' + bootstrap.split('repo_init_args=', 1)[1]
    manifest = fixture / 'reviewed.xml'; manifest.write_text('<manifest />\n')
    for name, native, fail in (('legacy', '0', False), ('native', '1', False),
                               ('native-failed-lfs', '1', True)):
        work = fixture / name; work.mkdir()
        apk_project = work / 'external/chromium-webview/prebuilt/arm64'
        apk_project.parent.mkdir(parents=True)
        run('git', 'clone', '--origin', 'fixture-lfs', str(remote), str(apk_project),
            extra_env={'GIT_LFS_SKIP_SMUDGE': '1'})
        assert (apk_project / 'webview.apk').read_bytes() == pointer
        if fail:
            run('git', 'config', 'lfs.url', (fixture / 'missing-lfs-server').as_uri(),
                cwd=apk_project)
        audit_marker = work / 'audit-ran'
        build = work / 'device/gm/GM8_sprout/tools/build-20.0.sh'
        build.parent.mkdir(parents=True)
        build.write_text('set -eu\ntest "$1" = audit\n'
                         'touch "$GM8_TEST_AUDIT_MARKER"\n')
        outcome = run('bash', '-euo', 'pipefail', '-c', workflow, cwd=work, checked=False,
                      extra_env={'GM8_TEST_NATIVE_LFS': native,
                                 'GM8_TEST_LFS_PROJECT': str(apk_project),
                                 'GM8_TEST_AUDIT_MARKER': str(audit_marker),
                                 'manifest': str(manifest), 'android_parent': str(work)})
        assert (outcome.returncode != 0) == fail, outcome.stdout + outcome.stderr
        assert audit_marker.exists() == (not fail)
        assert (apk_project / 'webview.apk').read_bytes() == (pointer if fail else payload)
        print('PASS:', name, '— real bootstrap materialization/audit gate')
