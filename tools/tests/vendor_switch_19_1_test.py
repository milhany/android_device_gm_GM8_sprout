#!/usr/bin/env python3
"""Exercise the real vendor selector with local Git commits and binary edits."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

helper = Path(__file__).resolve().parents[1] / 'switch-vendor-preserving-edits.py'
spec = importlib.util.spec_from_file_location('selector', helper)
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)


with tempfile.TemporaryDirectory(prefix='gm8-vendor-switch-') as directory:
    root = Path(directory)
    repo = root / 'repo'
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.name', 'Fixture')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    blob = repo / 'blob.so'
    startup = repo / 'post_boot.sh'
    blob.write_bytes(b'ELF fixture\0stock dependency')
    startup.write_text('baseline\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'base')
    base = git(repo, 'rev-parse', 'HEAD').decode().strip()
    startup.write_text('paired userspace LMKD\n')
    (repo / 'new-file').write_text('candidate file\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'candidate')
    target = git(repo, 'rev-parse', 'HEAD').decode().strip()
    git(repo, 'switch', '--detach', base)

    # Both staged and additional unstaged binary changes survive selection.
    staged = b'ELF fixture\0v29 dependency'
    working = staged + b'\0unstaged bytes'
    blob.write_bytes(staged)
    git(repo, 'add', 'blob.so')
    blob.write_bytes(working)
    untracked = repo / 'user-notes'
    untracked.write_text('keep me')
    before = selector.snapshot(repo)
    record = root / 'backup'
    selector.switch(repo, target, record)
    assert git(repo, 'rev-parse', 'HEAD').decode().strip() == target
    assert blob.read_bytes() == working and git(repo, 'show', ':blob.so') == staged
    assert selector.snapshot(repo) == before
    assert untracked.read_text() == 'keep me'
    assert record.stat().st_mode & 0o777 == 0o700
    assert all((record / name).read_bytes() == data for name, data in before.items())
    assert json.loads((record / 'selection.json').read_text())['paths'] == ['blob.so']

    # Repeating against the same commit also preserves the diffs.
    selector.switch(repo, target, root / 'second-backup')
    assert selector.snapshot(repo) == before

    # An edited startup script overlaps the incoming candidate: no checkout.
    git(repo, 'switch', '--detach', base)
    startup.write_text('user startup edits\n')
    conflicted = selector.snapshot(repo)
    try:
        selector.switch(repo, target, root / 'conflict-backup')
    except ValueError as error:
        assert 'post_boot.sh' in str(error) and 'overlap' in str(error)
    else:
        raise AssertionError('Accepted overlapping vendor changes')
    assert git(repo, 'rev-parse', 'HEAD').decode().strip() == base
    assert selector.snapshot(repo) == conflicted
    startup.write_text('baseline\n')

    # Native Git refuses an untracked path the incoming commit would replace.
    collision = repo / 'new-file'
    collision.write_text('untracked work\n')
    try:
        selector.switch(repo, target, root / 'untracked-backup')
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError('Overwrote an untracked file')
    assert collision.read_text() == 'untracked work\n'
    assert blob.read_bytes() == working and git(repo, 'show', ':blob.so') == staged
    collision.unlink()

    # Clean selection still succeeds and needs no local-edit backup.
    blob.write_bytes(b'ELF fixture\0stock dependency')
    git(repo, 'add', 'blob.so')
    selector.switch(repo, target, root / 'clean-backup')
    assert not (root / 'clean-backup').exists()
    assert not selector.names(repo, '--') and not selector.names(repo, '--cached', '--')

print('PASS: real Git preserves binary working/index edits, backups and repeated selection; '
      'overlapping edits/untracked collisions stop without data loss; clean selection works')
