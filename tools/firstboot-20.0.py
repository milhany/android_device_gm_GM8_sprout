#!/usr/bin/env python3
"""Sign an existing flattened SDK33 userdebug target-files with existing keys.

Produces and verifies a clean-install hardware-test OTA and matching boot image.
Never builds Android, generates keys, flashes, selects a slot or formats data.
"""
import argparse
import base64
from collections import Counter
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
# Share only the existing OpenSSL/APK/whole-OTA cryptographic utilities.
# SDK32 inventory, key generation and signing entry points are never called.
spec=importlib.util.spec_from_file_location('gm8_signing_crypto',ROOT/'tools/release-19.1.py')
crypto=importlib.util.module_from_spec(spec);spec.loader.exec_module(crypto)
sys.path.insert(0,str(ROOT/'tools/tests'))
from host_java import find_java

PARTITIONS={'boot','system','vendor'}
LIMIT=16*1024*1024


def boot_layout(header):
    if len(header)<48 or header[:8]!=b'ANDROID!':raise ValueError('Invalid Android boot header')
    values=struct.unpack_from('<10I',header,8)
    if values[4]!=0 or values[7]!=2048 or values[8]!=0:
        raise ValueError('Expected GM8 v0/2048 boot with no second stage')
    return dict(zip(('kernel_address','ramdisk_address','second_address','tags_address',
                     'page_size','header_version'),[values[i] for i in (1,3,5,6,7,8)]))


def checked_zip(z):
    names=z.namelist()
    if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP entries')
    return names


def metadata(z,signed=False):
    names=checked_zip(z)
    build=crypto.props(crypto.text(z,'SYSTEM/build.prop'))
    devices={build.get(k) for k in ('ro.build.product','ro.product.system.device','ro.product.device') if build.get(k)}
    if (build.get('ro.build.version.sdk')!='33' or build.get('ro.build.type')!='userdebug'
            or not devices or not devices<={'GM8_sprout','GM8_d_sprout'}):
        raise ValueError('Expected GM8 SDK33 userdebug target-files')
    if signed and set(build.get('ro.build.tags','').split(','))!={'release-keys'}:
        raise ValueError('Signed candidate must have release-keys tags')
    misc=crypto.props(crypto.text(z,'META/misc_info.txt'))
    if misc.get('ab_update')!='true':raise ValueError('Expected A/B target-files')
    if misc.get('avb_enable')=='true' or misc.get('verity')=='true':
        raise ValueError('AVB/verity enabled; an additional partition signing plan is required')
    if any(misc.get(k)=='true' for k in ('virtual_ab','virtual_ab_compression',
                                        'use_dynamic_partitions','dynamic_partition_retrofit')):
        raise ValueError('Virtual/dynamic A/B is outside this GM8 legacy layout')
    parts=crypto.text(z,'META/ab_partitions.txt').split()
    if len(parts)!=3 or set(parts)!=PARTITIONS:
        raise ValueError('Only boot/system/vendor may be present in the A/B payload')
    if any(n.endswith(('.apex','.capex')) for n in names):
        raise ValueError('This first-boot signer supports flattened APEX only')
    flat=sorted(n for n in names if '/apex/' in n and n.endswith('/apex_manifest.pb'))
    if not flat:raise ValueError('No flattened APEX manifests found')
    for name in ('VENDOR/etc/fstab.qcom','BOOT/RAMDISK/system/etc/recovery.fstab'):
        rows=[line.split('#',1)[0].split() for line in crypto.text(z,name).splitlines()]
        rows=[r for r in rows if len(r)>=5 and r[1]=='/data']
        if len(rows)!=1 or rows[0][2]!='f2fs':raise ValueError('Expected explicit F2FS /data: '+name)
        flags=[flag.split('=',1)[0] for flag in rows[0][4].split(',')]
        if set(flags)&{'encryptable','forceencrypt','forcefdeorfbe','fileencryption','metadata_encryption'}:
            raise ValueError('Unsupported encrypted userdata policy: '+name)
    for name in ('IMAGES/boot.img','IMAGES/system.img','IMAGES/vendor.img','BOOT/kernel','META/otakeys.txt'):
        if name not in names:raise ValueError('Missing packaged component: '+name)
    default=crypto.props(crypto.text(z,'BOOT/RAMDISK/prop.default'))
    if default.get('ro.debuggable')!='1':raise ValueError('Userdebug ramdisk debugging must remain enabled')
    if z.getinfo('IMAGES/boot.img').file_size>64*1024*1024:raise ValueError('Boot exceeds 64 MiB')
    return build,misc,flat


