#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil,subprocess
import argparse,tempfile
parser=argparse.ArgumentParser(description='Test real GM8 protobuf fixups with readelf and raw vendor ELF inputs.')
parser.add_argument('--top',type=Path,default=Path(__file__).resolve().parents[5])
parser.add_argument('--stock-vendor',type=Path)
parser.add_argument('--patchelf')
args=parser.parse_args()
r=Path(__file__).resolve().parents[2]
source_top=args.top.resolve()
stock=args.stock_vendor or source_top/'vendor/gm/GM8_sprout'
patchelf=args.patchelf or str(source_top/'prebuilts/extract-tools/linux-x86/bin/patchelf-0_9')
temp=tempfile.TemporaryDirectory(prefix='gm8-protobuf-regression-')
top=Path(temp.name)
(top/'build/core').mkdir(parents=True);(top/'build/core/version_defaults.mk').write_text('PLATFORM_SDK_VERSION := 32\n')
manifest=json.loads((r/'configs/legacy-protobuf.json').read_text())
def stock_input(path):
    result=subprocess.run(['git','show',manifest['vendor_ref']+':proprietary/'+path],cwd=stock,capture_output=True)
    data=result.stdout if result.returncode==0 else (stock/'proprietary'/path).read_bytes()
    expected=next(e['sha256'] for e in manifest['files'] if e['path']==path)
    assert hashlib.sha256(data).hexdigest()==expected,'Missing reviewed original vendor ELF: '+path
    return data
for arch in ('arm','arm64'):
 for v in ('full','lite'):
  rel=f'prebuilts/vndk/v29/arm64/arch-{arch}-armv8-a/shared/vndk-core/libprotobuf-cpp-{v}.so'
  dest=top/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_top/rel,dest)
entries=json.loads((r/'configs/legacy-protobuf.json').read_text())['files']
blobs=[]
for e in entries:
 p=top/'vendor/gm/GM8_sprout/proprietary'/e['path'];p.parent.mkdir(parents=True,exist_ok=True)
 p.write_bytes(stock_input(e['path']));blobs.append(p)
cmd=['python3',str(r/'tools/fixup-legacy-protobuf.py'),'--top',str(top),'--patchelf',patchelf]
def run(expected,*args):
 p=subprocess.run(cmd+list(args),capture_output=True,text=True)
 print(p.stdout.strip() or p.stderr.strip())
 assert p.returncode==expected,(p.stdout,p.stderr)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(p):
 s=subprocess.check_output(['readelf','--wide','--dyn-syms',str(p)],text=True)
 out=[]
 for line in s.splitlines():
  a=line.split()
  if len(a)>=8 and a[0].endswith(':') and a[0][:-1].isdigit():
   out.append(tuple(a[1:6]+[a[6]=='UND']+a[7:]))
 return sorted(out,key=repr)
original=[sha(p) for p in blobs];before_symbols=[symbols(p) for p in blobs]
# All validation completes before any source file is replaced.
last=blobs[-1];raw=last.read_bytes();last.write_bytes(raw+b'local-edit')
run(1)
assert [sha(p) for p in blobs[:-1]]==original[:-1]
assert last.read_bytes()==raw+b'local-edit'
last.write_bytes(raw)
run(1,'--check')
run(0)
after=[sha(p) for p in blobs];assert all(a!=b for a,b in zip(original,after))
run(0,'--check','--record',str(top/'record.json'))
run(0);assert [sha(p) for p in blobs]==after
for p,e,before in zip(blobs,entries,before_symbols):
 needed=subprocess.check_output([patchelf,'--print-needed',str(p)],text=True).splitlines()
 assert f"libprotobuf-cpp-{e['variant']}-v29.so" in needed
 assert f"libprotobuf-cpp-{e['variant']}.so" not in needed
 assert symbols(p)==before,p
for arch,lib in [('arm','lib'),('arm64','lib64')]:
 for v in ['full','lite']:
  src=top/f'prebuilts/vndk/v29/arm64/arch-{arch}-armv8-a/shared/vndk-core/libprotobuf-cpp-{v}.so'
  dest=r/f'generated/legacy-protobuf/{lib}/libprotobuf-cpp-{v}-v29.so'
  assert subprocess.check_output([patchelf,'--print-soname',str(dest)],text=True).strip()==dest.name
  assert symbols(src)==symbols(dest),dest
# The extraction hook handles raw and already-fixed single blobs too.
p=top/'extract.so';p.write_bytes(stock_input(entries[0]['path']))
for _ in range(2):
 subprocess.run(['python3',str(r/'tools/fixup-legacy-protobuf.py'),'--blob',str(p),'--relative-path',entries[0]['path'],'--patchelf',patchelf],check=True)
print('PASS: real patchelf, all four ARM/ARM64 snapshots and seven stock blobs')
print('PASS: distinct SONAMEs/dependencies; dynamic symbols preserved; check/repeat/extraction modes; source drift refused without partial writes')
