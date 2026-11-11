#!/usr/bin/env python3
"""Compile the actual patched firewall and Binder bridge with Android/iptables fixtures."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'tools/apply-firewall-20.0.py'
PATCH = ROOT / 'patches/sdk33/system_netd/0001-gm8-legacy-uid-firewall.patch'
TOP = None


def run(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def body(text, signature):
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


class FirewallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gm8-sdk33-firewall-')
        self.addCleanup(self.temp.cleanup)
        self.top = Path(self.temp.name)
        self.project = self.top / 'system/netd'
        self.server = self.project / 'server'
        self.server.mkdir(parents=True)
        for name in ('FirewallController.cpp', 'FirewallController.h', 'NetdNativeService.cpp', 'LegacyUidFirewall.h'):
            source = TOP / 'system/netd/server' / name
            if source.is_file(): shutil.copyfile(source, self.server / name)
        self.assertEqual(run(['git', 'init', '-q'], self.project).returncode, 0)
        if self.apply('--reverse', '--check').returncode == 0:
            self.assertEqual(self.apply('--reverse').returncode, 0)
        self.version = self.top / 'build/core/version_defaults.mk'
        self.version.parent.mkdir(parents=True)
        self.version.write_text('PLATFORM_SDK_VERSION := 33\n')
        self.source = self.server / 'FirewallController.cpp'
        with self.source.open('a') as stream: stream.write('\n// unrelated local edit remains\n')
        self.before = {p.name: p.read_bytes() for p in self.server.iterdir()}

    def apply(self, *flags):
        return run(['git', 'apply', *flags, str(PATCH)], self.project)

    def helper(self, *flags):
        return run([sys.executable, str(HELPER), '--top', str(self.top), *flags])

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.server.iterdir()}

    def test_apply_check_repeat_and_reverse_preserve_edits(self):
        result = self.helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.snapshot()
        self.assertEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(self.apply('--reverse').returncode, 0)
        self.assertEqual(self.snapshot(), self.before)

    def test_check_and_wrong_sdk_do_not_apply(self):
        self.assertNotEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.snapshot(), self.before)
        self.version.write_text('PLATFORM_SDK_VERSION := 32\n')
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), self.before)

    def test_conflicting_source_is_not_overwritten(self):
        self.source.write_text(self.source.read_text().replace('int FirewallController::setupIptablesHooks(',
                                                               'int FirewallController::differentHooks('))
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_existing_header_is_not_overwritten(self):
        (self.server / 'LegacyUidFirewall.h').write_text('private header\n')
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_sdk33_ids_and_kernel_owner_accounting_contract(self):
        text = (TOP / 'packages/modules/Connectivity/framework/src/android/net/ConnectivityManager.java').read_text()
        for name, value in {'DOZABLE': 1, 'STANDBY': 2, 'POWERSAVE': 3, 'RESTRICTED': 4,
                            'LOW_POWER_STANDBY': 5, 'LOCKDOWN_VPN': 6,
                            'OEM_DENY_1': 7, 'OEM_DENY_2': 8, 'OEM_DENY_3': 9}.items():
            self.assertRegex(text, rf'FIREWALL_CHAIN_{name}\s*=\s*{value}\s*;')
        kernel = (TOP / 'kernel/gm/msm8937/net/netfilter/xt_qtaguid.c').read_text()
        self.assertRegex(kernel, r'\.name\s*=\s*"owner"')
        self.assertRegex(kernel, r'bool\s+do_tag_stat\s*=\s*!\(info->match\s*&\s*XT_QTAGUID_UID\)')
        self.assertRegex(kernel, r'make_kuid\(&init_user_ns,\s*info->uid_min\)')
        self.assertRegex(kernel, r'make_kuid\(&init_user_ns,\s*info->uid_max\)')

    def test_actual_controller_rpc_and_rule_behavior(self):
        applied = self.helper()
        self.assertEqual(applied.returncode, 0, applied.stderr)
        host = self.top / 'host'
        (host / 'server').mkdir(parents=True)
        for name in ('FirewallController.cpp', 'FirewallController.h', 'LegacyUidFirewall.h'):
            shutil.copyfile(self.server / name, host / 'server' / name)
        # AOSP's unchanged out-of-class auto function-pointer definition is
        # accepted by its Clang but rejected by native GCC. Spell only that
        # declaration's existing header type explicitly in the host fixture.
        host_source = host / 'server/FirewallController.cpp'
        host_source.write_text(host_source.read_text().replace(
            'auto FirewallController::execIptablesRestore = ::execIptablesRestore;',
            'int (*FirewallController::execIptablesRestore)(IptablesTarget, const std::string&) = ::execIptablesRestore;'))
        (host / 'server/NetdConstants.h').write_text('''#pragma once
#include <cstdint>
#include <string>
#include <sys/types.h>
enum IptablesTarget { V4, V6, V4V6 };
int execIptablesRestore(IptablesTarget, const std::string&);
bool isIfaceName(const std::string&);
#define ARRAY_SIZE(a) (sizeof(a)/sizeof(*(a)))
namespace android::net {
enum FirewallRule { ALLOW=1, DENY=2 };
enum FirewallType { ALLOWLIST=0, DENYLIST=1 };
}
''')
        for path in ('server/Controllers.h', 'android-base/file.h', 'android-base/properties.h',
                     'android-base/stringprintf.h', 'android-base/strings.h', 'log/log.h', 'bpf/BpfUtils.h'):
            target = host / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('#pragma once\n')
        rpc = (self.server / 'NetdNativeService.cpp').read_text()
        methods = '\n\n'.join(body(rpc, signature) for signature in (
            'binder::Status NetdNativeService::firewallReplaceUidChain(',
            'binder::Status NetdNativeService::firewallSetUidRule(',
            'binder::Status NetdNativeService::firewallEnableChildChain('))
        fixture = Path(__file__).with_name('firewall_20_0_fixture.cpp').read_text()
        cpp = host / 'fixture.cpp'
        cpp.write_text(fixture.replace('// RPC_FUNCTIONS', methods))
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'Install a native C++ compiler for host regression.')
        binary = host / 'fixture'
        built = run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(host),
                     str(cpp), '-o', str(binary)])
        self.assertEqual(built.returncode, 0, built.stderr)
        for mode in ('legacy', 'modern', 'default'):
            result = run([str(binary), mode])
            self.assertEqual(result.returncode, 0, (mode, result.stderr))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    TOP = args.top.resolve(strict=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