def existing_key_dir(path,top):
    path=Path(path).expanduser()
    if path.is_symlink():raise ValueError('Key directory must not be a symlink')
    path=path.resolve(strict=True)
    if path==top or top in path.parents or not path.is_dir():raise ValueError('Keys must already exist outside the checkout')
    if path.stat().st_uid!=os.getuid() or stat.S_IMODE(path.stat().st_mode)&0o077:
        raise ValueError('Existing key directory must be owned by this user with mode 0700')
    return path


def require_pair(base):
    for suffix in ('.x509.pem','.pk8'):
        path=Path(base+suffix)
        if path.is_symlink() or not path.is_file():raise ValueError('Missing existing key pair (no keys generated): '+base)
        if suffix=='.pk8' and (path.stat().st_uid!=os.getuid() or stat.S_IMODE(path.stat().st_mode)&0o077):
            raise ValueError('Private key must be owned by this user without group/other access: '+str(path))


def inventory(top,target,keys):
    with zipfile.ZipFile(target) as z:
        build,misc,flat=metadata(z)
        apkcerts=crypto.records(crypto.text(z,'META/apkcerts.txt'))
        apexcerts=crypto.records(crypto.text(z,'META/apexkeys.txt'))
        dev=misc.get('default_system_dev_certificate','build/make/target/product/security/testkey')
        devdir=Path(dev).parent
        known={}
        for name,role in (('testkey','releasekey'),('devkey','releasekey'),
                          ('platform','platform'),('shared','shared'),('media','media'),
                          ('networkstack','networkstack'),('sdk_sandbox','sdk_sandbox'),
                          ('bluetooth','bluetooth')):
            cert=top/devdir/(name+'.x509.pem')
            if cert.is_file():known.setdefault(hashlib.sha256(crypto.cert_der(cert)).hexdigest(),str(keys/role))
        certs={}
        def certificate(name):
            if name=='PRESIGNED':return None
            if name=='EXTERNAL':raise ValueError('EXTERNAL APK requires explicit signing review')
            if name not in certs:
                old=crypto.source_certificate(top,name)
                old_hash=hashlib.sha256(crypto.cert_der(old)).hexdigest()
                base=known.get(old_hash,str(keys/'certs'/old_hash))
                require_pair(base)
                certs[name]={'key':base,'old_sha256':old_hash,
                             'new_sha256':hashlib.sha256(crypto.cert_der(base+'.x509.pem')).hexdigest()}
            return certs[name]['key']
        ota=certificate(dev+'.x509.pem')
        for old in crypto.text(z,'META/otakeys.txt').split():
            if certificate(old)!=ota:raise ValueError('More than one OTA signing identity requires separate review')
        apks=[]
        for name in z.namelist():
            if not name.endswith(('.apk','.apk.gz')):continue
            if name.split('/')[0] not in {'SYSTEM','SYSTEM_EXT','PRODUCT','VENDOR','ODM'}:
                raise ValueError('Unexpected APK outside installed partitions: '+name)
            basename=Path(name).name.removesuffix('.gz')
            if basename not in apkcerts:raise ValueError('Missing APK certificate metadata: '+basename)
            key=certificate(apkcerts[basename]['certificate'])
            apks.append({'entry':name,'key':key,
                         'presigned_sha256':hashlib.sha256(z.read(name)).hexdigest() if key is None else None})
        if not apks:raise ValueError('No installed APKs in target-files')
        # SDK33 ReplaceOtaKeys keeps recovery-only extras separate from normal
        # OTA extras. They are public trust anchors, not package signing keys.
        # Remap an already-known APK/default signing identity; otherwise keep
        # the explicitly declared public certificate without needing its PK8.
        def trust_certificate(old):
            source=old+'.x509.pem'
            original=crypto.source_certificate(top,source)
            original_hash=hashlib.sha256(crypto.cert_der(original)).hexdigest()
            if source in certs or original_hash in {c['old_sha256'] for c in certs.values()}:
                base=certificate(source)
                return {'source':old,'certificate':base+'.x509.pem',
                        'sha256':certs[source]['new_sha256'],'action':'remapped'}
            return {'source':old,'certificate':str(original),
                    'sha256':original_hash,'action':'preserved_public_only'}
        primary={'source':dev,'certificate':ota+'.x509.pem',
                 'sha256':hashlib.sha256(crypto.cert_der(ota+'.x509.pem')).hexdigest(),
                 'action':'primary_signer'}
        trust_metadata={key:misc.get(key,'').split() for key in ('extra_ota_keys','extra_recovery_keys')}
        trust={'system':[primary]+[trust_certificate(name) for name in trust_metadata['extra_ota_keys']],
               'recovery':[primary]+[trust_certificate(name) for name in trust_metadata['extra_recovery_keys']]}
        if any(len(entries)>64 for entries in trust.values()):raise ValueError('Too many planned OTA trust certificates')
        # Flattened APEXes have no signed containers/payload images. Stale build
        # metadata for nonexistent containers must not request/generate APEX keys.
        # Every actual flattened APK remains in the verified APK inventory above.
        for name in apexcerts:
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.apex',name):raise ValueError('Unexpected APEX metadata name')
        with z.open('IMAGES/boot.img') as image:layout=boot_layout(image.read(48))
        return {'schema':2,'sdk':33,'variant':'userdebug','top':str(top),'target':str(target),
                'target_bytes':target.stat().st_size,'target_sha256':crypto.digest(target),
                'key_dir':str(keys),'ota_key':ota,'certificates':certs,'apks':apks,
                'unused_apex_metadata':sorted(apexcerts),'flattened_manifests':flat,
                'original_build':build,'original_kernel_sha256':hashlib.sha256(z.read('BOOT/kernel')).hexdigest(),
                'boot_layout':layout,'trust_stores':trust,'trust_metadata':trust_metadata,
                'requires_clean_install':True,'hardware_tested':False}


