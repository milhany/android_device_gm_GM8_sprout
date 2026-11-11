#!/usr/bin/env python3
"""Read-only SDK33 source audit; successful inventory does not imply bootability."""
import argparse
import datetime
import json
import hashlib
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile


BLOCKERS = [
    'Rebase complete legacy accounting/BPF compatibility onto SDK33 Connectivity/netd; loader suppression alone is insufficient.',
    'Review/rebase SDK33 RadioConfig and data/PhoneSwitcher behavior for the GM8 legacy data switch.',
    'Review SDK33 Wi-Fi KeyStore/MAC persistence behavior against the current secure-service fix.',
    'Validate the reviewed SDK33 cgroup-v1 process-tracking source port and task profiles on hardware.',
    'Review optional charging-HAL, SystemUI and recents behavior instead of applying SDK32 framework patches blindly.',
    'Bring-up userdata is explicitly unencrypted F2FS; encrypted installs, FBE and migration are unsupported pending a separate implementation.',
    'Complete SDK33 Soong, module, SELinux/VINTF, vendor ABI and boot acceptance checks.',
    'Complete Android 13 GApps, signing and hardware/battery acceptance after a full build.',
]


def audit(top):
    device = top / 'device/gm/GM8_sprout'
    errors = []
    version = top / 'build/core/version_defaults.mk'
    if not version.is_file() or not re.search(r'^\s*PLATFORM_SDK_VERSION\s*:?=\s*33\s*$', version.read_text(), re.M):
        errors.append('Expected SDK33')
    paths = [
        'build/envsetup.sh', 'vendor/lineage/config/common_full_phone.mk',
        'device/qcom/sepolicy-legacy-um/SEPolicy.mk',
        'hardware/qcom-caf/bootctrl/Android.bp', 'hardware/qcom-caf/msm8996/audio/Android.mk',
        'tools/extract-utils/extract_utils.sh', 'vendor/gapps/arm64/arm64-vendor.mk',
        'device/gm/GM8_sprout/lineage_GM8_sprout.mk',
        'device/gm/GM8_sprout/rootdir/etc/fstab.qcom',
        'vendor/gm/GM8_sprout/GM8_sprout-vendor.mk',
        'kernel/gm/msm8937/Makefile',
        'packages/modules/Connectivity/netd/BpfHandler.cpp',
        'packages/modules/Connectivity/service-t/jni/com_android_server_net_NetworkStatsService.cpp',
        'packages/modules/Connectivity/service/Android.bp',
        'packages/modules/Connectivity/service/native/TrafficController.cpp',
        'frameworks/opt/telephony/src/java/com/android/internal/telephony/RadioConfig.java',
        'frameworks/opt/telephony/src/java/com/android/internal/telephony/data/PhoneSwitcher.java',
        'system/core/libprocessgroup/processgroup.cpp',
        'system/netd/server/FirewallController.cpp', 'system/netd/server/FirewallController.h',
        'system/netd/server/NetdNativeService.cpp',
    ]
    for path in paths:
        if not (top / path).is_file():
            errors.append('Missing source input: ' + path)
    for path in ('prebuilts/vndk/v28', 'prebuilts/vndk/v29', 'prebuilts/vndk/v30', 'prebuilts/vndk/v31'):
        if not (top / path).is_dir():
            errors.append('Missing snapshot: ' + path)
    webview = top / 'external/chromium-webview/prebuilt/arm64'
    webview_apks = sorted(webview.rglob('*.apk'))
    if not webview_apks:
        errors.append('Missing ARM64 WebView APK; complete repo sync with Git LFS enabled')
    for path in webview_apks:
        with path.open('rb') as stream:
            prefix = stream.read(200)
        if prefix.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
            errors.append('Unresolved Git LFS pointer: ' + str(path.relative_to(top)) +
                          '; materialize LFS in the owning prebuilt/arm64 project')
        elif not zipfile.is_zipfile(path):
            errors.append('Invalid APK (not a ZIP archive): ' + str(path.relative_to(top)))
    for path in list(device.rglob('*.xml')) + list(device.rglob('*.json')):
        try:
            if path.suffix == '.xml': ET.parse(path)
            else: json.loads(path.read_text())
        except (ET.ParseError, ValueError, OSError) as error:
            errors.append(f'Invalid source config {path.relative_to(top)}: {error}')
    revisions = {}
    for path in ('device/gm/GM8_sprout', 'vendor/gm/GM8_sprout', 'kernel/gm/msm8937',
                 'vendor/gapps', 'packages/modules/Connectivity', 'frameworks/opt/telephony',
                 'system/core', 'system/netd'):
        result = subprocess.run(['git', '-C', str(top / path), 'rev-parse', 'HEAD'],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0: revisions[path] = result.stdout.strip()
        else: errors.append('Missing Git revision: ' + path)
    patches = []
    project_paths = {
        'system_bpf': 'system/bpf', 'system_netd': 'system/netd',
        'system_core': 'system/core', 'frameworks_opt_telephony': 'frameworks/opt/telephony',
        'frameworks_base': 'frameworks/base', 'lineage_sdk': 'lineage-sdk',
        'packages_modules_Wifi': 'packages/modules/Wifi',
        'packages_modules_NetworkStack': 'packages/modules/NetworkStack',
        'packages_apps_Trebuchet': 'packages/apps/Trebuchet',
    }
    for folder, project in project_paths.items():
        for patch in sorted((device / 'patches' / folder).glob('*.patch')):
            result = subprocess.run(['git', '-C', str(top / project), 'apply', '--check', str(patch)],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            patches.append({'project': project, 'patch': str(patch.relative_to(device)),
                            'context_applies': result.returncode == 0,
                            'sdk33_reviewed': False})
    data_policy = {'mode': 'unencrypted_f2fs_bringup',
                   'encrypted_userdata_supported': False, 'migration_implemented': False}
    fstab = device / 'rootdir/etc/fstab.qcom'
    data_entries = []
    if fstab.is_file():
        for line in fstab.read_text().splitlines():
            fields = line.split('#', 1)[0].split()
            if len(fields) >= 5 and fields[1] == '/data':
                data_entries.append(fields)
    if len(data_entries) != 1 or data_entries[0][2] != 'f2fs':
        errors.append('SDK33 bring-up requires one explicit F2FS /data entry')
    elif any(flag.split('=', 1)[0] in ('encryptable', 'forceencrypt', 'forcefdeorfbe',
                                      'fileencryption', 'metadata_encryption')
             for flag in data_entries[0][4].split(',')):
        errors.append('SDK33 bring-up /data must not claim unsupported FDE/FBE encryption')
    ports = []
    for folder, project in (('system_core', 'system/core'),
                            ('Connectivity', 'packages/modules/Connectivity'),
                            ('system_netd', 'system/netd')):
        for patch in sorted((device / 'patches/sdk33' / folder).glob('*.patch')):
            command = ['git', '-C', str(top / project), 'apply']
            forward = subprocess.run(command + ['--check', str(patch)], capture_output=True)
            reverse = subprocess.run(command + ['--reverse', '--check', str(patch)], capture_output=True)
            ports.append({'project': project, 'patch': str(patch.relative_to(device)),
                          'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
                          'applied': reverse.returncode == 0, 'context_applies': forward.returncode == 0,
                          'hardware_accepted': False})
    return {'sdk': 33, 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source_inputs_complete': not errors, 'errors': errors, 'revisions': revisions,
            'sdk32_patch_context_checks': patches, 'sdk33_source_ports': ports,
            'userdata_policy': data_policy, 'runtime_blockers': BLOCKERS,
            'ready_for_boot_image': False, 'ready_for_ota': False, 'hardware_tested': False,
            'battery_improvement_measured': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--top', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = audit(args.top.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for error in report['errors']: print('ERROR:', error)
    for item in report['runtime_blockers']: print('OPEN:', item)
    print('Source audit only; no framework patches applied and no image readiness claimed.')
    print('Report:', args.output)
    return 0 if report['source_inputs_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
