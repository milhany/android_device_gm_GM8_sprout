#!/usr/bin/env python3
"""SDK33 planning/verification fixtures with real OpenSSL keys and OTA signatures.

Android apksigner/image rebuilding and delta_generator execution are explicit
fixtures here; the owner must run the actual binaries before installation.
"""
import base64
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('firstboot',ROOT/'tools/firstboot-20.0.py')
signer=importlib.util.module_from_spec(spec);spec.loader.exec_module(signer)


def zipped(entries):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,value in entries.items():z.writestr(name,value)
    return out.getvalue()


def cpio(entries):
    out=bytearray()
    for name,data,mode in [*entries,('TRAILER!!!',b'',0)]:
        raw=name.encode()+b'\0';fields=[0,mode,0,0,1,0,len(data),0,0,0,0,len(raw),0]
        out+=b'070701'+''.join(f'{v:08x}' for v in fields).encode()+raw
        out+=b'\0'*(-len(out)%4);out+=data;out+=b'\0'*(-len(out)%4)
    return bytes(out)


def boot(kernel,store,debug='1'):
    ram=gzip.compress(cpio([('prop.default',f'ro.debuggable={debug}\n'.encode(),stat.S_IFREG|0o644),
        ('system/etc/security/otacerts.zip',store,stat.S_IFREG|0o644)]))
    header=bytearray(2048);header[:8]=b'ANDROID!'
    struct.pack_into('<I',header,8,len(kernel));struct.pack_into('<I',header,16,len(ram))
    struct.pack_into('<I',header,36,2048)
    return bytes(header)+kernel+b'\0'*(-len(kernel)%2048)+ram


def varint(value):
    out=bytearray()
    while value>127:out.append((value&127)|128);value>>=7
    out.append(value);return bytes(out)


def field(number,value):
    if isinstance(value,int):return varint(number<<3)+varint(value)
    return varint(number<<3|2)+varint(len(value))+value


def payload(bootdata,parts=('boot','system','vendor'),minor=0,old=False):
    manifest=field(12,minor)
    for name in parts:
        data=bootdata if name=='boot' else name.encode()
        info=field(1,len(data))+field(2,hashlib.sha256(data).digest())
        row=field(1,name.encode())+field(7,info)
        if old:row+=field(6,b'')
        manifest+=field(13,row)
    return struct.pack('>4sQQI',b'CrAU',2,len(manifest),4)+manifest+b'sign'+b'payload-data'


def key(base):
    base.parent.mkdir(parents=True,exist_ok=True)
    signer.crypto.run(['openssl','req','-newkey','rsa:2048','-nodes','-x509','-sha256',
        '-days','1','-subj','/CN=GM8 SDK33 Host Fixture','-keyout',str(base)+'.pem','-out',str(base)+'.x509.pem'])
    signer.crypto.run(['openssl','pkcs8','-topk8','-nocrypt','-in',str(base)+'.pem','-outform','DER','-out',str(base)+'.pk8'])
    Path(str(base)+'.pk8').chmod(0o600)


class FirstBootTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='gm8-firstboot-crypto-')
        cls.root=Path(cls.temp.name)
        key(cls.root/'source');key(cls.root/'release')
        key(cls.root/'recovery-extra');key(cls.root/'system-extra')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='gm8-firstboot-test-')
        self.addCleanup(self.temp.cleanup);self.work=Path(self.temp.name)
        self.top=self.work/'android';self.top.mkdir()
        self.keys=self.work/'keys';self.keys.mkdir(mode=0o700)
        security=self.top/'build/make/target/product/security';security.mkdir(parents=True)
        for name in ('testkey','shared'):
            shutil.copyfile(self.root/'source.x509.pem',security/(name+'.x509.pem'))
        for suffix in ('.x509.pem','.pk8'):shutil.copyfile(self.root/('release'+suffix),self.keys/('releasekey'+suffix))
        (self.keys/'releasekey.pk8').chmod(0o600)
        self.cert=(self.keys/'releasekey.x509.pem').read_bytes()
        self.store=zipped({'releasekey.x509.pem':self.cert})
        self.kernel=b'fixture-kernel';self.boot=boot(self.kernel,self.store)
        old='build/make/target/product/security/testkey.x509.pem'
        alias='build/make/target/product/security/shared.x509.pem'
        self.entries={
            'SYSTEM/build.prop':'ro.build.version.sdk=33\nro.build.type=userdebug\nro.build.tags=test-keys\nro.build.product=GM8_sprout\nro.build.fingerprint=essential/mata/mata:8.1.0/id/399:user/release-keys\n',
            'META/misc_info.txt':'ab_update=true\ndefault_system_dev_certificate=build/make/target/product/security/testkey\n',
            'META/ab_partitions.txt':'boot\nsystem\nvendor\n','META/otakeys.txt':'',
            'META/apkcerts.txt':f'name="System.apk" certificate="{old}" private_key="a.pk8"\nname="Flat.apk" certificate="{alias}" private_key="a.pk8"\nname="Gms.apk" certificate="PRESIGNED" private_key=""\n',
            'META/apexkeys.txt':f'name="com.android.fixture.apex" public_key="unused.avbpubkey" private_key="unused.pem" container_certificate="{old}" container_private_key="unused.pk8"\n',
            'VENDOR/etc/fstab.qcom':'/dev/block/by-name/userdata /data f2fs rw,noatime wait,check,formattable,quota\n',
            'BOOT/RAMDISK/system/etc/recovery.fstab':'/dev/block/by-name/userdata /data f2fs rw wait,check,formattable,quota\n',
            'BOOT/RAMDISK/prop.default':'ro.debuggable=1\n',
            'SYSTEM/apex/com.android.fixture/apex_manifest.pb':b'flat-manifest',
            'SYSTEM/app/System/System.apk':b'unsigned-app',
            'SYSTEM/apex/com.android.fixture/app/Flat/Flat.apk':b'flattened-apex-apk',
            'SYSTEM/product/priv-app/Gms/Gms.apk':b'presigned-google',
            'SYSTEM/etc/security/otacerts.zip':self.store,
            'BOOT/RAMDISK/system/etc/security/otacerts.zip':self.store,
            'BOOT/kernel':self.kernel,'IMAGES/boot.img':self.boot,
            'IMAGES/system.img':b'system','IMAGES/vendor.img':b'vendor'}
        self.target=self.work/'target.zip';self.write_target()

    def write_target(self):self.target.write_bytes(zipped(self.entries))

    def plan(self):return signer.inventory(self.top,self.target,self.keys)

    def test_plan_uses_existing_keys_and_all_flattened_apks(self):
        before={p.name:p.read_bytes() for p in self.keys.iterdir()}
        plan=self.plan()
        self.assertEqual(len(plan['apks']),3)
        self.assertEqual({c['key'] for c in plan['certificates'].values()},{str(self.keys/'releasekey')})
        self.assertEqual(plan['unused_apex_metadata'],['com.android.fixture.apex'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.keys.iterdir()})
        self.assertTrue(any('/apex/' in a['entry'] and a['key'] for a in plan['apks']))

    def test_missing_or_exposed_keys_are_not_generated_or_overwritten(self):
        (self.keys/'releasekey.pk8').unlink()
        with self.assertRaisesRegex(ValueError,'no keys generated'):self.plan()
        self.assertFalse((self.keys/'releasekey.pk8').exists())
        shutil.copyfile(self.root/'release.pk8',self.keys/'releasekey.pk8');(self.keys/'releasekey.pk8').chmod(0o644)
        with self.assertRaisesRegex(ValueError,'Private key'):self.plan()
        self.keys.chmod(0o755)
        with self.assertRaisesRegex(ValueError,'0700'):signer.existing_key_dir(self.keys,self.top)

    def test_sdk_variant_encryption_apex_and_partition_gates(self):
        original=dict(self.entries)
        for name,value in [
            ('SYSTEM/build.prop',original['SYSTEM/build.prop'].replace('sdk=33','sdk=32')),
            ('SYSTEM/build.prop',original['SYSTEM/build.prop'].replace('type=userdebug','type=user')),
            ('META/ab_partitions.txt','boot\nsystem\nvendor\npersist\n'),
            ('SYSTEM/apex/new.apex',b'unsupported packed apex'),
            ('META/misc_info.txt',original['META/misc_info.txt']+'avb_enable=true\n'),
            ('META/misc_info.txt',original['META/misc_info.txt']+'use_dynamic_partitions=true\n'),
            ('META/apexkeys.txt','name=\"bad=container.apex\" public_key=\"x\" private_key=\"y\"\n'),
            ('VENDOR/etc/fstab.qcom',original['VENDOR/etc/fstab.qcom'].replace('quota','quota,encryptable=footer')),
            ('BOOT/RAMDISK/prop.default','ro.debuggable=0\n')]:
            self.entries=dict(original);self.entries[name]=value;self.write_target()
            with self.assertRaises(ValueError):self.plan()

    def test_actual_boot_ramdisk_keys_kernel_and_debug_state(self):
        wanted=signer.crypto.cert_der(self.keys/'releasekey.x509.pem')
        digest=hashlib.sha256(self.kernel).hexdigest()
        self.assertEqual(signer.verify_boot(self.boot,digest,wanted),['system/etc/security/otacerts.zip'])
        other=zipped({'wrong.pem':(self.root/'source.x509.pem').read_bytes()})
        for bad in (boot(self.kernel,other),boot(self.kernel,self.store,'0'),boot(b'other-kernel',self.store),self.boot[:-1]):
            with self.assertRaises((ValueError,EOFError,OSError)):signer.verify_boot(bad,digest,wanted)
        with self.assertRaises(ValueError):signer.ramdisk_files(b'not cpio')
        with self.assertRaises(ValueError):signer.ramdisk_files(cpio([('same',b'a',0),('same',b'b',0)]))

    def test_signed_inventory_presigned_bytes_and_all_trust_stores(self):
        plan=self.plan();self.entries['SYSTEM/build.prop']=self.entries['SYSTEM/build.prop'].replace('test-keys','release-keys');self.write_target()
        calls=[]
        with patch.object(signer.crypto,'apk_verify',side_effect=lambda path,cert,host:calls.append((path.name,cert))):
            result=signer.verify_signed(plan,self.target,self.work)
            self.assertEqual(result['apks_checked'],3);self.assertEqual(len(calls),2)
            self.entries['SYSTEM/product/priv-app/Gms/Gms.apk']=b'changed';self.write_target()
            with self.assertRaisesRegex(ValueError,'PRESIGNED'):signer.verify_signed(plan,self.target,self.work)
            self.entries['SYSTEM/product/priv-app/Gms/Gms.apk']=b'presigned-google'
            self.entries['BOOT/RAMDISK/system/etc/security/otacerts.zip']=zipped({'wrong.pem':(self.root/'source.x509.pem').read_bytes()});self.write_target()
            with self.assertRaisesRegex(ValueError,'trust-store'):signer.verify_signed(plan,self.target,self.work)

    def public_extra(self,name):
        base='vendor/lineage/security/'+name
        path=self.top/(base+'.x509.pem');path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(self.root/(name+'.x509.pem'),path)
        return base,path

    def test_public_extra_trust_is_scoped_and_needs_no_private_key(self):
        recovery,path=self.public_extra('recovery-extra')
        system,system_path=self.public_extra('system-extra')
        self.entries['META/misc_info.txt']+=f'extra_recovery_keys={recovery}\nextra_ota_keys={system}\n'
        self.write_target();before={p.name:p.read_bytes() for p in self.keys.iterdir()}
        plan=self.plan()
        self.assertEqual(len(plan['trust_stores']['recovery']),2)
        self.assertEqual(len(plan['trust_stores']['system']),2)
        self.assertEqual(plan['trust_stores']['recovery'][1]['action'],'preserved_public_only')
        self.assertEqual(len(plan['certificates']),2) # testkey + shared alias; no extra private keys
        self.assertFalse(path.with_suffix('.pk8').exists())
        recovery_store=zipped({'release.pem':self.cert,'extra.pem':path.read_bytes()})
        system_store=zipped({'release.pem':self.cert,'extra.pem':system_path.read_bytes()})
        self.entries['SYSTEM/build.prop']=self.entries['SYSTEM/build.prop'].replace('test-keys','release-keys')
        self.entries['SYSTEM/etc/security/otacerts.zip']=system_store
        self.entries['BOOT/RAMDISK/system/etc/security/otacerts.zip']=recovery_store
        self.entries['IMAGES/boot.img']=boot(self.kernel,recovery_store)
        self.write_target()
        with patch.object(signer.crypto,'apk_verify'):
            signer.verify_signed(plan,self.target,self.work)
            # A recovery-only root cannot leak into normal-system trust.
            self.entries['SYSTEM/etc/security/otacerts.zip']=recovery_store;self.write_target()
            with self.assertRaisesRegex(ValueError,'trust-store'):signer.verify_signed(plan,self.target,self.work)
            self.entries['SYSTEM/etc/security/otacerts.zip']=system_store
            # The actual packed ramdisk is verified independently of its tree.
            self.entries['IMAGES/boot.img']=boot(self.kernel,self.store);self.write_target()
            with self.assertRaisesRegex(ValueError,'trust-store'):signer.verify_signed(plan,self.target,self.work)
        path.write_bytes(system_path.read_bytes())
        with self.assertRaisesRegex(ValueError,'changed since planning'):signer.trusted_certificates(plan,'recovery')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.keys.iterdir()})

    def test_extra_alias_remaps_to_used_identity_and_exact_multiplicity(self):
        self.entries['META/misc_info.txt']+='extra_recovery_keys=build/make/target/product/security/shared\n'
        self.write_target();plan=self.plan()
        self.assertEqual(plan['trust_stores']['recovery'][1]['action'],'remapped')
        wanted=signer.trusted_certificates(plan,'recovery')
        self.assertEqual(wanted[0],wanted[1])
        store=io.BytesIO()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(store,'w') as z:
                z.writestr('same.pem',self.cert);z.writestr('same.pem',self.cert)
        signer.trust_store(store.getvalue(),wanted)
        with self.assertRaisesRegex(ValueError,'count'):signer.trust_store(self.store,wanted)
        with self.assertRaisesRegex(ValueError,'count'):signer.trust_store(store.getvalue(),wanted[:1])
        # Same-name entries must each be inspected, not read through ZIP's last-name lookup.
        other=io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(other,'w') as z:
                z.writestr('same.pem',(self.root/'source.x509.pem').read_bytes())
                z.writestr('same.pem',self.cert)
        with self.assertRaisesRegex(ValueError,'differ'):signer.trust_store(other.getvalue(),wanted)

    def test_missing_public_extra_is_rejected_before_signing(self):
        self.entries['META/misc_info.txt']+='extra_recovery_keys=vendor/lineage/missing\n'
        self.write_target()
        with self.assertRaisesRegex(ValueError,'Missing source public certificate'):self.plan()

    def test_payload_manifest_rejects_firmware_incremental_and_corruption(self):
        file=self.work/'payload'
        file.write_bytes(payload(self.boot));good=signer.payload_manifest(file)
        self.assertEqual(set(good),signer.PARTITIONS)
        self.assertEqual(good['boot']['sha256'],hashlib.sha256(self.boot).hexdigest())
        valid=payload(self.boot);length=struct.unpack_from('>Q',valid,12)[0]
        dynamic=valid[24:24+length]+field(15,b'unsupported')
        dynamic=struct.pack('>4sQQI',b'CrAU',2,len(dynamic),4)+dynamic+b'sign'
        for bad in (dynamic,payload(self.boot,parts=('boot','system','persist')),
                    payload(self.boot,parts=('boot','system','vendor','boot')),
                    payload(self.boot,minor=1),payload(self.boot,old=True),b'CrAU',
                    struct.pack('>4sQQI',b'CrAU',2,signer.LIMIT+1,4),
                    struct.pack('>4sQQI',b'CrAU',2,2,4)+b'\x6a\xff'):
            file.write_bytes(bad)
            with self.assertRaises(ValueError):signer.payload_manifest(file)

    def signed_ota(self,extra='',data=None,bad_properties=False):
        data=payload(self.boot) if data is None else data
        meta_size=24+struct.unpack_from('>Q',data,12)[0]
        props='FILE_SIZE='+str(len(data))+'\nFILE_HASH='+base64.b64encode(hashlib.sha256(data).digest()).decode()+'\nMETADATA_SIZE='+str(meta_size)+'\nMETADATA_HASH='+base64.b64encode(hashlib.sha256(data[:meta_size]).digest()).decode()+'\n'
        if bad_properties:props=props.replace('FILE_SIZE='+str(len(data)),'FILE_SIZE=1')
        metadata='ota-type=AB\npre-device=GM8_sprout\npost-sdk-level=33\npost-build=essential/mata/mata:8.1.0/id/399:user/release-keys\n'+extra
        unsigned=zipped({'META-INF/com/android/metadata':metadata,'payload.bin':data,'payload_properties.txt':props})
        content=self.work/'cms-content';content.write_bytes(unsigned[:-2])
        signature=signer.crypto.run(['openssl','cms','-sign','-binary','-in',content,
            '-signer',self.keys/'releasekey.x509.pem','-inkey',self.root/'release.pem',
            '-outform','DER','-nosmimecap','-noattr','-md','sha256'])
        count=len(signature)+6;footer=struct.pack('<HHH',count,0xffff,count)
        ota=self.work/'ota.zip';ota.write_bytes(unsigned[:-2]+struct.pack('<H',count)+signature+footer)
        return ota

    def test_real_whole_ota_crypto_and_payload_verifier_command(self):
        plan=self.plan();ota=self.signed_ota()
        check={'boot_bytes':len(self.boot),'boot_sha256':hashlib.sha256(self.boot).hexdigest(),
               'signed_build':{'ro.build.fingerprint':'essential/mata/mata:8.1.0/id/399:user/release-keys'}}
        # The real delta_generator runs on the build host, after all other
        # checks. Here assert the exact verified SDK33 invocation and its failure.
        actual=subprocess.run;commands=[]
        def invoke(argv,*a,**kw):
            if Path(argv[0]).name=='delta_generator':commands.append(argv);return subprocess.CompletedProcess(argv,0)
            return actual(argv,*a,**kw)
        with patch.object(signer.subprocess,'run',side_effect=invoke):
            info,parts=signer.verify_payload(ota,plan,self.work,check)
            self.assertEqual(info['post-sdk-level'],'33');self.assertEqual(set(parts),signer.PARTITIONS)
            self.assertEqual(len(commands),1);self.assertTrue(commands[0][1].startswith('--in_file='));self.assertTrue(commands[0][2].startswith('--public_key='))
        for extra,data,bad_props in [('ota-wipe=yes\n',None,False),('pre-build=old\n',None,False),
                ('post-sdk-level=32\n',None,False),('',payload(b'other boot'),False),('',None,True)]:
            ota=self.signed_ota(extra,data,bad_props)
            with self.assertRaises(ValueError):signer.verify_payload(ota,plan,self.work,check)
        ota=self.signed_ota();raw=bytearray(ota.read_bytes());raw[raw.index(b'payload-data')]^=1;ota.write_bytes(raw)
        with self.assertRaises((ValueError,subprocess.CalledProcessError,zipfile.BadZipFile)):
            signer.verify_payload(ota,plan,self.work,check)

    def test_sign_orchestration_verifies_before_publishing_and_keeps_keys(self):
        plan=self.plan();keys_before={p.name:p.read_bytes() for p in self.keys.iterdir()}
        actual=subprocess.run;password_files=[];commands=[];fail_payload=False
        def invoke(argv,*a,**kw):
            nonlocal fail_payload
            name=Path(argv[0]).name
            if name in ('sign_target_files_apks','ota_from_target_files'):
                commands.append([str(v) for v in argv]);pw=Path(kw['env']['ANDROID_PW_FILE']);password_files.append(pw)
                self.assertEqual(stat.S_IMODE(pw.stat().st_mode),0o600)
                self.assertNotIn('ANDROID_SECURE_STORAGE_CMD',kw['env'])
                if name=='sign_target_files_apks':
                    self.assertNotIn('-d',argv)
                    self.assertIn('--extra_apks',argv);self.assertIn('com.android.fixture.apex=',argv)
                    entries=dict(self.entries);entries['SYSTEM/build.prop']=entries['SYSTEM/build.prop'].replace('test-keys','release-keys')
                    Path(argv[-1]).write_bytes(zipped(entries))
                else:shutil.copyfile(self.signed_ota(),argv[-1])
                return subprocess.CompletedProcess(argv,0)
            if name=='delta_generator':
                if fail_payload:raise subprocess.CalledProcessError(1,argv)
                return subprocess.CompletedProcess(argv,0)
            return actual(argv,*a,**kw)
        with patch.object(signer.subprocess,'run',side_effect=invoke),patch.object(signer.crypto,'apk_verify'),contextlib.redirect_stdout(io.StringIO()):
            output=self.work/'success';output.mkdir(mode=0o700)
            signer.sign(plan,output,self.work,'java','')
            report=json.loads((output/'verification.json').read_text())
            self.assertTrue(report['payload_signature_verified']);self.assertFalse(report['hardware_tested'])
            self.assertEqual((output/'gm8-20.0-userdebug-firstboot-boot.img').read_bytes(),self.boot)
            self.assertTrue(all(not p.exists() for p in password_files))
            self.assertFalse(any(flag in command for command in commands for flag in ('--wipe_user_data','--downgrade','-i')))
            with self.assertRaisesRegex(ValueError,'Outputs already exist'):signer.sign(plan,output,self.work,'java','')
            fail_payload=True;output=self.work/'failed';output.mkdir(mode=0o700)
            with self.assertRaises(subprocess.CalledProcessError):signer.sign(plan,output,self.work,'java','')
            self.assertFalse((output/'verification.json').exists())
            self.assertFalse((output/'gm8-20.0-userdebug-firstboot-boot.img').exists())
            self.assertTrue(all(not p.exists() for p in password_files))
        self.assertEqual(keys_before,{p.name:p.read_bytes() for p in self.keys.iterdir()})


if __name__=='__main__':unittest.main(verbosity=2)