def trust_store(data,wanted):
    expected=[wanted] if isinstance(wanted,bytes) else wanted
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        entries=z.infolist()
        if not expected or len(entries)!=len(expected) or len(entries)>64:
            raise ValueError('OTA trust-store certificate count differs from the explicit plan')
        actual=[]
        for entry in entries:
            if entry.is_dir() or entry.file_size>16384:
                raise ValueError('Invalid OTA trust-store entry')
            # Read each ZipInfo independently, including planned duplicate
            # filenames caused by two source aliases mapping to one key.
            value=z.read(entry)
            if value.count(b'-----BEGIN CERTIFICATE-----')!=1:
                raise ValueError('Expected one PEM certificate per OTA trust-store entry')
            actual.append(crypto.run(['openssl','x509','-outform','DER'],value))
        if Counter(actual)!=Counter(expected):
            raise ValueError('OTA trust-store certificates differ from the explicit plan')


def trusted_certificates(plan,scope):
    result=[]
    for item in plan['trust_stores'][scope]:
        data=crypto.cert_der(item['certificate'])
        if hashlib.sha256(data).hexdigest()!=item['sha256']:
            raise ValueError('OTA trust certificate changed since planning: '+item['certificate'])
        result.append(data)
    return result


def pinned_certificate(plan,base):
    hashes={c['new_sha256'] for c in plan['certificates'].values() if c['key']==base}
    data=crypto.cert_der(base+'.x509.pem')
    if hashes!={hashlib.sha256(data).hexdigest()}:
        raise ValueError('Signing certificate changed since planning: '+base)
    return data


