#!/usr/bin/env python3
"""Validate actual SDK33 socket/backend/RPC bodies with host fixtures, not Android."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOP = None
HELPER = ROOT / 'tools/apply-socket-20.0.py'
PATCH = ROOT / 'patches/sdk33/system_netd/0003-gm8-legacy-socket-tagging.patch'


def run(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True)


def body(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


class SocketTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='gm8-sdk33-socket-')
        self.addCleanup(temp.cleanup)
        self.top = Path(temp.name)
        self.netd = self.top / 'system/netd'
        server = self.netd / 'server'; server.mkdir(parents=True)
        for name in ('Android.bp', 'Controllers.h', 'FwmarkServer.cpp', 'NetdNativeService.cpp',
                     'FirewallController.cpp', 'FirewallController.h', 'LegacyUidFirewall.h',
                     'BandwidthController.cpp', 'BandwidthController.h', 'LegacyBandwidthRules.h',
                     'LegacySocketTagger.cpp', 'LegacySocketTagger.h'):
            src = TOP / 'system/netd/server' / name
            if src.is_file(): shutil.copyfile(src, server / name)
        self.assertEqual(run(['git', 'init', '-q'], self.netd).returncode, 0)
        if self.apply('--reverse', '--check').returncode == 0:
            self.assertEqual(self.apply('--reverse').returncode, 0)
        self.version = self.top / 'build/core/version_defaults.mk'
        self.version.parent.mkdir(parents=True)
        self.version.write_text('PLATFORM_SDK_VERSION := 33\n')
        with (server / 'FwmarkServer.cpp').open('a') as f: f.write('\n// retain local fwmark edit\n')
        self.before = self.snapshot()

    def snapshot(self):
        return {str(p.relative_to(self.top)): p.read_bytes() for p in self.top.rglob('*')
                if p.is_file() and '.git' not in p.parts}

    def apply(self, *flags):
        return run(['git', 'apply', *flags, str(PATCH)], self.netd)

    def helper(self, *flags):
        return run([sys.executable, str(HELPER), '--top', str(self.top), *flags])

    def test_apply_repeat_check_and_reverse(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        after = self.snapshot()
        self.assertEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(self.apply('--reverse').returncode, 0)
        self.assertEqual(self.snapshot(), self.before)

    def test_check_and_wrong_sdk_are_read_only(self):
        self.assertNotEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.snapshot(), self.before)
        self.version.write_text('PLATFORM_SDK_VERSION := 32\n')
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_conflict_or_private_header_prevents_partial_write(self):
        fwmark = self.netd / 'server/FwmarkServer.cpp'
        fwmark.write_text(fwmark.read_text().replace('return libnetd_updatable_tagSocket(', 'return custom_tagSocket('))
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)
        fwmark.write_bytes(self.before['system/netd/server/FwmarkServer.cpp'])
        (self.netd / 'server/LegacySocketTagger.h').write_text('private header\n')
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_missing_bandwidth_prerequisite_refuses_changes(self):
        prior = ROOT / 'patches/sdk33/system_netd/0002-gm8-legacy-bandwidth-policy.patch'
        result = run(['git', 'apply', '--reverse', str(prior)], self.netd)
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_native_backend_and_real_fwmark_binder_bridges(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        host = self.top / 'host'; host.mkdir()
        server = self.netd / 'server'
        for name in ('LegacySocketTagger.cpp', 'LegacySocketTagger.h'):
            shutil.copyfile(server / name, host / name)
        (host / 'netdutils').mkdir(); (host / 'private').mkdir()
        (host / 'netdutils/UidConstants.h').write_text('#pragma once\nconstexpr unsigned PER_USER_RANGE = 100000;\n')
        (host / 'private/android_filesystem_config.h').write_text('#pragma once\n#define AID_ROOT 0\n#define AID_SYSTEM 1000\n#define AID_DNS 1051\n#define AID_CLAT 1029\n')
        fixture = Path(__file__).with_name('socket_20_0_fixture.cpp').read_text()
        rpc = body((server / 'NetdNativeService.cpp').read_text(), 'binder::Status NetdNativeService::trafficSetNetPermForUids(')
        fwmark = (server / 'FwmarkServer.cpp').read_text()
        tag = body(fwmark, 'case FwmarkCommand::TAG_SOCKET:')
        untag = body(fwmark, 'case FwmarkCommand::UNTAG_SOCKET:')
        fixture = fixture.replace('// BINDER_BODY', rpc)
        fixture = fixture.replace('// FWMARK_TAG_BODY', tag[tag.index('{') + 1:-1])
        fixture = fixture.replace('// FWMARK_UNTAG_BODY', untag[untag.index('{') + 1:-1])
        (host / 'fixture.cpp').write_text(fixture)
        compiler = shutil.which('c++'); self.assertIsNotNone(compiler)
        built = run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread', '-I', str(host),
                     str(host / 'fixture.cpp'), str(host / 'LegacySocketTagger.cpp'),
                     '-Wl,--wrap=getsockopt', '-Wl,--wrap=open', '-Wl,--wrap=close', '-Wl,--wrap=write', '-o', str(host / 'fixture')])
        self.assertEqual(built.returncode, 0, built.stderr)
        files = host / 'proc-fixture'; files.mkdir()
        result = run([str(host / 'fixture'), str(files)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    TOP = parser.parse_args().top.resolve(strict=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
