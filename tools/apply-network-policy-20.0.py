#!/usr/bin/env python3
"""Apply the paired SDK33 Java routing and legacy bandwidth ports, preserving local work."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--top', type=Path, default=Path(__file__).resolve().parents[4])
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    top = args.top.resolve()
    version = top / 'build/core/version_defaults.mk'
    if not version.is_file() or not re.search(r'^\s*PLATFORM_SDK_VERSION\s*:?=\s*33\s*$', version.read_text(), re.M):
        print('Expected Android 13 / SDK33; no files changed.', file=sys.stderr)
        return 1
    device = Path(__file__).resolve().parents[1]

    def apply(project, patch, *flags, patch_text=None):
        return subprocess.run(['git', 'apply', *flags, '-' if patch_text is not None else str(patch)],
                              input=patch_text, cwd=top / project,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def applied_with_permission_route(project, patch):
        if project != 'packages/modules/Connectivity': return False
        successor = patch.parent / '0003-gm8-legacy-permission-routing.patch'
        if not successor.is_file() or apply(project, successor, '--reverse', '--check').returncode:
            return False
        # Verify the predecessor on an isolated copy. Never undo the successor
        # in the user's checkout, including during a check-only build.
        with tempfile.TemporaryDirectory(prefix='gm8-policy-check-') as directory:
            stage = Path(directory)
            relative = Path('service/src/com/android/server/BpfNetMaps.java')
            target = stage / relative
            target.parent.mkdir(parents=True)
            shutil.copyfile(top / project / relative, target)
            result = subprocess.run(['git', 'apply', '--reverse', str(successor)],
                                    cwd=stage, capture_output=True)
            if result.returncode: return False
            return subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)],
                                  cwd=stage, capture_output=True).returncode == 0

    prerequisite = device / 'patches/sdk33/system_netd/0001-gm8-legacy-uid-firewall.patch'
    if not (top / 'system/netd').is_dir() or not prerequisite.is_file() or apply(
            'system/netd', prerequisite, '--reverse', '--check').returncode != 0:
        print('Apply/check the reviewed SDK33 UID-firewall prerequisite first; no files changed.', file=sys.stderr)
        return 1
    pending = []
    for project, name in (
            ('system/netd', 'system_netd/0002-gm8-legacy-bandwidth-policy.patch'),
            ('packages/modules/Connectivity', 'Connectivity/0002-gm8-legacy-network-policy-routing.patch')):
        patch = device / 'patches/sdk33' / name
        if not (top / project).is_dir() or not patch.is_file():
            print('Missing source or patch: ' + project, file=sys.stderr)
            return 1
        if apply(project, patch, '--reverse', '--check').returncode == 0: continue
        if applied_with_permission_route(project, patch): continue
        result = apply(project, patch, '--check')
        if result.returncode:
            if project == 'packages/modules/Connectivity':
                # Recognize the exact earlier reviewed patch, then use a narrow
                # upgrade instead of reverting the user's whole source tree.
                previous = patch.read_text().replace('EIO', 'EREMOTEIO')
                upgrade = patch.parent / 'upgrades/0001-gm8-java-public-errno.patch'
                if (upgrade.is_file() and apply(project, patch, '--reverse', '--check',
                        patch_text=previous).returncode == 0
                        and apply(project, upgrade, '--check').returncode == 0):
                    pending.append((project, upgrade))
                    continue
            print(project + ' differs; no files changed.\n' + result.stderr, file=sys.stderr)
            return 1
        pending.append((project, patch))
    if args.check and pending:
        print('SDK33 paired network-policy ports are not fully applied.', file=sys.stderr)
        return 1
    completed = []
    for project, patch in pending:
        result = apply(project, patch)
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            for old_project, old_patch in reversed(completed):
                rolled = apply(old_project, old_patch, '--reverse')
                if rolled.returncode: print('Rollback failed: ' + rolled.stderr, file=sys.stderr)
            return 1
        completed.append((project, patch))
    print('SDK33 Java UID/bandwidth routing and native legacy bandwidth policy are applied.')
    print('Complete socket/accounting acceptance, VPN/CLAT and BPF startup remain open.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