def ramdisk_files(data):
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:data=gz.read(128*1024*1024+1)
    if len(data)>128*1024*1024:raise ValueError('Ramdisk exceeds verification bound')
    result={};offset=0
    for _ in range(100000):
        header=data[offset:offset+110]
        if len(header)!=110 or header[:6] not in (b'070701',b'070702'):
            raise ValueError('Expected gzip/raw newc ramdisk for this GM8 boot layout')
        fields=[int(header[6+i*8:14+i*8],16) for i in range(13)]
        size,namesize=fields[6],fields[11]
        if not 1<=namesize<=4096:raise ValueError('Invalid cpio name size')
        name=data[offset+110:offset+110+namesize]
        if len(name)!=namesize or name[-1:]!=b'\0':raise ValueError('Truncated cpio name')
        name=name[:-1].decode()
        start=(offset+110+namesize+3)&~3;end=start+size
        if end>len(data):raise ValueError('Truncated cpio body')
        if header[:6]==b'070702' and sum(data[start:end])&0xffffffff!=fields[12]:
            raise ValueError('Invalid cpio checksum')
        if name=='TRAILER!!!':
            if size or any(data[(end+3)&~3:]):raise ValueError('Unexpected data after cpio trailer')
            return result
        if name in result:raise ValueError('Duplicate ramdisk entry')
        result[name]=(fields[1],data[start:end]);offset=(end+3)&~3
    raise ValueError('Missing cpio trailer')


def verify_boot(data,kernel_hash,wanted_cert):
    if len(data)>64*1024*1024 or data[:8]!=b'ANDROID!' or len(data)<1632:
        raise ValueError('Invalid/oversized GM8 boot image')
    ks,rs,page,version=struct.unpack_from('<I',data,8)[0],struct.unpack_from('<I',data,16)[0],struct.unpack_from('<I',data,36)[0],struct.unpack_from('<I',data,40)[0]
    if page!=2048 or version!=0 or not ks or not rs:raise ValueError('Unexpected GM8 boot header/layout')
    ramstart=(page+ks+page-1)&~(page-1)
    if ramstart+rs>len(data):raise ValueError('Boot ramdisk exceeds image bounds')
    if hashlib.sha256(data[page:page+ks]).hexdigest()!=kernel_hash:
        raise ValueError('Kernel changed or boot image does not match signed target-files')
    entries=ramdisk_files(data[ramstart:ramstart+rs])
    stores=[n for n in entries if n.endswith('/otacerts.zip')]
    if not stores:raise ValueError('No OTA trust store inside actual boot ramdisk')
    for name in stores:
        mode,value=entries[name]
        if not stat.S_ISREG(mode):raise ValueError('Ramdisk OTA trust store is not a regular file')
        trust_store(value,wanted_cert)
    if 'prop.default' not in entries or crypto.props(entries['prop.default'][1].decode()).get('ro.debuggable')!='1':
        raise ValueError('Actual boot ramdisk lost userdebug support')
    return stores


def verify_signed(plan,signed,host):
    pinned_certificate(plan,plan['ota_key'])
    trust={scope:trusted_certificates(plan,scope) for scope in ('system','recovery')}
    expected={c['key']:c['new_sha256'] for c in plan['certificates'].values()}
    with zipfile.ZipFile(signed) as z:
        build,misc,flat=metadata(z,True)
        if {key:misc.get(key,'').split() for key in plan['trust_metadata']}!=plan['trust_metadata']:
            raise ValueError('Declared OTA trust scope changed during signing')
        if flat!=plan['flattened_manifests']:raise ValueError('Flattened APEX inventory changed')
        current={n for n in z.namelist() if n.endswith(('.apk','.apk.gz'))}
        if current!={a['entry'] for a in plan['apks']}:raise ValueError('Installed APK inventory changed')
        with tempfile.TemporaryDirectory(prefix='gm8-apk-check-') as temp:
            for index,apk in enumerate(plan['apks']):
                data=z.read(apk['entry'])
                if apk['key'] is None:
                    if hashlib.sha256(data).hexdigest()!=apk['presigned_sha256']:raise ValueError('PRESIGNED APK changed: '+apk['entry'])
                else:
                    file=Path(temp)/f'{index}.apk';file.write_bytes(gzip.decompress(data) if apk['entry'].endswith('.gz') else data)
                    crypto.apk_verify(file,expected[apk['key']],host)
        stores=[n for n in z.namelist() if n.endswith('/otacerts.zip')]
        if not stores:raise ValueError('Missing signed OTA trust stores')
        for name in stores:
            scope='recovery' if name.startswith(('BOOT/','RECOVERY/','VENDOR_BOOT/')) else 'system'
            trust_store(z.read(name),trust[scope])
        if hashlib.sha256(z.read('BOOT/kernel')).hexdigest()!=plan['original_kernel_sha256']:
            raise ValueError('Signing must preserve the compiled kernel')
        boot=z.read('IMAGES/boot.img')
        if boot_layout(boot[:48])!=plan['boot_layout']:raise ValueError('Signing changed the boot load layout')
        actual_stores=verify_boot(boot,plan['original_kernel_sha256'],trust['recovery'])
        return {'apks_checked':len(plan['apks']),'flattened_apexes':len(flat),
                'target_trust_stores':stores,'actual_boot_trust_stores':actual_stores,
                'trust_stores':plan['trust_stores'],
                'signed_build':build,'boot_bytes':len(boot),'boot_sha256':hashlib.sha256(boot).hexdigest()}


