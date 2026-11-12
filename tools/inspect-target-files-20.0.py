#!/usr/bin/env python3
"""Inspect an existing GM8 SDK33 target-files ZIP without rebuilding or extracting it."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import xml.etree.ElementTree as ET
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


def wifi_init_service(archive):
    """Check the packaged AIDL contract, not just PRODUCT_PACKAGES/VINTF claims."""
    declarations=[];manifests=[]
    interface='android.hardware.wifi.supplicant.ISupplicant/default'
    for path in archive.namelist():
        if re.fullmatch(r'VENDOR/etc/init/(?:.*/)?[^/]+\.rc',path):
            # Init service options and continued command lines are indented;
            # the next top-level section terminates the current service.
            section=None
            for line in text_from_zip(archive,path).splitlines():
                raw=line.split('#',1)[0].rstrip()
                if not raw.strip():continue
                if not raw[0].isspace():
                    words=raw.split();section=None
                    if len(words)>=3 and words[:2]==['service','wpa_supplicant']:
                        section={'rc':path,'executable':words[2],'options':[]}
                        declarations.append(section)
                elif section is not None:section['options'].append(raw.split())
        if re.fullmatch(r'VENDOR/etc/vintf/(?:manifest\.xml|manifest/[^/]+\.xml)',path):
            try:root=ET.fromstring(text_from_zip(archive,path))
            except ET.ParseError as error:raise ValueError('Invalid packaged VINTF XML: '+path) from error
            for hal in root.findall('hal'):
                if hal.get('format')!='aidl' or hal.findtext('name')!='android.hardware.wifi.supplicant':continue
                for name in hal.findall('fqname'):
                    if (name.text or '').strip()=='ISupplicant/default':manifests.append(path)
                for item in hal.findall('interface'):
                    if item.findtext('name')=='ISupplicant':
                        manifests.extend(path for name in item.findall('instance') if (name.text or '').strip()=='default')
    if len(declarations)!=1:raise ValueError('Expected exactly one packaged wpa_supplicant init service; found '+str(len(declarations)))
    entry=declarations[0]
    if ['interface','aidl',interface] not in entry['options']:
        raise ValueError('Packaged supplicant init service lacks the AIDL ISupplicant/default interface')
    if entry['executable']!='/vendor/bin/hw/wpa_supplicant':raise ValueError('Unexpected packaged supplicant executable')
    binary='VENDOR/bin/hw/wpa_supplicant'
    if binary not in archive.namelist() or archive.getinfo(binary).file_size==0:
        raise ValueError('Missing packaged supplicant executable: '+binary)
    if len(manifests)!=1:raise ValueError('Expected exactly one packaged AIDL supplicant VINTF instance; found '+str(len(manifests)))
    return {'rc':entry['rc'],'executable':binary,'interface':interface,'vintf':manifests[0],
            'scope':'Packaged service wiring only; daemon operation and Wi-Fi connectivity require hardware testing.'}


def legacy_runtime_policy(archive):
    """Validate the paired packaged kernel policy and IMS camera callback ABIs."""
    names=archive.namelist()
    vendor=properties(text_from_zip(archive,'VENDOR/build.prop'))
    if vendor.get('ro.vendor.gm8.legacy_cgroups')!='true':
        raise ValueError('Missing packaged GM8 legacy-cgroup policy selector')
    cgroups=json.loads(text_from_zip(archive,'VENDOR/etc/cgroups.json'))
    expected={'cpu':'/dev/cpuctl','cpuset':'/dev/cpuset','cpuacct':'/acct'}
    entries=cgroups.get('Cgroups',[])
    if ('Cgroups2' in cgroups or len(entries)!=3 or
            {c['Controller']:c['Path'] for c in entries}!=expected):
        raise ValueError('Packaged legacy cgroup controllers do not match the supported GM8 policy')
    profiles=json.loads(text_from_zip(archive,'VENDOR/etc/task_profiles.json'))
    attrs={a['Name'] for a in profiles.get('Attributes',[])}
    for attr in profiles.get('Attributes',[]):
        if attr['Controller'] not in expected or attr['File'].startswith('cpu.uclamp.'):
            raise ValueError('Unsupported packaged legacy cgroup attribute')
    available={p['Name'] for p in profiles.get('Profiles',[])}
    if len(available)!=40 or len(profiles.get('AggregateProfiles',[]))!=15:
        raise ValueError('Incomplete packaged GM8 task profile database')
    for profile in profiles['Profiles']:
        for action in profile['Actions']:
            params=action.get('Params',{})
            if action['Name']=='SetClamps':raise ValueError('Legacy kernel does not implement uclamp')
            if action['Name']=='JoinCgroup' and params['Controller'] not in expected:
                raise ValueError('Task profile references an unsupported controller')
            if action['Name']=='SetAttribute' and params['Name'] not in attrs:
                raise ValueError('Task profile references an absent attribute')
    if any(not set(p['Profiles'])<=available for p in profiles['AggregateProfiles']):
        raise ValueError('Aggregate task profile references an absent profile')
    libraries={}
    for directory,elf_class,machine in [('lib',1,40),('lib64',2,183)]:
        suffix=directory+'/vendor.qti.hardware.camera.device@1.0.so'
        matches=[n for n in names if n in {'SYSTEM_EXT/'+suffix,'SYSTEM/system_ext/'+suffix}]
        if len(matches)!=1:raise ValueError('Missing/duplicate packaged IMS camera callback ABI: '+suffix)
        with archive.open(matches[0]) as stream:header=stream.read(64)
        if (len(header)<20 or header[:4]!=b'\x7fELF' or header[4]!=elf_class or
                header[5]!=1 or struct.unpack_from('<H',header,18)[0]!=machine):
            raise ValueError('Wrong packaged IMS camera callback ELF ABI: '+matches[0])
        libraries[directory]=matches[0]
    if vendor.get('ro.vendor.extension_library')!='libqti-perfd-client.so':
        raise ValueError('Missing packaged Qualcomm audio/video performance client selection')
    for directory in ('lib','lib64'):
        if 'VENDOR/'+directory+'/libqti-perfd-client.so' not in names:
            raise ValueError('Missing packaged Qualcomm performance client: '+directory)
    return {'controllers':expected,'profiles':len(available),'ims_camera_libraries':libraries,
            'performance_client':'libqti-perfd-client.so',
            'scope':'Packaged policy, presence and ELF architecture checks; not runtime/IMS/audio acceptance.'}


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
        report['wifi_service']=wifi_init_service(archive)
        report['legacy_runtime_policy']=legacy_runtime_policy(archive)
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
