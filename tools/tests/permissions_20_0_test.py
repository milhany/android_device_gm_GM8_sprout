#!/usr/bin/env python3
"""Exercise SDK33 permission routing and real PermissionMonitor grouping with host fixtures."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOP = None
HELPER = ROOT / 'tools/apply-permissions-20.0.py'
POLICY = ROOT / 'tools/apply-network-policy-20.0.py'
PATCH = ROOT / 'patches/sdk33/Connectivity/0003-gm8-legacy-permission-routing.patch'


def run(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True)


def body(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        if source[end] == '{': depth += 1
        if source[end] == '}': depth -= 1
        end += 1
    return source[start:end]


class PermissionTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='gm8-sdk33-permissions-')
        self.addCleanup(temp.cleanup)
        self.top = Path(temp.name)
        for project, paths in {
            'system/netd': ['server/' + n for n in ('Android.bp', 'Controllers.h',
                'FwmarkServer.cpp', 'NetdNativeService.cpp', 'FirewallController.cpp',
                'FirewallController.h', 'LegacyUidFirewall.h', 'BandwidthController.cpp',
                'BandwidthController.h', 'LegacyBandwidthRules.h', 'LegacySocketTagger.cpp',
                'LegacySocketTagger.h')],
            'packages/modules/Connectivity': ['service/src/com/android/server/BpfNetMaps.java',
                'service/src/com/android/server/connectivity/PermissionMonitor.java'],
        }.items():
            for path in paths:
                source = TOP / project / path
                if source.is_file():
                    target = self.top / project / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            self.assertEqual(run(['git', 'init', '-q'], self.top / project).returncode, 0)
        self.project = self.top / 'packages/modules/Connectivity'
        if self.apply('--reverse', '--check').returncode == 0:
            self.assertEqual(self.apply('--reverse').returncode, 0)
        self.version = self.top / 'build/core/version_defaults.mk'
        self.version.parent.mkdir(parents=True)
        self.version.write_text('PLATFORM_SDK_VERSION := 33\n')
        self.java = self.project / 'service/src/com/android/server/BpfNetMaps.java'
        with self.java.open('a') as f: f.write('\n// unrelated local Java edit\n')
        self.before = self.snapshot()

    def snapshot(self):
        return {str(p.relative_to(self.top)): p.read_bytes() for p in self.top.rglob('*')
                if p.is_file() and '.git' not in p.parts}

    def apply(self, *flags):
        return run(['git', 'apply', *flags, str(PATCH)], self.project)

    def helper(self, *flags):
        return run([sys.executable, str(HELPER), '--top', str(self.top), *flags])

    def test_apply_check_repeat_reverse_and_predecessor_validation(self):
        self.assertNotEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.snapshot(), self.before)
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        after = self.snapshot()
        self.assertEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.helper().returncode, 0)
        result = run([sys.executable, str(POLICY), '--top', str(self.top), '--check'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(self.apply('--reverse').returncode, 0)
        self.assertEqual(self.snapshot(), self.before)

    def test_missing_native_backend_is_not_silently_accepted(self):
        native = ROOT / 'patches/sdk33/system_netd/0003-gm8-legacy-socket-tagging.patch'
        result = run(['git', 'apply', '--reverse', str(native)], self.top / 'system/netd')
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_source_conflict_and_wrong_sdk_are_read_only(self):
        self.java.write_text(self.java.read_text().replace('"Socket permission synchronization"', '"custom permission routing"'))
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)
        self.version.write_text('PLATFORM_SDK_VERSION := 32\n')
        before = self.snapshot()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_successor_does_not_hide_unreviewed_predecessor(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        self.java.write_text(self.java.read_text().replace('private static final String TAG', 'private static final String OTHER_TAG'))
        before = self.snapshot()
        self.assertNotEqual(self.helper('--check').returncode, 0)
        result = run([sys.executable, str(POLICY), '--top', str(self.top), '--check'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_audit_recognizes_verified_predecessor_without_changing_sources(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        device = self.top / 'device/gm/GM8_sprout'
        (device / 'tools').mkdir(parents=True)
        shutil.copytree(ROOT / 'patches/sdk33', device / 'patches/sdk33')
        for name in ('apply-network-policy-20.0.py', 'apply-socket-20.0.py'):
            shutil.copyfile(ROOT / 'tools' / name, device / 'tools' / name)
        spec = importlib.util.spec_from_file_location('gm8_permissions_audit', ROOT / 'tools/preflight-20.0.py')
        audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
        before = self.snapshot()
        report = audit.audit(self.top)
        port = next(p for p in report['sdk33_source_ports'] if p['patch'].endswith(
            'Connectivity/0002-gm8-legacy-network-policy-routing.patch'))
        self.assertTrue(port['applied'] and port['verified_with_successor'])
        self.assertFalse(port['hardware_accepted'] or report['ready_for_boot_image'])
        self.assertEqual(self.snapshot(), before)

    def test_real_java_and_permission_monitor_error_paths(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        host = self.top / 'java'; (host / 'com/android/server').mkdir(parents=True)
        shutil.copyfile(self.java, host / 'com/android/server/BpfNetMaps.java')
        shutil.copyfile(Path(__file__).with_name('NetworkPolicyFixture.java'), host / 'com/android/server/NetworkPolicyFixture.java')
        monitor = self.project / 'service/src/com/android/server/connectivity/PermissionMonitor.java'
        method = body(monitor.read_text(), 'void sendAppIdsTrafficPermission(')
        fixture = Path(__file__).with_name('PermissionRoutingFixture.java').read_text()
        (host / 'com/android/server/PermissionRoutingFixture.java').write_text(
            fixture.replace('// ACTUAL_PERMISSION_MONITOR_METHOD', method))
        stubs = {
            'android/os/RemoteException.java': 'package android.os; public class RemoteException extends Exception { public RemoteException(String s){super(s);} }',
            'android/os/ServiceSpecificException.java': 'package android.os; public class ServiceSpecificException extends RuntimeException { public final int errorCode; public ServiceSpecificException(int c,String s){super(s);errorCode=c;} }',
            'android/os/SystemProperties.java': 'package android.os; public class SystemProperties {public static boolean getBoolean(String k,boolean d){return Boolean.parseBoolean(System.getProperty(k,Boolean.toString(d)));}}',
            'android/system/OsConstants.java': 'package android.system; public class OsConstants { public static final int EOPNOTSUPP=95,ENODEV=19,EIO=5;}',
            'android/system/Os.java': 'package android.system; public class Os {public static String strerror(int n){return Integer.toString(n);}}',
            'android/util/Log.java': 'package android.util; public class Log {public static int errors;public static int e(String t,String s){errors++;return 0;}}',
            'android/util/SparseIntArray.java': '''package android.util;
import java.util.TreeMap;
import java.util.ArrayList;
public class SparseIntArray {
 final TreeMap<Integer,Integer> entries = new TreeMap<>();
 public void put(int key,int value){entries.put(key,value);}
 public int size(){return entries.size();}
 public int keyAt(int i){return new ArrayList<>(entries.keySet()).get(i);}
 public int valueAt(int i){return new ArrayList<>(entries.values()).get(i);}
}''',
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
        for name, content in stubs.items():
            path = host / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
        candidates = [TOP / 'prebuilts/jdk/jdk11/linux-x86/bin/java', TOP / 'prebuilts/jdk/jdk17/linux-x86/bin/java',
                      Path(shutil.which('java') or '/nonexistent'), Path('/usr/lib/jvm/default-java/bin/java')]
        java = next((str(p) for p in candidates if p.is_file()), None)
        self.assertIsNotNone(java)
        classes = host / 'classes'; classes.mkdir()
        built = run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-source', '8', '-target', '8',
                     '-d', str(classes)] + [str(p) for p in host.rglob('*.java')])
        self.assertEqual(built.returncode, 0, built.stderr)
        for mode in ('legacy', 'pret', 'modern', 'default'):
            flags = ['-Dgm8.sdk.t=' + ('false' if mode == 'pret' else 'true')]
            if mode != 'default': flags += ['-Dro.kernel.ebpf.supported=' + ('false' if mode == 'legacy' else 'true')]
            result = run([java, '-ea', *flags, '-cp', str(classes), 'com.android.server.PermissionRoutingFixture', mode])
            self.assertEqual(result.returncode, 0, (mode, result.stderr))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    TOP = parser.parse_args().top.resolve(strict=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