def proto_fields(data):
    offset=0
    def varint():
        nonlocal offset
        value=0
        for count in range(10):
            if offset>=len(data):raise ValueError('Truncated protobuf varint')
            byte=data[offset];offset+=1;value|=(byte&127)<<(count*7)
            if not byte&128:return value
        raise ValueError('Oversized protobuf varint')
    while offset<len(data):
        key=varint();field,wire=key>>3,key&7
        if field==0:raise ValueError('Invalid protobuf field')
        if wire==0:value=varint()
        elif wire in (1,2,5):
            size=varint() if wire==2 else 8 if wire==1 else 4
            if size>len(data)-offset:raise ValueError('Truncated protobuf field')
            value=data[offset:offset+size];offset+=size
        else:raise ValueError('Unsupported protobuf wire type')
        yield field,wire,value


def payload_manifest(path):
    with Path(path).open('rb') as stream:
        header=stream.read(24)
        if len(header)!=24:raise ValueError('Truncated payload header')
        magic,version,length,siglen=struct.unpack('>4sQQI',header)
        if magic!=b'CrAU' or version!=2 or not 0<length<=LIMIT or not siglen:
            raise ValueError('Expected signed v2 A/B payload')
        data=stream.read(length)
        if len(data)!=length:raise ValueError('Truncated payload manifest')
    result={}
    for field,wire,value in proto_fields(data):
        if field==12 and (wire!=0 or value!=0):raise ValueError('Only a full payload (minor version 0) is allowed')
        if field==15 and (wire!=2 or value):raise ValueError('Dynamic partition updates are not allowed')
        if field!=13:continue
        if wire!=2:raise ValueError('Invalid partition protobuf')
        name=None;new=None
        for f,w,v in proto_fields(value):
            if f==1:
                if w!=2 or name is not None:raise ValueError('Invalid partition name field')
                name=v.decode()
            if f==6:raise ValueError('Incremental old partition data is not allowed')
            if f==7:
                if w!=2 or new is not None:raise ValueError('Invalid new partition info')
                new={a:c for a,b,c in proto_fields(v) if a in (1,2) and b==(0 if a==1 else 2)}
        if name not in PARTITIONS or name in result or new is None:
            raise ValueError('Unexpected/duplicate/missing payload partition: '+str(name))
        if not isinstance(new.get(1),int) or new[1]<=0 or not isinstance(new.get(2),bytes) or len(new[2])!=32:
            raise ValueError('Missing partition size/hash')
        result[name]={'bytes':new[1],'sha256':new[2].hex()}
    if set(result)!=PARTITIONS:raise ValueError('Payload must update exactly boot/system/vendor')
    return result


