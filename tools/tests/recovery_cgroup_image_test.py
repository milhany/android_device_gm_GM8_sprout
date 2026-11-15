#!/usr/bin/env python3
"""Recovery boot repair: preserve real content and reject unsupported images."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import stat
import struct
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('repair',ROOT/'tools/make-recovery-cgroup-test.py')
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)


def fixture(extra=()):
    entries=[('vendor',b'',stat.S_IFDIR|0o755),
             ('prop.default',b'ro.debuggable=1\nro.adb.secure=1\nro.vendor.gm8.legacy_cgroups=true\n',stat.S_IFREG|0o644),
             ('system/bin/init',b'init fixture',stat.S_IFREG|0o755),
             ('init',b'/system/bin/init',stat.S_IFLNK|0o777),
             ('system/etc/security/otacerts.zip',b'certificate fixture',stat.S_IFREG|0o644),*extra]
    raw=b''.join(repair.record(n,b,m,i) for i,(n,b,m) in enumerate(entries,1))
    ram=gzip.compress(raw+repair.record('TRAILER!!!',b'',0,0),mtime=0)
    kernel=b'kernel and appended DTBs'
    header=bytearray(2048);header[:8]=b'ANDROID!'
    struct.pack_into('<10I',header,8,len(kernel),0x80008000,len(ram),0x82000000,0,0,0x81e00000,2048,0,0)
    header[64:80]=b'console=ttyHSL0\x00'
    header[576:596]=repair.legacy_id(kernel,ram)
    data=bytes(header)+kernel+b'\0'*(-len(kernel)%2048)+ram+b'\0'*(-len(ram)%2048)+b'\0'*4096
    return data,entries


def checked(data):
    return repair.repair(data,hashlib.sha256(data).hexdigest())


class RecoveryRepairTest(unittest.TestCase):
    def test_preserves_header_kernel_existing_files_and_adds_policy(self):
        original,entries=fixture();output,report=checked(original)
        before=bytearray(original[:2048]);after=bytearray(output[:2048])
        for header in (before,after):
            header[16:20]=b'\0'*4;header[576:596]=b'\0'*20
        self.assertEqual(before,after)
        ks=struct.unpack_from('<I',output,8)[0];rs=struct.unpack_from('<I',output,16)[0]
        self.assertEqual(output[2048:2048+repair.align(ks)],original[2048:2048+repair.align(ks)])
        start=2048+repair.align(ks);ram=output[start:start+rs]
        files=repair.firstboot.ramdisk_files(ram)
        for name,body,mode in entries:self.assertEqual(files[name],(mode,body))
        repair.firstboot.verify_recovery_cgroups(files)
        self.assertEqual(output[576:596],repair.legacy_id(output[2048:2048+ks],ram))
        self.assertEqual(report['added'],['vendor/etc','vendor/etc/cgroups.json','vendor/etc/task_profiles.json'])
        with self.assertRaisesRegex(ValueError,'already exists'):checked(output)

    def test_rejects_wrong_hash_corruption_signature_and_truncation(self):
        data,_=fixture()
        with self.assertRaisesRegex(ValueError,'SHA256'):repair.repair(data,'0'*64)
        corrupt=bytearray(data);corrupt[2048]^=1
        with self.assertRaisesRegex(ValueError,'boot ID'):checked(bytes(corrupt))
        with self.assertRaisesRegex(ValueError,'tail'):checked(data[:-1]+b'X')
        with self.assertRaisesRegex(ValueError,'Truncated'):checked(data[:5000])

    def test_rejects_policy_collision_and_symlink_parent(self):
        for extra in ([('vendor/etc',b'/outside',stat.S_IFLNK|0o777)],
                      [('vendor/etc/cgroups.json',b'{}',stat.S_IFREG|0o644)]):
            with self.assertRaises(ValueError):checked(fixture(extra)[0])


if __name__=='__main__':unittest.main(verbosity=2)
