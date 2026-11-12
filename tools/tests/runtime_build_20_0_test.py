#!/usr/bin/env python3
"""Exercise the real full-build shell entry with command fixtures and output sentinels."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=(ROOT/'tools/build-runtime-20.0.sh').read_text()
for case in ('success','build-failure','host-failure','source-failure','symlink-output'):
    with tempfile.TemporaryDirectory(prefix='gm8-runtime-build-test-') as tmp:
        parent=Path(tmp);top=parent/'lineage-20.0';tools=top/'device/gm/GM8_sprout/tools'
        (tools/'tests').mkdir(parents=True)
        entry=tools/'build-runtime-20.0.sh';entry.write_text(SCRIPT)
        trace=parent/'trace';bin_dir=parent/'bin';bin_dir.mkdir()
        repo=bin_dir/'repo';repo.write_text('#!/bin/sh\nexit 0\n');repo.chmod(0o755)
        leaf='''import os,sys
from pathlib import Path
name=Path(__file__).name
with Path(os.environ['GM8_TRACE']).open('a') as f:f.write(name+'\\n')
case=os.environ['GM8_CASE']
if case=='source-failure' and name=='apply-runtime-stack-20.0.py':raise SystemExit(21)
if case=='host-failure' and name=='check-runtime-20.0.py':raise SystemExit(22)
'''
        for name in ('apply-runtime-stack-20.0.py','preflight-20.0.py','check-runtime-20.0.py',
                     'fixup-legacy-protobuf.py','inspect-target-files-20.0.py',
                     'tests/kernel_host_link_test.py','tests/ft8006_gesture_test.py',
                     'tests/qsee_wait_test.py','tests/power_policy_test.py'):
            (tools/name).write_text(leaf)
        (top/'build').mkdir()
        (top/'build/envsetup.sh').write_text('''lunch(){ echo "lunch $*" >> "$GM8_TRACE"; }
m(){ echo "m $*" >> "$GM8_TRACE"; if [[ "$GM8_CASE" == build-failure ]]; then return 17; fi; }
''')
        product=top/'out/target/product/GM8_sprout';(product/'obj').mkdir(parents=True)
        obj=product/'obj/KERNEL_OBJ';outside=parent/'outside';outside.mkdir()
        if case=='symlink-output':obj.symlink_to(outside,target_is_directory=True)
        else:obj.mkdir()
        (obj/'keep-until-build').write_text('kernel')
        for name in ('kernel','boot.img','system.img'):(product/name).write_text('sentinel')
        env={**os.environ,'PATH':str(bin_dir)+os.pathsep+os.environ['PATH'],
             'GM8_TRACE':str(trace),'GM8_CASE':case,'OUT_DIR':'out'}
        result=subprocess.run(['bash',str(entry)],env=env,text=True,capture_output=True)
        expected={'success':0,'build-failure':17,'host-failure':22,'source-failure':21,'symlink-output':1}[case]
        assert result.returncode==expected,(case,result.returncode,result.stdout,result.stderr)
        calls=trace.read_text().splitlines()
        assert (product/'system.img').read_text()=='sentinel'
        if case in ('success','build-failure'):
            assert not obj.exists() and not (product/'kernel').exists() and not (product/'boot.img').exists()
            assert [line for line in calls if line.startswith('m ')]==['m target-files-package otatools -j32']
        else:
            assert (obj/'keep-until-build').read_text()=='kernel'
            assert (product/'kernel').exists() and (product/'boot.img').exists()
            assert not any(line.startswith('m ') for line in calls)
        assert ('inspect-target-files-20.0.py' in calls)==(case=='success')
        assert ('Full build completed.' in result.stdout)==(case=='success')
print('PASS: full build target, failure propagation, narrow kernel cleanup and symlink refusal')
