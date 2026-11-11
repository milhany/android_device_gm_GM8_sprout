#!/usr/bin/env python3
"""Exercise the real inspector on small ZIPs, including incomplete and ambiguous inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/inspect-target-files-20.0.py'
SPEC = importlib.util.spec_from_file_location('inspect_gm8_target_files', SCRIPT)
INSPECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECTOR)


class InspectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.top = Path(self.temp.name)
        self.folder = self.top / INSPECTOR.PRODUCT / 'obj/PACKAGING/target_files_intermediates'
        self.folder.mkdir(parents=True)
        self.target = self.folder / 'target_files.zip'
        self.output = self.top / 'report.json'
        self.entries = {
            'SYSTEM/build.prop': 'ro.build.version.sdk=33\nro.build.type=userdebug\nro.product.system.device=GM8_sprout\n',
            'VENDOR/etc/fstab.qcom': '/dev/block/by-name/userdata /data f2fs rw wait,check,encryptable=footer,quota\n',
            'SYSTEM/etc/cgroups.json': '{"Cgroups": [], "Cgroups2": [{"Controller":"cpu"}]}',
            'VENDOR/etc/cgroups.json': '{"Cgroups": [{"Controller":"cpu","Path":"/dev/cpuctl"}]}',
            'VENDOR/etc/task_profiles.json': '{"Profiles": []}',
            'SYSTEM/apex/com.android.art/apex_manifest.pb': b'not parsed',
            'SYSTEM/etc/bpf/netd.o': b'not parsed',
            'IMAGES/boot.img': b'not a real boot image',
        }
        self.write_zip()

    def write_zip(self):
        with zipfile.ZipFile(self.target, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, value in self.entries.items():
                archive.writestr(name, value)

    def run_cli(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), '--top', str(self.top),
                               '--output', str(self.output), *extra],
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_packaged_facts_and_config_are_read_without_certifying_images(self):
        kernel = self.top / INSPECTOR.PRODUCT / 'obj/KERNEL_OBJ'
        (kernel / 'include/config').mkdir(parents=True)
        (kernel / '.config').write_text('CONFIG_CGROUPS=y\n# CONFIG_BPF_SYSCALL is not set\n')
        (kernel / 'include/config/kernel.release').write_text('3.18.124-test\n')
        before = hashlib.sha256(self.target.read_bytes()).hexdigest()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.output.read_text())
        self.assertFalse(report['ready_for_installation'])
        self.assertFalse(report['hardware_validated'])
        self.assertEqual(report['current_build_tree_kernel']['symbols']['CONFIG_BPF_SYSCALL'], 'n')
        self.assertEqual(report['current_build_tree_kernel']['symbols']['CONFIG_PSI'], 'absent')
        self.assertEqual(report['properties']['SYSTEM/build.prop']['ro.product.system.device'], 'GM8_sprout')
        self.assertTrue(any('legacy FDE' in line for line in report['observations']))
        self.assertIn('VENDOR/etc/cgroups.json', report['cgroup_configs'])
        self.assertEqual(len(report['apex_inventory']['flattened_manifests']), 1)
        self.assertIn('SYSTEM/etc/bpf/netd.o', report['network_inventory'])
        self.assertEqual(before, hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertFalse((self.top / 'SYSTEM').exists())

    def test_ambiguity_requires_explicit_archive(self):
        other = self.folder / 'other.zip'
        other.write_bytes(self.target.read_bytes())
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--target-files explicitly', result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.run_cli('--target-files', str(self.target)).returncode, 0)

    def test_invalid_zip_stops_without_a_success_report(self):
        self.target.write_text('version https://git-lfs.github.com/spec/v1\n')
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_duplicate_entry_is_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.target, 'a') as archive:
                archive.writestr('SYSTEM/build.prop', 'ro.build.version.sdk=33\n')
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Duplicate archive entries', result.stderr)

    def test_large_compressed_text_is_bounded(self):
        self.entries['SYSTEM/build.prop'] = 'X' * (INSPECTOR.TEXT_LIMIT + 1)
        self.write_zip()
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exceeds 1 MiB', result.stderr)
        self.assertFalse(self.output.exists())

    def test_wrong_sdk_is_rejected(self):
        self.entries['SYSTEM/build.prop'] = 'ro.build.version.sdk=32\n'
        self.write_zip()
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.write_text('keep this file\n')
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertEqual(self.output.read_text(), 'keep this file\n')

    def test_missing_data_fstab_does_not_claim_acceptance(self):
        del self.entries['VENDOR/etc/fstab.qcom']
        self.write_zip()
        self.assertEqual(self.run_cli().returncode, 0)
        report = json.loads(self.output.read_text())
        self.assertFalse(report['ready_for_installation'])
        self.assertTrue(any('No /data entry' in line for line in report['observations']))

    def test_file_encryption_is_an_observation_not_a_boot_pass(self):
        self.entries['VENDOR/etc/fstab.qcom'] = '/dev/block/by-name/userdata /data f2fs rw wait,fileencryption=aes-256-xts:aes-256-cts:v1\n'
        self.write_zip()
        self.assertEqual(self.run_cli().returncode, 0)
        report = json.loads(self.output.read_text())
        self.assertFalse(any('legacy FDE' in line for line in report['observations']))
        self.assertFalse(report['ready_for_installation'])


if __name__ == '__main__':
    unittest.main()
