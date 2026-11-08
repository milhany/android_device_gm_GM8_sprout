#!/usr/bin/env python3
"""Exercise real SDK33 audit and bootstrap validation with local fixtures."""
import contextlib
import importlib.util
import io
import json
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
for name in ('fresh', 'wrong-sdk', 'old-manifest', 'nonempty', 'bad-remote', 'low-space'):
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
        assert success == (name == 'fresh'), name
        after = {str(p.relative_to(parent)): p.read_bytes() for p in parent.rglob('*') if p.is_file()}
        assert before == after
        print('PASS:', name, '— actual bootstrap validator preserves existing files')
