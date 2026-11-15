#!/usr/bin/env python3
"""Add the source recovery cgroup policy to a known unsigned GM8 boot dump.

For fastboot boot testing only. Preserves kernel, all existing CPIO records,
boot load addresses, cmdline, trust stores and ADB settings. Never flashes.
Refuses images with nonzero trailing signatures/footers or unexpected layouts.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import struct

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gm8_firstboot',ROOT/'tools/firstboot-20.0.py')
firstboot=importlib.util.module_from_spec(spec);spec.loader.exec_module(firstboot)
LIMIT=64*1024*1024


def align(value):
    return (value+2047)&~2047


def legacy_id(kernel,ramdisk):
    return hashlib.sha1(kernel+struct.pack('<I',len(kernel))+
                        ramdisk+struct.pack('<I',len(ramdisk))+b'\0'*8).digest()


def record(name,data,mode,ino):
    raw=name.encode()+b'\0'
    fields=[ino,mode,0,0,1,0,len(data),0,0,0,0,len(raw),0]
    out=b'070701'+''.join(f'{v:08x}' for v in fields).encode()+raw
    out+=b'\0'*(-len(out)%4)
    out+=data
    return out+b'\0'*(-len(out)%4)


def repair(data,expected_sha256):
    if hashlib.sha256(data).hexdigest()!=expected_sha256:
        raise ValueError('Input SHA256 mismatch')
    if len(data)>LIMIT:raise ValueError('Boot dump exceeds GM8 partition')
    firstboot.boot_layout(data[:48])
    ks=struct.unpack_from('<I',data,8)[0]
    rs=struct.unpack_from('<I',data,16)[0]
    if not ks or not rs:raise ValueError('Empty kernel/ramdisk')
    ramstart=2048+align(ks);end=ramstart+align(rs)
    if end>len(data) or any(data[end:]):
        raise ValueError('Truncated image or signed/nonzero tail; rebuild from source')
    kernel=data[2048:2048+ks];oldram=data[ramstart:ramstart+rs]
    if data[576:596]!=legacy_id(kernel,oldram) or any(data[596:608]):
        raise ValueError('Unexpected boot ID; refusing unknown image format')
    entries=firstboot.ramdisk_files(oldram)
    props=firstboot.crypto.props(entries.get('prop.default',(0,b''))[1].decode())
    if props.get('ro.vendor.gm8.legacy_cgroups')!='true':
        raise ValueError('Image does not select GM8 cgroup-v1')
    if 'vendor' not in entries or not stat.S_ISDIR(entries['vendor'][0]):
        raise ValueError('Expected real vendor directory in recovery ramdisk')
    if not oldram.startswith(b'\x1f\x8b'):raise ValueError('Expected gzip ramdisk')
    raw=gzip.decompress(oldram);offset=0;max_ino=0
    # The validated parser checked lengths, duplicates, checksums and trailer.
    while True:
        h=raw[offset:offset+110]
        fields=[int(h[6+i*8:14+i*8],16) for i in range(13)]
        name=raw[offset+110:offset+110+fields[11]-1].decode()
        if name=='TRAILER!!!':break
        max_ino=max(max_ino,fields[0])
        offset=((offset+110+fields[11]+3)&~3)+fields[6]
        offset=(offset+3)&~3
    additions=[]
    if 'vendor/etc' not in entries:
        additions.append(('vendor/etc',b'',stat.S_IFDIR|0o755))
    elif not stat.S_ISDIR(entries['vendor/etc'][0]):
        raise ValueError('vendor/etc is not a directory')
    for source,target in (('cgroups-gm8.json','cgroups.json'),
                          ('task-profiles-gm8.json','task_profiles.json')):
        name='vendor/etc/'+target
        if name in entries:raise ValueError('Policy already exists: '+name)
        additions.append((name,(ROOT/'configs'/source).read_bytes(),stat.S_IFREG|0o644))
    changed=raw[:offset]
    for index,(name,body,mode) in enumerate(additions,1):
        changed+=record(name,body,mode,max_ino+index)
    changed+=record('TRAILER!!!',b'',0,0)
    newram=gzip.compress(changed,mtime=0)
    checked=firstboot.ramdisk_files(newram)
    firstboot.verify_recovery_cgroups(checked)
    for name,value in entries.items():
        if checked[name]!=value:raise ValueError('Existing ramdisk entry changed: '+name)
    header=bytearray(data[:2048])
    struct.pack_into('<I',header,16,len(newram))
    header[576:596]=legacy_id(kernel,newram)
    result=bytes(header)+data[2048:ramstart]+newram+b'\0'*(-len(newram)%2048)
    if len(result)>LIMIT:raise ValueError('Repaired image exceeds GM8 partition')
    return result,{'input_sha256':expected_sha256,
                   'output_sha256':hashlib.sha256(result).hexdigest(),
                   'kernel_sha256':hashlib.sha256(kernel).hexdigest(),
                   'added':[item[0] for item in additions],
                   'preserved_ramdisk_entries':len(entries),'output_bytes':len(result)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--input-sha256',required=True)
    args=p.parse_args()
    result,report=repair(args.input.read_bytes(),args.input_sha256)
    with args.output.open('xb') as f:f.write(result)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
