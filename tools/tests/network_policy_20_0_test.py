#!/usr/bin/env python3
"""Test paired SDK33 policy patches, real Java routing and native bandwidth bodies with fixtures."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'tools/apply-network-policy-20.0.py'
TOP = None


def run(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def body(text, signature):
    start = text.index(signature)
    opening = text.index('}) {', start) + 3 if signature.endswith('::BandwidthController()') else text.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gm8-sdk33-policy-')
        self.addCleanup(self.temp.cleanup)
        self.top = Path(self.temp.name)
        for project, paths in {
            'system/netd': ['server/' + n for n in ('FirewallController.cpp', 'FirewallController.h',
                'LegacyUidFirewall.h', 'BandwidthController.cpp', 'BandwidthController.h',
                'LegacyBandwidthRules.h', 'NetdNativeService.cpp')],
            'packages/modules/Connectivity': ['service/src/com/android/server/BpfNetMaps.java'],
        }.items():
            for path in paths:
                source = TOP / project / path
                if source.is_file():
                    target = self.top / project / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            self.assertEqual(run(['git', 'init', '-q'], self.top / project).returncode, 0)
        for project, patch in self.patches():
            if self.apply(project, patch, '--reverse', '--check').returncode == 0:
                self.assertEqual(self.apply(project, patch, '--reverse').returncode, 0)
            elif project == 'packages/modules/Connectivity':
                previous = patch.read_text().replace('EIO', 'EREMOTEIO')
                checked = subprocess.run(['git', 'apply', '--reverse', '--check', '-'],
                    input=previous, text=True, capture_output=True, cwd=self.top / project)
                if checked.returncode == 0:
                    reverted = subprocess.run(['git', 'apply', '--reverse', '-'],
                        input=previous, text=True, capture_output=True, cwd=self.top / project)
                    self.assertEqual(reverted.returncode, 0, reverted.stderr)
        self.version = self.top / 'build/core/version_defaults.mk'
        self.version.parent.mkdir(parents=True)
        self.version.write_text('PLATFORM_SDK_VERSION := 33\n')
        self.bw = self.top / 'system/netd/server/BandwidthController.cpp'
        self.java = self.top / 'packages/modules/Connectivity/service/src/com/android/server/BpfNetMaps.java'
        with self.bw.open('a') as f: f.write('\n// preserve unrelated bandwidth edit\n')
        self.before = self.snapshot()

    def patches(self):
        return [('system/netd', ROOT / 'patches/sdk33/system_netd/0002-gm8-legacy-bandwidth-policy.patch'),
                ('packages/modules/Connectivity', ROOT / 'patches/sdk33/Connectivity/0002-gm8-legacy-network-policy-routing.patch')]

    def apply(self, project, patch, *flags):
        return run(['git', 'apply', *flags, str(patch)], self.top / project)

    def helper(self, *flags):
        return run([sys.executable, str(HELPER), '--top', str(self.top), *flags])

    def snapshot(self):
        return {str(p.relative_to(self.top)): p.read_bytes() for p in self.top.rglob('*')
                if p.is_file() and '.git' not in p.parts}

    def test_apply_repeat_and_reverse_preserve_edits(self):
        applied = self.helper()
        self.assertEqual(applied.returncode, 0, applied.stderr)
        after = self.snapshot()
        self.assertEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), after)
        for project, patch in reversed(self.patches()):
            self.assertEqual(self.apply(project, patch, '--reverse').returncode, 0)
        self.assertEqual(self.snapshot(), self.before)

    def test_check_and_wrong_sdk_do_not_apply(self):
        self.assertNotEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.snapshot(), self.before)
        self.version.write_text('PLATFORM_SDK_VERSION := 32\n')
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_previous_errno_patch_upgrades_without_losing_edits(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        self.java.write_text(self.java.read_text().replace('EIO', 'EREMOTEIO')
                             + '\n// preserve unrelated Java edit\n')
        before = self.snapshot()
        self.assertNotEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.snapshot(), before)
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        after = self.snapshot()
        self.assertNotIn('EREMOTEIO', self.java.read_text())
        self.assertIn('// preserve unrelated Java edit', self.java.read_text())
        self.assertEqual(after['system/netd/server/BandwidthController.cpp'],
                         before['system/netd/server/BandwidthController.cpp'])
        self.assertEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), after)

    def test_unreviewed_old_errno_source_is_not_upgraded(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        self.java.write_text(self.java.read_text().replace('EIO', 'EREMOTEIO')
                             .replace('private static final String TAG', 'private static final String OTHER_TAG'))
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_second_project_conflict_does_not_partially_apply(self):
        self.java.write_text(self.java.read_text().replace('private static final String TAG', 'private static final String OTHER_TAG'))
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_prerequisite_and_existing_header_are_not_overwritten(self):
        prior = ROOT / 'patches/sdk33/system_netd/0001-gm8-legacy-uid-firewall.patch'
        self.assertEqual(self.apply('system/netd', prior, '--reverse').returncode, 0)
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.apply('system/netd', prior).returncode, 0)
        (self.bw.parent / 'LegacyBandwidthRules.h').write_text('private header\n')
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_native_bandwidth_and_rpc(self):
        original = self.bw.read_text()
        applied = self.helper()
        self.assertEqual(applied.returncode, 0, applied.stderr)
        source = self.bw.read_text()
        host = self.top / 'native'; (host / 'server').mkdir(parents=True)
        for name in ('BandwidthController.h', 'LegacyBandwidthRules.h'):
            shutil.copyfile(self.bw.parent / name, host / 'server' / name)
        (host / 'server/NetdConstants.h').write_text('''#pragma once
#include <cstdint>
#include <string>
#include <sys/types.h>
enum IptablesTarget { V4, V6, V4V6 };
int execIptablesRestore(IptablesTarget,const std::string&);
bool isIfaceName(const std::string&);
''')
        methods = '\n\n'.join(body(source, sig) for sig in (
            'BandwidthController::BandwidthController()',
            'int BandwidthController::setupIptablesHooks(',
            'int BandwidthController::enableBandwidthControl(', 'int BandwidthController::disableBandwidthControl(',
            'std::string BandwidthController::makeDataSaverCommand(', 'int BandwidthController::enableDataSaver(',
            'int BandwidthController::addNaughtyApps(', 'int BandwidthController::removeNaughtyApps(',
            'int BandwidthController::addNiceApps(', 'int BandwidthController::removeNiceApps('))
        rpc = (self.bw.parent / 'NetdNativeService.cpp').read_text()
        bridges = '\n\n'.join(body(rpc, 'binder::Status NetdNativeService::' + name + '(') for name in (
            'bandwidthAddNaughtyApp', 'bandwidthRemoveNaughtyApp', 'bandwidthAddNiceApp',
            'bandwidthRemoveNiceApp', 'bandwidthEnableDataSaver'))
        accounting = body(source, 'std::vector<std::string> getBasicAccountingCommands(')
        baseline = body(original, 'std::vector<std::string> getBasicAccountingCommands(').replace(
            'getBasicAccountingCommands', 'getOriginalAccountingCommands')
        fixture = Path(__file__).with_name('network_policy_20_0_fixture.cpp').read_text()
        fixture = fixture.replace('// ACCOUNTING_FUNCTIONS', baseline + '\n' + accounting)
        fixture = fixture.replace('// BANDWIDTH_FUNCTIONS', methods).replace('// BANDWIDTH_RPC', bridges)
        cpp = host / 'fixture.cpp'; cpp.write_text(fixture)
        compiler = shutil.which('c++'); self.assertIsNotNone(compiler)
        built = run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(host), str(cpp), '-o', str(host / 'fixture')])
        self.assertEqual(built.returncode, 0, built.stderr)
        for mode in ('legacy', 'modern', 'default'):
            result = run([str(host / 'fixture'), mode])
            self.assertEqual(result.returncode, 0, (mode, result.stderr))

    def test_real_java_routing_and_initialization(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        host = self.top / 'java'; (host / 'com/android/server').mkdir(parents=True)
        shutil.copyfile(self.java, host / 'com/android/server/BpfNetMaps.java')
        shutil.copyfile(Path(__file__).with_name('NetworkPolicyFixture.java'), host / 'com/android/server/NetworkPolicyFixture.java')
        stubs = {
            'android/os/RemoteException.java': 'package android.os; public class RemoteException extends Exception { public RemoteException(String s) {super(s);} }',
            'android/os/ServiceSpecificException.java': 'package android.os; public class ServiceSpecificException extends RuntimeException { public final int errorCode; public ServiceSpecificException(int c,String s){super(s);errorCode=c;} }',
            'android/os/SystemProperties.java': 'package android.os; public class SystemProperties {public static boolean getBoolean(String k,boolean d){return Boolean.parseBoolean(System.getProperty(k,Boolean.toString(d)));}}',
            'android/system/OsConstants.java': 'package android.system; public class OsConstants { public static final int EOPNOTSUPP=95,ENODEV=19,EIO=5;}',
            'android/system/Os.java': 'package android.system; public class Os {public static String strerror(int n){return Integer.toString(n);}}',
            'android/util/Log.java': 'package android.util; public class Log {public static int e(String t,String s){return 0;}}',
            'com/android/modules/utils/build/SdkLevel.java': 'package com.android.modules.utils.build; public class SdkLevel {public static boolean isAtLeastT(){return Boolean.parseBoolean(System.getProperty("gm8.sdk.t","true"));}}',
            'com/android/internal/annotations/VisibleForTesting.java': 'package com.android.internal.annotations; public @interface VisibleForTesting {}',
            'android/net/INetd.java': '''package android.net;
import android.os.RemoteException;
public interface INetd {
 void bandwidthAddNaughtyApp(int uid) throws RemoteException;
 void bandwidthRemoveNaughtyApp(int uid) throws RemoteException;
 void bandwidthAddNiceApp(int uid) throws RemoteException;
 void bandwidthRemoveNiceApp(int uid) throws RemoteException;
 void firewallEnableChildChain(int chain,boolean enable) throws RemoteException;
 void firewallSetUidRule(int chain,int uid,int rule) throws RemoteException;
 boolean firewallReplaceUidChain(String name,boolean allow,int[] uids) throws RemoteException;
 void firewallAddUidInterfaceRules(String iface,int[] uids) throws RemoteException;
 void firewallRemoveUidInterfaceRules(int[] uids) throws RemoteException;
 void trafficSetNetPermForUids(int permissions,int[] uids) throws RemoteException;
}'''}
        for name, text in stubs.items():
            path = host / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        candidates = [TOP / 'prebuilts/jdk/jdk11/linux-x86/bin/java', TOP / 'prebuilts/jdk/jdk17/linux-x86/bin/java',
                      Path(shutil.which('java') or '/nonexistent'), Path('/usr/lib/jvm/default-java/bin/java')]
        java = next((str(p) for p in candidates if p.is_file()), None)
        self.assertIsNotNone(java, 'A Java runtime with jdk.compiler is required for host checks.')
        classes = host / 'classes'; classes.mkdir()
        # Minimal runtimes can contain jdk.compiler without ct.sym; use source/
        # target language selection. Android APIs are fixtures, not SDK validation.
        built = run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-source', '8', '-target', '8', '-d', str(classes)] +
                    [str(p) for p in host.rglob('*.java')])
        self.assertEqual(built.returncode, 0, built.stderr)
        for mode in ('legacy', 'modern', 'default', 'pret', 'load-failure'):
            flags = ['-Dgm8.sdk.t=' + ('false' if mode == 'pret' else 'true')]
            if mode != 'default': flags += ['-Dro.kernel.ebpf.supported=' + ('false' if mode == 'legacy' else 'true')]
            result = run([java, '-ea', *flags, '-cp', str(classes), 'com.android.server.NetworkPolicyFixture', mode])
            self.assertEqual(result.returncode, 0, (mode, result.stderr))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--top', type=Path, required=True)
    TOP = p.parse_args().top.resolve(strict=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
