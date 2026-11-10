#!/usr/bin/env python3
"""Read-only SDK33 source audit; successful inventory does not imply bootability."""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile


BLOCKERS = [
    'Rebase complete legacy accounting/BPF compatibility onto SDK33 Connectivity/netd; loader suppression alone is insufficient.',
    'Review/rebase SDK33 RadioConfig and data/PhoneSwitcher behavior for the GM8 legacy data switch.',
    'Review SDK33 Wi-Fi KeyStore/MAC persistence behavior against the current secure-service fix.',
    'Rebase/review processgroup and task-profile behavior for the legacy cgroup-v1 kernel.',
    'Review optional charging-HAL, SystemUI and recents behavior instead of applying SDK32 framework patches blindly.',
    'Review SDK33 userdata fstab/FBE and migration policy; inherited encryptable=footer is not an Android 13 FDE implementation.',
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
        'vendor/gm/GM8_sprout/GM8_sprout-vendor.mk',
        'kernel/gm/msm8937/Makefile',
        'packages/modules/Connectivity/netd/BpfHandler.cpp',
        'packages/modules/Connectivity/service/native/TrafficController.cpp',
        'frameworks/opt/telephony/src/java/com/android/internal/telephony/RadioConfig.java',
        'frameworks/opt/telephony/src/java/com/android/internal/telephony/data/PhoneSwitcher.java',
        'system/core/libprocessgroup/processgroup.cpp',
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
    return {'sdk': 33, 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source_inputs_complete': not errors, 'errors': errors, 'revisions': revisions,
            'sdk32_patch_context_checks': patches, 'runtime_blockers': BLOCKERS,
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
