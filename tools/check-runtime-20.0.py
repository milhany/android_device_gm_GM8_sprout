#!/usr/bin/env python3
"""Run predecessor regressions on an isolated normalized view and final-stack checks."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/tests'))
from host_java import find_java
spec = importlib.util.spec_from_file_location('stack', ROOT/'tools/apply-runtime-stack-20.0.py')
stack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top',type=Path,required=True)
    args=parser.parse_args();top=args.top.resolve()
    java=find_java(top)
    child_env={**os.environ, 'GM8_HOST_JAVA':java}
    print(f'Host test JDK: {java}',flush=True)
    subprocess.run([sys.executable,str(ROOT/'tools/tests/host_java_test.py')],check=True,env=child_env)
    subprocess.run([sys.executable,str(ROOT/'tools/apply-runtime-stack-20.0.py'),'--top',str(top),'--check'],check=True)
    config=json.loads((ROOT/'tools/runtime-stack-20.0.json').read_text())
    with tempfile.TemporaryDirectory(prefix='gm8-runtime-predecessor-tests-') as temporary:
        baseline=Path(temporary)
        # These tests exercise the published predecessor patch installers as well
        # as their backends. Normalize only this copy, never the live source tree.
        keep={'system/core':1,'system/netd':3,'packages/modules/Connectivity':4}
        for item in config['projects']:
            project=baseline/item['path'];project.mkdir(parents=True)
            paths=set().union(*(stack.patch_paths(ROOT/p) for p in item['patches']))
            for path in paths:
                source=top/item['path']/path
                if source.is_file():
                    destination=project/path;destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,destination)
            subprocess.run(['git','init','-q',str(project)],check=True)
            for patch in reversed(item['patches'][keep.get(item['path'],0):]):
                result=stack.run(project,['--reverse',str(ROOT/patch)])
                if result.returncode:raise RuntimeError(result.stderr)
        version=baseline/'build/core/version_defaults.mk';version.parent.mkdir(parents=True)
        version.write_text('PLATFORM_SDK_VERSION := 33\n')
        manager='packages/modules/Connectivity/framework/src/android/net/ConnectivityManager.java'
        destination=baseline/manager;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(top/manager,destination)
        monitor='packages/modules/Connectivity/service/src/com/android/server/connectivity/PermissionMonitor.java'
        destination=baseline/monitor;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(top/monitor,destination)
        kernel='kernel/gm/msm8937/net/netfilter/xt_qtaguid.c'
        destination=baseline/kernel;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(top/kernel,destination)
        tests=[
            ('processgroup_20_0_test.py',['--source',str(baseline/'system/core/libprocessgroup/processgroup.cpp')]),
            ('network_stats_20_0_test.py',['--source',str(baseline/'packages/modules/Connectivity/service-t/jni/com_android_server_net_NetworkStatsService.cpp'),'--kernel',str(baseline/kernel)]),
            ('firewall_20_0_test.py',['--top',str(baseline)]),
            ('network_policy_20_0_test.py',['--top',str(baseline)]),
            ('socket_20_0_test.py',['--top',str(baseline)]),
            ('permissions_20_0_test.py',['--top',str(baseline)]),
        ]
        for name,flags in tests:
            subprocess.run([sys.executable,str(ROOT/'tools/tests'/name),*flags],check=True,env=child_env)
    # Compile the final factory and routing/backend methods, not normalized ones.
    for name in ('snapshots_20_0_test.py','runtime_stack_20_0_test.py','boot_findings_20_0_test.py'):
        subprocess.run([sys.executable,str(ROOT/'tools/tests'/name),'--top',str(top)],check=True,env=child_env)
    subprocess.run([sys.executable,str(ROOT/'tools/tests/tcp_info_19_1_test.py'),'--source',
                    str(top/'packages/modules/NetworkStack'),'--java',java],check=True,env=child_env)
    print('Host source regressions passed. Android build, real networking and hardware remain unvalidated.')


if __name__=='__main__':main()
