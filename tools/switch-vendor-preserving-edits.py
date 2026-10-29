#!/usr/bin/env python3
"""Select a vendor commit while preserving non-overlapping tracked local edits."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def names(repo, *args):
    return set(git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--no-renames',
                   '--name-only', '-z', *args).rstrip(b'\0').split(b'\0')) - {b''}


def snapshot(repo):
    common = ('diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--binary', '--full-index')
    return {
        'working-tree.patch': git(repo, *common, 'HEAD', '--'),
        'index.patch': git(repo, *common, '--cached', 'HEAD', '--'),
    }


def switch(repo, ref, record_dir):
    before = git(repo, 'rev-parse', 'HEAD').decode().strip()
    target = git(repo, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()
    dirty = names(repo, '--') | names(repo, '--cached', '--')
    patches = snapshot(repo)
    if dirty:
        # Save both net working-tree changes and staged changes, including
        # binary data. Never stash, reset, discard, stage or reapply edits.
        record_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        for name, data in patches.items():
            (record_dir / name).write_bytes(data)
        metadata = {'before': before, 'target': target,
                    'paths': sorted(p.decode('utf-8', 'surrogateescape') for p in dirty),
                    'patch_sha256': {n: hashlib.sha256(d).hexdigest() for n, d in patches.items()}}
        (record_dir / 'selection.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print(f'Vendor local-edit backup: {record_dir}', flush=True)
        overlaps = dirty & names(repo, before, target, '--')
        if overlaps:
            paths = '\n'.join('  ' + p.decode('utf-8', 'replace') for p in sorted(overlaps))
            raise ValueError('Vendor edits overlap files changed by the candidate; '
                             'no checkout performed. Review these paths:\n' + paths)
    # Native git switch also protects untracked collisions. No force option.
    subprocess.run(['git', '-C', str(repo), 'switch', '--detach', target], check=True)
    if snapshot(repo) != patches:
        raise ValueError('Vendor diff changed unexpectedly during selection; '
                         f'build stopped. Inspect the backup at {record_dir}')
    if dirty:
        print(f'Preserved vendor tracked edits ({len(dirty)} paths), including index state.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--record-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        switch(args.repo.resolve(), args.ref, args.record_dir.resolve())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
