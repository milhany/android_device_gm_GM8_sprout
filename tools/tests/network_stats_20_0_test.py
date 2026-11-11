#!/usr/bin/env python3
"""Compile real GM8 qtaguid text writers, TrafficStats readers and JNI dispatch with native fixtures."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'tools/apply-network-stats-20.0.py'
PATCH = ROOT / 'patches/sdk33/Connectivity/0001-gm8-legacy-traffic-stats-readers.patch'
SOURCE = KERNEL = None


def run(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def body(text, signature):
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


class NetworkStatsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gm8-sdk33-netstats-')
        self.addCleanup(self.temp.cleanup)
        self.top = Path(self.temp.name)
        self.project = self.top / 'packages/modules/Connectivity'
        self.source = self.project / 'service-t/jni/com_android_server_net_NetworkStatsService.cpp'
        self.source.parent.mkdir(parents=True)
        self.source.write_text(SOURCE.read_text())
        self.header = self.source.with_name('LegacyTrafficStats.h')
        original_header = SOURCE.with_name('LegacyTrafficStats.h')
        if original_header.exists():
            self.header.write_bytes(original_header.read_bytes())
        self.assertEqual(run(['git', 'init', '-q'], self.project).returncode, 0)
        if self.apply('--reverse', '--check').returncode == 0:
            self.assertEqual(self.apply('--reverse').returncode, 0)
        self.version = self.top / 'build/core/version_defaults.mk'
        self.version.parent.mkdir(parents=True)
        self.version.write_text('PLATFORM_SDK_VERSION := 33\n')
        with self.source.open('a') as stream:
            stream.write('\n// unrelated local edit remains\n')
        self.before = self.source.read_bytes()

    def apply(self, *flags):
        return run(['git', 'apply', *flags, str(PATCH)], self.project)

    def helper(self, *flags):
        return run([sys.executable, str(HELPER), '--top', str(self.top), *flags])

    def test_apply_repeat_check_and_reverse_preserve_work(self):
        result = self.helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        applied, header = self.source.read_bytes(), self.header.read_bytes()
        self.assertEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.helper().returncode, 0)
        self.assertEqual(self.source.read_bytes(), applied)
        self.assertEqual(self.header.read_bytes(), header)
        self.assertEqual(self.apply('--reverse').returncode, 0)
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertFalse(self.header.exists())

    def test_check_does_not_apply(self):
        self.assertNotEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertFalse(self.header.exists())

    def test_wrong_sdk_refuses_before_changing_source(self):
        self.version.write_text('PLATFORM_SDK_VERSION := 32\n')
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertFalse(self.header.exists())

    def test_context_conflict_is_not_overwritten(self):
        self.source.write_text(self.source.read_text().replace('#include <cutils/qtaguid.h>',
                                                               '// locally changed include'))
        before = self.source.read_bytes()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.header.exists())

    def test_existing_header_is_not_overwritten(self):
        self.header.write_text('unrelated private header\n')
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertEqual(self.header.read_text(), 'unrelated private header\n')

    def test_actual_kernel_format_reader_and_mode_dispatch(self):
        result = self.helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        source = self.source.read_text()
        functions = '\n\n'.join(body(source, signature) + (';' if signature.startswith('enum ') else '')
                                for signature in (
                                    'enum StatsType ', 'static uint64_t getStatsType(',
                                    'static bool useBpfTrafficStats(', 'static jlong getTotalStat(',
                                    'static jlong getIfaceStat(', 'static jlong getUidStat('))
        kernel = KERNEL.read_text()
        writers = '\n\n'.join(body(kernel, signature) for signature in (
            'static void pp_iface_stat_header(', 'static void pp_iface_stat_line('))
        fixture = Path(__file__).with_name('network_stats_20_0_fixture.cpp').read_text()
        fixture = fixture.replace('// JNI_FUNCTIONS', 'static const uint64_t UNKNOWN = -1;\n' + functions)
        fixture = fixture.replace('// KERNEL_FUNCTIONS', writers)
        cpp = self.top / 'fixture.cpp'
        cpp.write_text(fixture)
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'Install a native C++ compiler for host regression.')
        binary = self.top / 'fixture'
        compiled = run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', '-I', str(self.source.parent), str(cpp), '-o', str(binary)])
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        for mode in ('enabled', 'disabled', 'default'):
            result = run([str(binary), mode, str(self.top / mode)])
            self.assertEqual(result.returncode, 0, (mode, result.stderr))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    args = parser.parse_args()
    SOURCE, KERNEL = args.source.resolve(strict=True), args.kernel.resolve(strict=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
