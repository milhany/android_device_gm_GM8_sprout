#!/usr/bin/env python3
"""Run the real snapshot factory using GM8 kernel text writers and Android/JNI fixtures."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOP = None
PATCH = ROOT / 'patches/sdk33/Connectivity/0004-gm8-legacy-cumulative-snapshots.patch'
HELPER = ROOT / 'tools/apply-snapshots-20.0.py'


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


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='gm8-sdk33-snapshots-')
        self.addCleanup(temp.cleanup)
        self.top = Path(temp.name)
        self.project = self.top / 'packages/modules/Connectivity'
        self.source = self.project / 'service-t/src/com/android/server/net/NetworkStatsFactory.java'
        self.source.parent.mkdir(parents=True)
        shutil.copyfile(TOP / 'packages/modules/Connectivity/service-t/src/com/android/server/net/NetworkStatsFactory.java', self.source)
        self.assertEqual(run(['git', 'init', '-q'], self.project).returncode, 0)
        if self.apply('--reverse', '--check').returncode == 0:
            self.assertEqual(self.apply('--reverse').returncode, 0)
        self.version = self.top / 'build/core/version_defaults.mk'
        self.version.parent.mkdir(parents=True)
        self.version.write_text('PLATFORM_SDK_VERSION := 33\n')
        with self.source.open('a') as stream: stream.write('\n// preserve local snapshot edit\n')
        self.before = self.source.read_bytes()

    def apply(self, *flags):
        return run(['git', 'apply', *flags, str(PATCH)], self.project)

    def helper(self, *flags):
        return run([sys.executable, str(HELPER), '--top', str(self.top), *flags])

    def test_apply_repeat_check_and_reverse(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        after = self.source.read_bytes()
        self.assertEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.helper().returncode, 0)
        self.assertEqual(self.source.read_bytes(), after)
        self.assertEqual(self.apply('--reverse').returncode, 0)
        self.assertEqual(self.source.read_bytes(), self.before)

    def test_check_wrong_sdk_and_source_conflict_are_read_only(self):
        self.assertNotEqual(self.helper('--check').returncode, 0)
        self.assertEqual(self.source.read_bytes(), self.before)
        self.source.write_text(self.source.read_text().replace('mBpfNetMaps = new BpfNetMaps();', 'mBpfNetMaps = null;'))
        before = self.source.read_bytes()
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.source.read_bytes(), before)
        self.source.write_bytes(self.before)
        self.version.write_text('PLATFORM_SDK_VERSION := 32\n')
        self.assertNotEqual(self.helper().returncode, 0)
        self.assertEqual(self.source.read_bytes(), self.before)

    def test_real_kernel_rows_factory_polling_filters_and_bpf_selection(self):
        result = self.helper(); self.assertEqual(result.returncode, 0, result.stderr)
        host = self.top / 'host'; host.mkdir()
        compiler = shutil.which('c++'); self.assertIsNotNone(compiler)
        kernel = (TOP / 'kernel/gm/msm8937/net/netfilter/xt_qtaguid.c').read_text()
        writers = '\n\n'.join(body(kernel, signature) for signature in (
            'static void pp_stats_header(', 'static int pp_stats_line(',
            'static void pp_iface_stat_header(', 'static void pp_iface_stat_line('))
        cpp = Path(__file__).with_name('SnapshotKernelFixture.cpp').read_text().replace('// ACTUAL_KERNEL_WRITERS', writers)
        (host / 'kernel.cpp').write_text(cpp)
        built = run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', str(host / 'kernel.cpp'), '-o', str(host / 'kernel')])
        self.assertEqual(built.returncode, 0, built.stderr)
        # This tiny JNI library deliberately rejects native legacy reads and fails
        # BPF reads. It tests dispatch/failure visibility, not Android JNI or BPF.
        (host / 'jni.cpp').write_text('''#include <cstdlib>
extern "C" int Java_com_android_server_net_NetworkStatsFactory_nativeReadNetworkStatsDetail(
    void*,void*,void*,void*,int,void*,int,unsigned char bpf) {if(!bpf)std::abort();return -1;}
extern "C" int Java_com_android_server_net_NetworkStatsFactory_nativeReadNetworkStatsDev(
    void*,void*,void*) {return -1;}
''')
        built = run([compiler, '-shared', '-fPIC', '-std=c++17', str(host / 'jni.cpp'), '-o', str(host / 'libservice-connectivity.so')])
        self.assertEqual(built.returncode, 0, built.stderr)
        source = host / 'src'; (source / 'com/android/server/net').mkdir(parents=True)
        shutil.copyfile(self.source, source / 'com/android/server/net/NetworkStatsFactory.java')
        shutil.copyfile(Path(__file__).with_name('CumulativeSnapshotFixture.java'), source / 'com/android/server/net/CumulativeSnapshotFixture.java')
        (source / 'android/net').mkdir(parents=True)
        shutil.copyfile(Path(__file__).with_name('NetworkStatsFixture.java'), source / 'android/net/NetworkStats.java')
        stubs = {
            'android/annotation/NonNull.java': 'package android.annotation; public @interface NonNull {}',
            'android/annotation/Nullable.java': 'package android.annotation; public @interface Nullable {}',
            'android/content/Context.java': 'package android.content; public class Context {}',
            'android/net/UnderlyingNetworkInfo.java': 'package android.net; public class UnderlyingNetworkInfo {public int getOwnerUid(){return 0;}public String getInterface(){return "tun0";}public String[] getUnderlyingInterfaces(){return new String[0];}}',
            'android/os/ServiceSpecificException.java': 'package android.os; public class ServiceSpecificException extends RuntimeException {}',
            'android/os/StrictMode.java': '''package android.os; public class StrictMode {
 public static class ThreadPolicy {} public static ThreadPolicy current = new ThreadPolicy();
 public static ThreadPolicy allowThreadDiskReads(){ThreadPolicy old=current;current=new ThreadPolicy();return old;}
 public static void setThreadPolicy(ThreadPolicy value){current=value;}
}''',
            'android/os/SystemClock.java': 'package android.os; public class SystemClock {private static long now;public static long elapsedRealtime(){return ++now;}}',
            'android/os/SystemProperties.java': 'package android.os; public class SystemProperties {public static boolean getBoolean(String key,boolean fallback){return Boolean.parseBoolean(System.getProperty(key,Boolean.toString(fallback)));}}',
            'com/android/internal/annotations/GuardedBy.java': 'package com.android.internal.annotations; public @interface GuardedBy {String value();}',
            'com/android/internal/annotations/VisibleForTesting.java': 'package com.android.internal.annotations; public @interface VisibleForTesting {}',
            'com/android/net/module/util/CollectionUtils.java': 'package com.android.net.module.util; public class CollectionUtils {public static <T> boolean contains(T[] values,T target){return java.util.Arrays.asList(values).contains(target);}}',
            'com/android/server/BpfNetMaps.java': 'package com.android.server; public class BpfNetMaps {public static int created,swaps;public BpfNetMaps(){created++;}public void swapActiveStatsMap(){swaps++;}}',
            'libcore/io/IoUtils.java': 'package libcore.io; public class IoUtils {public static void closeQuietly(java.io.Closeable value){if(value!=null)try{value.close();}catch(java.io.IOException ignored){}}}',
            'com/android/internal/util/ProcFileReader.java': '''package com.android.internal.util;
import java.io.*;import java.net.ProtocolException;import java.nio.charset.StandardCharsets;import java.util.*;
public class ProcFileReader implements Closeable {
 final InputStream input;final ArrayList<String[]> lines=new ArrayList<>();int line,column;
 public ProcFileReader(InputStream input)throws IOException {this.input=input;BufferedReader reader=new BufferedReader(new InputStreamReader(input,StandardCharsets.UTF_8));
  String text;while((text=reader.readLine())!=null)if(!text.isEmpty())lines.add(text.trim().split("\\\\s+"));}
 public boolean hasMoreData(){return line<lines.size();}
 public String nextString()throws IOException{if(!hasMoreData()||column>=lines.get(line).length)throw new ProtocolException("truncated fixture row");return lines.get(line)[column++];}
 public int nextInt()throws IOException{return Integer.parseInt(nextString());}
 public long nextLong()throws IOException{return Long.parseLong(nextString());}
 public void finishLine(){line++;column=0;}
 public void close()throws IOException{input.close();}
}'''}
        for name, content in stubs.items():
            path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
        candidates = [TOP / 'prebuilts/jdk/jdk11/linux-x86/bin/java', TOP / 'prebuilts/jdk/jdk17/linux-x86/bin/java',
                      Path(shutil.which('java') or '/nonexistent'), Path('/usr/lib/jvm/default-java/bin/java')]
        java = next((str(path) for path in candidates if path.is_file()), None)
        self.assertIsNotNone(java)
        classes = host / 'classes'; classes.mkdir()
        built = run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-source', '8', '-target', '8',
                     '-d', str(classes)] + [str(path) for path in source.rglob('*.java')])
        self.assertEqual(built.returncode, 0, built.stderr)
        for mode in ('legacy', 'modern', 'default'):
            proc = host / mode; (proc / 'net/xt_qtaguid').mkdir(parents=True)
            generated = run([str(host / 'kernel'), str(proc)])
            self.assertEqual(generated.returncode, 0, generated.stderr)
            folder = proc / 'net/xt_qtaguid'
            shutil.copyfile(proc / 'stats-first', folder / 'stats')
            shutil.copyfile(proc / 'iface-fmt', folder / 'iface_stat_fmt')
            (folder / 'iface_stat_all').write_text('wlan0 1 100 1 200 2 20 1 30 1\nrmnet_data0 0 50 5 60 6 999 99 999 99\n')
            flags = [] if mode == 'default' else ['-Dro.kernel.ebpf.supported=' + ('false' if mode == 'legacy' else 'true')]
            result = run([java, '-ea', '-Djava.library.path=' + str(host), *flags, '-cp', str(classes),
                          'com.android.server.net.CumulativeSnapshotFixture', mode, str(proc)])
            self.assertEqual(result.returncode, 0, (mode, result.stderr))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    TOP = parser.parse_args().top.resolve(strict=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
