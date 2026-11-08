#!/usr/bin/env python3
"""Select the paired candidate, backing up only recognized local candidate edits."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def revision_blob(repo, revision, path):
    r = git(repo, 'rev-parse', '--verify', revision + ':' + path, check=False)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    parser.add_argument('--device-ref', required=True, help='full SHA fetched with this script')
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r'[0-9a-f]{40}', args.device_ref):
            raise ValueError('--device-ref must be a full commit SHA')
        top = args.top.resolve(strict=True)
        version = (top / 'build/core/version_defaults.mk').read_text()
        if not re.search(r'^\s*PLATFORM_SDK_VERSION\s*:?=\s*29\s*$', version, re.M):
            raise ValueError('Expected the separate Android 10 / SDK29 checkout')
        manifest = json.loads(args.manifest.read_text())
        plans = []
        for entry in manifest['repositories']:
            repo = top / entry['checkout']
            real = git(repo, 'rev-parse', '--show-toplevel').stdout.decode().strip()
            if Path(real).resolve() != repo.resolve():
                raise ValueError('Expected a separate Git checkout: ' + str(repo))
            target = args.device_ref if entry['kind'] == 'device' else entry['target']
            if not re.fullmatch(r'[0-9a-f]{40}', target):
                raise ValueError('Invalid pinned target')
            git(repo, 'fetch', '--no-tags', entry['url'], target)
            git(repo, 'merge-base', '--is-ancestor', entry['base'], target)
            if git(repo, 'merge-base', '--is-ancestor', 'HEAD', target, check=False).returncode:
                raise ValueError('Local commits outside the candidate preserved: ' + str(repo))
            if git(repo, 'diff', '--cached', '--diff-filter=D', '--name-only').stdout:
                raise ValueError('Staged deletions preserved: ' + str(repo))
            dirty = set(git(repo, 'diff', '--no-renames', '--name-only', '-z', 'HEAD').stdout.decode().split('\0'))
            dirty.update(git(repo, 'diff', '--cached', '--no-renames', '--name-only', '-z').stdout.decode().split('\0'))
            untracked = git(repo, 'ls-files', '--others', '--exclude-standard', '-z').stdout.decode().split('\0')
            for path in untracked:
                if path and revision_blob(repo, target, path):
                    dirty.add(path)
            dirty.discard('')
            for path in sorted(dirty):
                f = repo / path
                if f.is_symlink() or not f.is_file():
                    raise ValueError('Deleted/nonregular local file preserved: ' + str(f))
                accepted = set(entry['known_local_blobs'].get(path, []))
                accepted.update([revision_blob(repo, entry['base'], path),
                                 revision_blob(repo, target, path)])
                accepted.discard(None)
                if blob(f.read_bytes()) not in accepted:
                    raise ValueError('Unknown local work preserved; review before switching: ' + str(f))
                index_blob = revision_blob(repo, '', path)
                if index_blob is not None and index_blob not in accepted:
                    raise ValueError('Unknown staged work preserved: ' + str(f))
            plans.append((repo, target, sorted(dirty)))
        # Check every tree before changing a worktree. Fetching above only
        # obtains Git objects and does not switch, reset or publish local work.
        for repo, target, paths in plans:
            if paths:
                git(repo, 'stash', 'push', '--include-untracked', '-m',
                    'gm8-before-stability-20261108', '--', *paths)
                saved = git(repo, 'rev-parse', 'refs/stash').stdout.decode().strip()
                print('Saved recognized local candidate edits:', repo, saved, flush=True)
        for repo, target, paths in plans:
            git(repo, 'switch', '--detach', target)
            actual = git(repo, 'rev-parse', 'HEAD').stdout.decode().strip()
            if actual != target:
                raise ValueError('Unexpected selected revision: ' + str(repo))
            print('Selected:', repo, actual, flush=True)
        print('Paired sources ready. Local backups are not popped: their reviewed changes are in the selected candidate.')
        print('No reset, forced checkout, key changes, build or device writes performed.')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        detail = getattr(error, 'stderr', b'') or b''
        parser.exit(1, 'Selection stopped; preserve any printed stash backups.\n' +
                    str(error) + '\n' + detail.decode(errors='replace'))


if __name__ == '__main__':
    main()
