#!/usr/bin/env python3
"""Prepare the entire SDK33 patch stack in isolation before touching any source."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(work, args):
    return subprocess.run(['git', '-C', str(work), 'apply', *args], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def safe(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe path: ' + relative)
    out = root.joinpath(*path.parts)
    # Do not follow symlinks for either inputs or destinations.
    cursor = out
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('Symlink in source path: ' + str(cursor))
        cursor = cursor.parent
    if out.exists() and not out.is_file():
        raise ValueError('Not a regular source file: ' + str(out))
    return out


def patch_paths(patch):
    text = patch.read_text()
    pairs = re.findall(r'^diff --git a/(\S+) b/(\S+)$', text, re.M)
    if not pairs or any(a != b for a, b in pairs):
        raise ValueError('Only explicit, non-rename source patches supported: ' + str(patch))
    if any(token in text for token in ('GIT binary patch', 'old mode ', 'deleted file mode', 'new file mode 120000')):
        raise ValueError('Unsupported patch operation: ' + str(patch))
    return {a for a, _ in pairs}


def prepare(top, temporary, config):
    changes = []
    audit = []
    for number, item in enumerate(config['projects']):
        relative = item['path']
        # Validate project paths independently of the files below them.
        pure = PurePosixPath(relative)
        if pure.is_absolute() or '..' in pure.parts:
            raise ValueError('Unsafe project path')
        project = top.joinpath(*pure.parts)
        if not project.is_dir():
            raise ValueError('Missing project: ' + relative)
        # Android repo project roots themselves may be bind mounts, not symlinks.
        if project.is_symlink():
            raise ValueError('Project root must not be a symlink: ' + relative)
        patches = [safe(ROOT, name) for name in item['patches']]
        paths = set().union(*(patch_paths(patch) for patch in patches))
        work = temporary / str(number)
        work.mkdir()
        subprocess.run(['git', 'init', '-q', str(work)], check=True)
        original = {}
        modes = {}
        for name in sorted(paths):
            source, destination = safe(project, name), safe(work, name)
            original[name] = source.read_bytes() if source.exists() else None
            modes[name] = stat.S_IMODE(source.stat().st_mode) if source.exists() else 0o644
            if source.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(original[name])
        # Peel a fully applied suffix first. This supports pristine inputs,
        # any published prefix, and a complete repeat without guessing hunks.
        for patch in reversed(patches):
            if run(work, ['--reverse', '--check', str(patch)]).returncode == 0:
                result = run(work, ['--reverse', str(patch)])
                if result.returncode: raise ValueError(result.stderr)
        for patch in patches:
            result = run(work, ['--check', str(patch)])
            if result.returncode:
                raise ValueError(f'Conflict in {relative}: {patch.name}\n{result.stderr}')
            result = run(work, [str(patch)])
            if result.returncode: raise ValueError(result.stderr)
        hashes = {}
        for name in sorted(paths):
            destination = safe(work, name)
            final = destination.read_bytes() if destination.exists() else None
            if final is None:
                raise ValueError('Unexpected deleted source: ' + relative + '/' + name)
            hashes[name] = hashlib.sha256(final).hexdigest()
            if final != original[name]:
                changes.append((safe(project, name), original[name], final, modes[name]))
        audit.append({'project': relative, 'files_sha256': hashes,
                      'patches': [{'path': str(p.relative_to(ROOT)),
                                   'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in patches]})
    return changes, audit


def replace(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.gm8-source-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def apply_changes(changes):
    completed = []
    try:
        # Detect edits since preparation before the first mutation.
        for path, old, new, mode in changes:
            actual = path.read_bytes() if path.exists() else None
            if actual != old or path.is_symlink():
                raise ValueError('Source changed during preparation: ' + str(path))
        for path, old, new, mode in changes:
            replace(path, new, mode)
            completed.append((path, old, new, mode))
    except BaseException:
        failed = []
        for path, old, new, mode in reversed(completed):
            try:
                if path.read_bytes() != new:
                    raise ValueError('Concurrent edit; refusing to overwrite')
                if old is None: path.unlink()
                else: replace(path, old, mode)
            except Exception as error:
                failed.append(f'{path}: {error}')
        if failed:
            raise RuntimeError('Rollback incomplete; preserve this tree and inspect: ' + '; '.join(failed))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--record', type=Path)
    args = parser.parse_args()
    if args.record and args.record.exists(): raise ValueError('Record already exists')
    top = args.top.resolve()
    version = top / 'build/core/version_defaults.mk'
    if not version.is_file() or not re.search(r'^\s*PLATFORM_SDK_VERSION\s*:?=\s*33\s*$', version.read_text(), re.M):
        raise ValueError('Expected SDK33 checkout')
    config = json.loads((ROOT / 'tools/runtime-stack-20.0.json').read_text())
    with tempfile.TemporaryDirectory(prefix='gm8-runtime-stack-') as tmp:
        changes, audit = prepare(top, Path(tmp), config)
        if args.check and changes:
            raise ValueError(f'Runtime stack is not fully applied ({len(changes)} source files differ)')
        if not args.check: apply_changes(changes)
    if args.record:
        if args.record.exists(): raise ValueError('Record already exists')
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps({'sdk': 33, 'source_stack_applied': True,
            'android_build_passed': False, 'hardware_tested': False, 'projects': audit}, indent=2)+'\n')
    print(f'SDK33 runtime stack verified; {len(changes)} files updated. Hardware acceptance is pending.')


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit('ERROR: ' + str(error))