def verify_payload(ota,plan,host,boot_check):
    pinned_certificate(plan,plan['ota_key'])
    info=crypto.verify_ota(ota,plan['ota_key']+'.x509.pem')
    if info.get('post-sdk-level')!='33' or any(k in info for k in ('pre-build','pre-build-incremental')):
        raise ValueError('Expected a full SDK33 OTA, not an incremental/different SDK')
    if info.get('post-build')!=boot_check['signed_build'].get('ro.build.fingerprint'):
        raise ValueError('OTA fingerprint differs from signed target-files')
    with zipfile.ZipFile(ota) as z, tempfile.TemporaryDirectory(prefix='gm8-payload-check-') as temp:
        checked_zip(z)
        payload=Path(temp)/'payload.bin';crypto.copy_entry(z,'payload.bin',payload)
        parts=payload_manifest(payload)
        if parts['boot']!={'bytes':boot_check['boot_bytes'],'sha256':boot_check['boot_sha256']}:
            raise ValueError('OTA payload boot differs from the signed boot image')
        properties=crypto.props(crypto.text(z,'payload_properties.txt'))
        if properties.get('FILE_SIZE')!=str(payload.stat().st_size):raise ValueError('Payload size header mismatch')
        actual=base64.b64encode(bytes.fromhex(crypto.digest(payload))).decode()
        if properties.get('FILE_HASH')!=actual:raise ValueError('Payload FILE_HASH mismatch')
        count=int(properties.get('METADATA_SIZE','0'))
        if not 0<count<=LIMIT:raise ValueError('Invalid payload metadata size')
        with payload.open('rb') as stream:meta=stream.read(count)
        if len(meta)!=count or properties.get('METADATA_HASH')!=base64.b64encode(hashlib.sha256(meta).digest()).decode():
            raise ValueError('Payload METADATA_HASH mismatch')
        public=Path(temp)/'public.pem'
        public.write_bytes(crypto.run(['openssl','x509','-in',plan['ota_key']+'.x509.pem','-pubkey','-noout']))
        # SDK33 delta_generator verifies when --public_key is supplied; there
        # is no invented --verify flag and no payload application is requested.
        subprocess.run([str(host/'bin/delta_generator'),'--in_file='+str(payload),
                        '--public_key='+str(public)],check=True)
    return info,parts


def host_tools(top):
    version=top/'build/core/version_defaults.mk'
    if not re.search(r'^\s*PLATFORM_SDK_VERSION\s*:?=\s*33\s*$',version.read_text(),re.M):
        raise ValueError('Expected the SDK33 source checkout')
    host=top/'out/host/linux-x86'
    for name in ('sign_target_files_apks','ota_from_target_files','apksigner','delta_generator'):
        path=host/'bin'/name
        if not path.is_file() or not os.access(path,os.X_OK):raise ValueError('Missing executable; run m otatools: '+str(path))
    java=find_java(top)
    os.environ['PATH']=str(Path(java).parent)+os.pathsep+str(host/'bin')+os.pathsep+os.environ.get('PATH','')
    return host,java


