#!/usr/bin/env python3
"""Inspect an existing GM8 SDK33 target-files ZIP without rebuilding or extracting it."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile


PRODUCT = 'out/target/product/GM8_sprout'
TEXT_LIMIT = 1024 * 1024
CONFIG_KEYS = (
    'BPF', 'BPF_SYSCALL', 'BPF_JIT', 'CGROUP_BPF', 'CGROUPS', 'CGROUP_SCHED',
    'CGROUP_CPUACCT', 'CGROUP_FREEZER', 'CPUSETS', 'CFS_BANDWIDTH', 'MEMCG', 'MEMCG_SWAP',
    'MEMCG_SWAP_ENABLED', 'PSI', 'F2FS_FS', 'F2FS_FS_ENCRYPTION',
    'FS_ENCRYPTION', 'EXT4_ENCRYPTION', 'ANDROID_BINDER_IPC',
    'ANDROID_BINDER_DEVICES', 'ASHMEM', 'ZRAM', 'ZSMALLOC',
    'NETFILTER_XT_MATCH_QTAGUID', 'NETFILTER_XT_MATCH_OWNER',
    'NETFILTER_XT_MATCH_BPF', 'INET_UDP_DIAG',
)
PROJECTS = (
    'device/gm/GM8_sprout', 'vendor/gm/GM8_sprout', 'kernel/gm/msm8937',
    'system/core', 'system/netd', 'system/bpf',
    'packages/modules/Connectivity', 'packages/modules/Wifi',
    'frameworks/opt/telephony', 'vendor/gapps',
)


def text_from_zip(archive, name):
    info = archive.getinfo(name)
    if info.file_size > TEXT_LIMIT:
        raise ValueError('Text entry exceeds 1 MiB: ' + name)
    with archive.open(info) as stream:
        data = stream.read(TEXT_LIMIT + 1)
    if len(data) > TEXT_LIMIT:
        raise ValueError('Text entry exceeds 1 MiB: ' + name)
    return data.decode('utf-8')


def properties(text):
    return dict(line.split('=', 1) for line in text.splitlines()
                if '=' in line and not line.lstrip().startswith('#'))


def current_sources(top):
    result = {}
    for project in PROJECTS:
        path = top / project
        def git(*args):
            return subprocess.run(['git', '--no-optional-locks', '-C', str(path), *args],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, timeout=30, check=True).stdout.strip()
        try:
            if Path(git('rev-parse', '--show-toplevel')).resolve() != path.resolve():
                raise ValueError('Not a project checkout')
            result[project] = {
                'head': git('rev-parse', 'HEAD'),
                'tracked_dirty': bool(git('status', '--porcelain', '--untracked-files=no')),
            }
        except (OSError, ValueError, subprocess.SubprocessError):
            result[project] = {'unavailable': True}
    return result


def build_tree_kernel(top):
    root = top / PRODUCT / 'obj/KERNEL_OBJ'
    result = {'provenance': 'Current build-tree files; not proof of the kernel packaged in the ZIP.'}
    path = root / '.config'
    if path.is_file():
        data = path.read_bytes()
        if len(data) > TEXT_LIMIT:
            raise ValueError('Kernel .config exceeds 1 MiB')
        text = data.decode('utf-8')
        values = properties(text)
        disabled = set(re.findall(r'^# (CONFIG_\w+) is not set$', text, re.M))
        result['config_sha256'] = hashlib.sha256(data).hexdigest()
        result['symbols'] = {
            'CONFIG_' + key: values.get('CONFIG_' + key,
                                       'n' if 'CONFIG_' + key in disabled else 'absent')
            for key in CONFIG_KEYS
        }
    else:
        result['config_missing'] = True
    release = root / 'include/config/kernel.release'
    if release.is_file():
        if release.stat().st_size > 1024:
            raise ValueError('Unexpected kernel.release size')
        result['release'] = release.read_text().strip()
    return result


def inspect(top, target):
    observations = []
    report = {
        'schema_version': 1,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'archive': {'path': str(target), 'bytes': target.stat().st_size},
        'properties': {}, 'data_fstabs': {}, 'cgroup_configs': {},
        'observations': observations,
        'ready_for_installation': False, 'hardware_validated': False,
    }
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        duplicates = [name for name, count in Counter(names).items() if count > 1]
        if duplicates:
            raise ValueError('Duplicate archive entries: ' + ', '.join(duplicates[:5]))
        names = sorted(names)
        for name in names:
            if re.fullmatch(r'(SYSTEM|VENDOR|PRODUCT|SYSTEM_EXT|ODM)/(system/|etc/)?build\.prop', name):
                props = properties(text_from_zip(archive, name))
                report['properties'][name] = {
                    k: v for k, v in props.items()
                    if re.fullmatch(r'ro\.(build\.(version\.(sdk|release|security_patch)|type|tags|fingerprint)|'
                                    r'product\.((system|vendor|product|odm|system_ext)\.)?(device|name)|lineage\.version)', k)
                }
            if re.fullmatch(r'(SYSTEM|VENDOR|BOOT/RAMDISK)/(.*/)?(fstab\.[^/]+|recovery\.fstab)', name):
                entries = []
                for line in text_from_zip(archive, name).splitlines():
                    fields = line.split('#', 1)[0].split()
                    if len(fields) >= 5 and fields[1] == '/data':
                        entries.append(dict(zip(('source', 'mount', 'type', 'mount_flags',
                                                 'fs_mgr_flags'), fields[:5])))
                if entries:
                    report['data_fstabs'][name] = entries
            if re.fullmatch(r'(SYSTEM|VENDOR)/etc/(cgroups|task_profiles)\.json', name):
                report['cgroup_configs'][name] = json.loads(text_from_zip(archive, name))
        sdks = {p['ro.build.version.sdk'] for p in report['properties'].values()
                if 'ro.build.version.sdk' in p}
        if '33' not in sdks:
            raise ValueError('No SDK33 build property found in target-files')
        if not report['data_fstabs']:
            observations.append('No /data entry found in the inspected packaged fstab paths.')
        for path, entries in report['data_fstabs'].items():
            for entry in entries:
                flags = entry['fs_mgr_flags'].split(',')
                legacy = any(f.startswith(('forceencrypt=', 'forcefdeorfbe=')) for f in flags)
                legacy |= (any(f.startswith('encryptable=') for f in flags) and
                           not any(f.startswith('voldmanaged=') for f in flags))
                if legacy:
                    observations.append(path + ': /data has legacy FDE flags; SDK33 normal-boot parser rejects these outside recovery.')
                if not any(f.startswith('fileencryption=') for f in flags):
                    observations.append(path + ': /data has no fileencryption= flag; FBE support is not established.')
        report['apex_inventory'] = {
            'packaged': [n for n in names if '/apex/' in n and n.endswith(('.apex', '.capex'))],
            'flattened_manifests': [n for n in names if '/apex/' in n and n.endswith('/apex_manifest.pb')],
        }
        report['network_inventory'] = [n for n in names if
                                       n.endswith('/bpfloader') or
                                       ('/etc/bpf/' in n and n.endswith('.o'))]
        report['boot_components'] = {n: archive.getinfo(n).file_size for n in
                                     ('BOOT/kernel', 'IMAGES/boot.img', 'BOOT/RAMDISK/init',
                                      'BOOT/RAMDISK/system/bin/init') if n in names}
        report['integrity_scope'] = 'ZIP directory and selected text CRCs checked; image/APEX/APK payloads not validated.'
    report['current_build_tree_kernel'] = build_tree_kernel(top)
    report['current_source_checkouts'] = current_sources(top)
    report['source_provenance'] = 'Inspection-time HEADs and tracked edits; not a manifest binding the ZIP to these revisions.'
    observations.append('SDK33 network/BPF, cgroup-v1, radio, Wi-Fi and userdata runtime acceptance remain open.')
    return report


def choose_target(top, explicit=None):
    if explicit:
        return explicit.resolve(strict=True)
    folder = top / PRODUCT / 'obj/PACKAGING/target_files_intermediates'
    choices = sorted(folder.glob('*.zip'))
    if len(choices) != 1:
        raise ValueError(f'Expected exactly one target-files ZIP, found {len(choices)}; use --target-files explicitly.')
    return choices[0].resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    parser.add_argument('--target-files', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        top = args.top.resolve(strict=True)
        target = choose_target(top, args.target_files)
        output = args.output.resolve()
        if output == target or output.exists():
            raise ValueError('Output must be a new file; existing files are never overwritten.')
        report = inspect(top, target)
        # Exclusive creation also preserves a file created since the check above.
        with output.open('x') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        parser.exit(1, f'ERROR: {error}\n')
    print('Report:', output)
    for item in report['observations']:
        print('REVIEW:', item)
    print('Read-only inspection finished; no build, signing or device operation performed.')


if __name__ == '__main__':
    main()
