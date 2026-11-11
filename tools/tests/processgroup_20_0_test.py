#!/usr/bin/env python3
"""Exercise the SDK33 port helper and compiled real processgroup entry-point bodies."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'tools/apply-processgroup-20.0.py'
PATCH = ROOT / 'patches/sdk33/system_core/0001-gm8-cgroup-v1-process-tracking.patch'
SOURCE = None


def command(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


class ProcessgroupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gm8-sdk33-cgroups-')
        self.addCleanup(self.temp.cleanup)
        self.top = Path(self.temp.name)
        self.core = self.top / 'system/core'
        self.path = self.core / 'libprocessgroup/processgroup.cpp'
        self.path.parent.mkdir(parents=True)
        self.path.write_text(SOURCE.read_text())
        self.assertEqual(command(['git', 'init', '-q'], self.core).returncode, 0)
        self.version = self.top / 'build/core/version_defaults.mk'
        self.version.parent.mkdir(parents=True)
        self.version.write_text('PLATFORM_SDK_VERSION := 33\n')
        if self.git_apply('--reverse', '--check').returncode == 0:
            self.assertEqual(self.git_apply('--reverse').returncode, 0)
        # Keep a distinct real local edit outside patch hunks.
        with self.path.open('a') as stream:
            stream.write('\n// unrelated local edit preserved by SDK33 helper\n')
        self.before = self.path.read_bytes()

    def git_apply(self, *flags):
        return command(['git', 'apply', *flags, str(PATCH)], self.core)

    def helper(self, *flags):
        return command([sys.executable, str(HELPER), '--top', str(self.top), *flags])

    def test_apply_idempotence_and_preservation(self):
        result = self.helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        applied = self.path.read_bytes()
        self.assertIn(b'unrelated local edit preserved', applied)
        self.assertEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.helper().returncode, 0)
        self.assertEqual(self.path.read_bytes(), applied)
        self.assertEqual(self.git_apply('--reverse').returncode, 0)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_check_is_read_only(self):
        self.assertNotEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_wrong_sdk_does_not_modify_source(self):
        self.version.write_text('PLATFORM_SDK_VERSION := 32\n')
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_context_drift_is_not_overwritten(self):
        self.path.write_text(self.path.read_text().replace('static bool CgroupGetMemcgAppsPath(',
                                                          'static bool DifferentMemcgPath('))
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)

    def test_native_hierarchy_lifecycle_and_errors(self):
        result = self.helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        source = self.path.read_text()
        bodies = '\n\n'.join(function(source, signature) for signature in (
            'static bool GetProcessGroupControllerPath(',
            'void removeAllProcessGroupsInternal(',
            'static int KillProcessGroup(',
            'int createProcessGroup(',
        ))
        fixture = (Path(__file__).with_name('processgroup_20_0_fixture.cpp')).read_text()
        cpp = self.top / 'fixture.cpp'
        cpp.write_text(fixture.replace('// GM8_FUNCTIONS', bodies))
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'Install a native C++ compiler for the host regression.')
        binary = self.top / 'fixture'
        # glibc annotates closedir in a way that GCC warns about as a template
        # deleter type. Android uses bionic; suppress only this host-header warning.
        result = command([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                          '-Wno-ignored-attributes',
                          str(cpp), '-o', str(binary)])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = command([str(binary), str(self.top / 'hierarchies')])
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    SOURCE = args.source.resolve(strict=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
