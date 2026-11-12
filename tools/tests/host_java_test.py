#!/usr/bin/env python3
"""Check checkout JDK selection and propagation into JDK-free source fixtures."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from host_java import find_java


class HostJavaTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='gm8-host-java-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.environment=patch.dict(os.environ,{},clear=True)
        self.environment.start();self.addCleanup(self.environment.stop)

    def java(self,relative,code=0,executable=True):
        path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('#!/bin/sh\nexit '+str(code)+'\n')
        path.chmod(0o755 if executable else 0o644)
        return path

    def test_checkout_jdk_with_no_java_on_path(self):
        os.environ['PATH']=''
        java=self.java('checkout/prebuilts/jdk/jdk11/linux-x86/bin/java')
        self.assertEqual(find_java(self.root/'checkout'),str(java))

    def test_noncompiler_or_nonexecutable_candidate_falls_back(self):
        self.java('checkout/prebuilts/jdk/jdk11/linux-x86/bin/java',code=1)
        java=self.java('checkout/prebuilts/jdk/jdk17/linux-x86/bin/java')
        self.assertEqual(find_java(self.root/'checkout'),str(java))
        (self.root/'checkout/prebuilts/jdk/jdk11/linux-x86/bin/java').chmod(0o644)
        self.assertEqual(find_java(self.root/'checkout'),str(java))

    def test_real_checkout_selection_reaches_jdk_free_child(self):
        os.environ['PATH']=''
        java=self.java('checkout/prebuilts/jdk/jdk11/linux-x86/bin/java')
        chosen=find_java(self.root/'checkout')
        fixture=self.root/'source fixture';fixture.mkdir()
        env={**os.environ,'GM8_HOST_JAVA':chosen}
        command='import sys;from host_java import find_java;print(find_java(sys.argv[1]))'
        env['PYTHONPATH']=str(Path(__file__).parent)
        result=subprocess.run([sys.executable,'-c',command,str(fixture)],env=env,
                              text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),str(java))
        self.assertFalse((fixture/'prebuilts').exists())

    def test_explicit_bad_override_does_not_silently_fall_back(self):
        self.java('checkout/prebuilts/jdk/jdk11/linux-x86/bin/java')
        os.environ['GM8_HOST_JAVA']=str(self.root/'missing-java')
        with self.assertRaisesRegex(RuntimeError,'missing or not executable'):
            find_java(self.root/'checkout')

    def test_explicit_compiler_failure_is_reported(self):
        java=self.java('jdk with spaces/bin/java',code=3)
        with self.assertRaisesRegex(RuntimeError,'compiler probe failed \\(3\\)'):
            find_java(self.root,java)

    def test_java_home_and_path_are_fallbacks(self):
        java=self.java('installed-jdk/bin/java')
        os.environ['JAVA_HOME']=str(java.parent.parent)
        self.assertEqual(find_java(self.root/'checkout'),str(java))
        del os.environ['JAVA_HOME']
        os.environ['PATH']=str(java.parent)
        self.assertEqual(find_java(self.root/'checkout'),str(java))


if __name__=='__main__':unittest.main(verbosity=2)
