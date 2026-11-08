"""Host simulation of config preservation and cleanup; no phone is accessed."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent
script = (root.parent / 'diagnostics/gm8-gps-diagnose.sh').read_text()
mock = r'''#!/usr/bin/env python3
import json,os,pathlib,signal,sys,time,shutil
root=pathlib.Path(os.environ['GM8_MOCK_ROOT'])
name=pathlib.Path(sys.argv[0]).name
state=root/'state.json'
data=json.loads(state.read_text())
with (root/'actions.txt').open('a') as out: out.write(name+' '+repr(sys.argv[1:])+'\n')
fault=os.environ.get('GM8_MOCK_FAULT','')
if name=='id': print('2000' if fault=='nonroot' else '0')
elif name=='getprop':
    key=sys.argv[1]
    if key.startswith('init.svc.'):
        print(data[key[9:]])
    else: print({'ro.build.version.sdk':'29','ro.build.type':'userdebug'}.get(key,'mock'))
elif name in ('start','stop'):
    data[sys.argv[1]]='running' if name=='start' else 'stopped'
    state.write_text(json.dumps(data))
elif name=='ls': print('u:object_r:vendor_configs_file:s0 '+sys.argv[-1])
elif name=='chcon':
    if fault=='label': sys.exit(1)
elif name=='mount':
    source,target=map(pathlib.Path,sys.argv[-2:])
    if fault=='secondmount' and target.name=='izat.conf': sys.exit(1)
    shutil.copyfile(target,str(target)+'.mount-backup')
    shutil.copyfile(source,target)
elif name=='umount':
    target=pathlib.Path(sys.argv[-1]);shutil.copyfile(str(target)+'.mount-backup',target)
    pathlib.Path(str(target)+'.mount-backup').unlink()
elif name=='dumpsys':
    configs=[(root/'vendor/etc'/n).read_text() for n in ('gps.conf','izat.conf')]
    if '-after' not in repr(sys.argv): pass
    print('MOCK location state')
elif name=='sleep':
    time.sleep(0.03) # Let the log producer/filter run before ending the simulated capture.
    # During collection both configs must actually have verbosity 5.
    assert 'DEBUG_LEVEL = 5' in (root/'vendor/etc/gps.conf').read_text()
    assert 'IZAT_DEBUG_LEVEL = 5' in (root/'vendor/etc/izat.conf').read_text()
    if fault=='interrupt': os.kill(os.getppid(),signal.SIGTERM)
elif name=='logcat':
    print('01-01 00:00:00.000 1 1 D LocSvc_xtra2: MOCK GPS EVENT',flush=True)
    print('01-01 00:00:00.001 1 1 D OtherApp: unrelated event',flush=True)
    while True: time.sleep(0.02)
else: raise SystemExit('Unknown mock '+name)
'''


def check(fault=''):
    with tempfile.TemporaryDirectory(prefix='gm8-gps-host-') as tmp:
        tree=Path(tmp)
        (tree/'vendor/etc').mkdir(parents=True)
        (tree/'data/local/tmp').mkdir(parents=True)
        gps='# leave server/config intact\nNTP_SERVER=time.google.com\nDEBUG_LEVEL = 3\nSUPL_VER=0x10000\n'
        izat='IZAT_DEBUG_LEVEL = 2\nNLP_MODE = 1\nPROCESS_NAME=xtra-daemon\nPROCESS_STATE=ENABLED\n'
        if fault=='duplicate': gps+='DEBUG_LEVEL=2\n'
        for name,text in (('gps.conf',gps),('izat.conf',izat)):
            (tree/'vendor/etc'/name).write_text(text)
        for rel in ('vendor/bin/xtra-daemon','vendor/lib64/libizat_core.so',
                    'vendor/lib64/libloc_api_v02.so','vendor/lib64/libgnss.so'):
            f=tree/rel;f.parent.mkdir(exist_ok=True,parents=True);f.write_text('MOCK')
        state={'gnss_service':'running','loc_launcher':'running'}
        if fault=='stopped': state['gnss_service']='stopped'
        (tree/'state.json').write_text(json.dumps(state))
        commands=tree/'commands';commands.mkdir()
        dispatcher=commands/'dispatcher';dispatcher.write_text(mock);dispatcher.chmod(0o755)
        for name in ('id','getprop','start','stop','ls','chcon','mount','umount','dumpsys','sleep','logcat'):
            (commands/name).symlink_to(dispatcher)
        # Adapt only absolute Android filesystem locations; execute the actual shell logic.
        adapted=script.replace('/vendor/',str(tree/'vendor')+'/').replace('/data/local/tmp',str(tree/'data/local/tmp'))
        program=tree/'run.sh';program.write_text(adapted)
        env={**os.environ,'GM8_MOCK_ROOT':tmp,'GM8_MOCK_FAULT':fault,
             'PATH':str(commands)+':'+os.environ['PATH']}
        result=subprocess.run(['sh',str(program),'30'],env=env,text=True,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15)
        assert (result.returncode==0)==(fault==''), result.stdout
        assert (tree/'vendor/etc/gps.conf').read_text()==gps, result.stdout
        assert (tree/'vendor/etc/izat.conf').read_text()==izat, result.stdout
        assert json.loads((tree/'state.json').read_text())==state, result.stdout
        assert not (tree/'data/local/tmp/gm8-gps-diagnostic.lock').exists()
        if fault=='':
            logs=list((tree/'data/local/tmp/gm8-gps-diagnostic').rglob('gps-log.txt'))
            assert len(logs)==1
            text=logs[0].read_text()
            assert 'MOCK GPS EVENT' in text, result.stdout
            assert 'unrelated event' not in text
        print('PASS:',fault or 'normal capture','— original configs and service state preserved')


for fault in ('','nonroot','stopped','duplicate','label','secondmount','interrupt'):
    check(fault)
