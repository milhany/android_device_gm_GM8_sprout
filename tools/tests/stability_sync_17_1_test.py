#!/usr/bin/env python3
"""Exercise the real selector on temporary Git repositories without a network."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

script = Path(__file__).resolve().parents[1] / 'sync-stability-17.1.py'
env = dict(os.environ, GIT_AUTHOR_NAME='GM8 test', GIT_COMMITTER_NAME='GM8 test',
           GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_EMAIL='test@example.invalid')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], env=env,
                                   stderr=subprocess.STDOUT, text=True).strip()


def sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def scenario(kind):
    with tempfile.TemporaryDirectory(prefix='gm8-source-sync-') as temp:
        top = Path(temp)
        version = top / 'build/core/version_defaults.mk'
        version.parent.mkdir(parents=True)
        version.write_text('PLATFORM_SDK_VERSION := 29\n')
        entries = []
        snapshots = []
        device = None
        for name in ('device', 'vendor', 'kernel'):
            repo = top / name
            repo.mkdir()
            git(repo, 'init', '-q')
            git(repo, 'config', 'user.name', 'GM8 test')
            git(repo, 'config', 'user.email', 'test@example.invalid')
            f = repo / 'source.c'
            f.write_text('base\n')
            git(repo, 'add', '.'); git(repo, 'commit', '-qm', 'base')
            base = git(repo, 'rev-parse', 'HEAD')
            f.write_text('candidate\n')
            (repo / 'new-test.py').write_text('candidate test\n')
            git(repo, 'add', '.'); git(repo, 'commit', '-qm', 'candidate')
            target = git(repo, 'rev-parse', 'HEAD')
            git(repo, 'switch', '--detach', base)
            (repo / 'unrelated-notes.txt').write_text('keep private notes\n')
            if kind != 'clean':
                f.write_text('candidate\n')
                (repo / 'new-test.py').write_text('candidate test\n')
            if name == 'kernel':
                if kind == 'unknown': f.write_text('unreviewed edit\n')
                if kind == 'staged-delete': git(repo, 'rm', '--cached', 'source.c')
                if kind == 'local-commit':
                    git(repo, 'add', 'source.c'); git(repo, 'commit', '-qm', 'private commit')
                if kind == 'symlink':
                    f.unlink(); f.symlink_to(repo / 'unrelated-notes.txt')
            entries.append(dict(kind=name, checkout=name, url=str(repo), base=base,
                                target=target, known_local_blobs={}))
            snapshots.append((repo, git(repo, 'rev-parse', 'HEAD'), f.read_bytes(),
                              git(repo, 'status', '--porcelain')))
            if name == 'device': device = target
        manifest = top / 'manifest.json'
        manifest.write_text(json.dumps({'repositories': entries}))
        r = subprocess.run(['python3', str(script), '--top', str(top),
                            '--manifest', str(manifest), '--device-ref', device],
                           env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        okay = kind in ('clean', 'preapplied')
        assert (r.returncode == 0) == okay, r.stdout
        for entry, (repo, oldhead, olddata, oldstatus) in zip(entries, snapshots):
            assert (repo / 'unrelated-notes.txt').read_text() == 'keep private notes\n'
            if okay:
                assert git(repo, 'rev-parse', 'HEAD') == entry['target']
                assert (repo / 'source.c').read_text() == 'candidate\n'
                if kind == 'preapplied':
                    saved = git(repo, 'rev-parse', 'refs/stash')
                    assert git(repo, 'show', saved + ':source.c') == 'candidate'
            else:
                assert git(repo, 'rev-parse', 'HEAD') == oldhead
                assert (repo / 'source.c').read_bytes() == olddata
                assert git(repo, 'status', '--porcelain') == oldstatus
                no_stash = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', 'refs/stash'], capture_output=True)
                assert no_stash.returncode
        print('PASS:', kind, '— paired selection or all worktrees preserved')


for case in ('clean', 'preapplied', 'unknown', 'staged-delete', 'local-commit', 'symlink'):
    scenario(case)