def sign(plan,output,host,java,password):
    if crypto.digest(plan['target'])!=plan['target_sha256']:raise ValueError('Target-files changed since planning')
    for scope in ('system','recovery'):trusted_certificates(plan,scope)
    for base in sorted({c['key'] for c in plan['certificates'].values()}):
        require_pair(base);crypto.validate_private(base,password)
    for c in plan['certificates'].values():
        if hashlib.sha256(crypto.cert_der(c['key']+'.x509.pem')).hexdigest()!=c['new_sha256']:
            raise ValueError('Public signing identity changed since planning')
    signed=output/'signed-target_files.zip';ota=output/'gm8-20.0-userdebug-firstboot.zip';boot=output/'gm8-20.0-userdebug-firstboot-boot.img'
    if any(p.exists() for p in (signed,ota,boot,output/'verification.json')):raise ValueError('Outputs already exist; preserve them and use a new plan directory')
    needed=6*Path(plan['target']).stat().st_size+2*1024**3
    if shutil.disk_usage(output).free<needed:raise ValueError('Insufficient staging space for signing/images/payload verification')
    # Explicit maps cover all actual APK signers and the primary OTA signer.
    # Do not add -d: it implicitly maps unused SDK33 roles and can require a
    # private key for a public-only extra trust anchor that is not being signed.
    command=[host/'bin/sign_target_files_apks','-p',host,'--java_path',java,'-o']
    for old,c in sorted(plan['certificates'].items()):command+=['-k',old.removesuffix('.x509.pem')+'='+c['key']]
    for name in plan['unused_apex_metadata']:
        command+=['--extra_apks',name+'=','--extra_apex_payload_key',name+'=']
    command+=[plan['target'],signed]
    with tempfile.TemporaryDirectory(dir=output,prefix='.passwords-') as tmp:
        pw=Path(tmp)/'passwords'
        with os.fdopen(os.open(pw,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
            for base in sorted({c['key'] for c in plan['certificates'].values()}):stream.write(f'[[[ {password} ]]] {base}\n')
        env={**os.environ,'ANDROID_PW_FILE':str(pw),'TMPDIR':str(output)};env.pop('ANDROID_SECURE_STORAGE_CMD',None);env.pop('EDITOR',None)
        subprocess.run([str(a) for a in command],check=True,env=env)
        checked=verify_signed(plan,signed,host)
        subprocess.run([str(host/'bin/ota_from_target_files'),'-p',str(host),'--java_path',java,
                        '-k',plan['ota_key'],str(signed),str(ota)],check=True,env=env)
    ota_info,parts=verify_payload(ota,plan,host,checked)
    for base in sorted({c['key'] for c in plan['certificates'].values()}):pinned_certificate(plan,base)
    for scope in ('system','recovery'):trusted_certificates(plan,scope)
    with zipfile.ZipFile(signed) as z:crypto.copy_entry(z,'IMAGES/boot.img',boot)
    result={**checked,'source_target_sha256':plan['target_sha256'],'signed_target_sha256':crypto.digest(signed),
            'ota_sha256':crypto.digest(ota),'ota_metadata':ota_info,'payload_partitions':parts,
            'whole_ota_signature_verified':True,'payload_signature_verified':True,
            'hardware_tested':False,'public_release':False,'requires_clean_install':True,
            'automatic_wipe':False,'output_zip':str(ota),'output_boot':str(boot)}
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified hardware-test OTA: '+str(ota))
    print('Matching signed recovery-as-boot: '+str(boot))
    print('Verification: '+str(output/'verification.json'))
    print('Not hardware-validated. No phone was modified. Plan backup/clean F2FS installation before the first boot test.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('plan','sign'))
    parser.add_argument('--top',type=Path,required=True)
    parser.add_argument('--target-files',type=Path)
    parser.add_argument('--key-dir',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();os.umask(0o077)
    try:
        top=args.top.expanduser().resolve(strict=True);host,java=host_tools(top)
        output=args.output_dir.expanduser().resolve()
        if output==top or top in output.parents:raise ValueError('Output must be outside the Android checkout')
        output.mkdir(mode=0o700,parents=True,exist_ok=True)
        if output.stat().st_uid!=os.getuid() or stat.S_IMODE(output.stat().st_mode)&0o077:
            raise ValueError('Output must be owned by this user with mode 0700')
        tempfile.tempdir=str(output)
        planfile=output/'firstboot-plan.json'
        if args.stage=='plan':
            if args.target_files is None or args.key_dir is None:raise ValueError('plan requires --target-files and --key-dir')
            if any(output.iterdir()):raise ValueError('Plan output directory must be empty')
            keys=existing_key_dir(args.key_dir,top)
            target=args.target_files.expanduser().resolve(strict=True)
            plan=inventory(top,target,keys)
            with planfile.open('x') as stream:json.dump(plan,stream,indent=2);stream.write('\n')
            print(f'Planned {len(plan["apks"])} APKs and {len(plan["flattened_manifests"])} flattened APEXes: {planfile}')
            print(f'Planned OTA trust: system={len(plan["trust_stores"]["system"])}, recovery={len(plan["trust_stores"]["recovery"])} certificate entries.')
            print('Existing keys only; no keys generated and no signing/device operation performed.')
        else:
            plan=json.loads(planfile.read_text())
            if plan['schema']!=2 or plan['top']!=str(top) or plan['sdk']!=33 or plan['variant']!='userdebug':raise ValueError('Plan does not match the current SDK33 userdebug signer; create a fresh plan directory')
            existing_key_dir(plan['key_dir'],top)
            sign(plan,output,host,java,crypto.key_password())
    except (OSError,ValueError,KeyError,RuntimeError,zipfile.BadZipFile,subprocess.SubprocessError) as error:
        parser.exit(1,'ERROR: '+str(error)+'\n')


if __name__=='__main__':main()
