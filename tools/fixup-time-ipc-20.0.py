#!/usr/bin/env python3
"""Repair reviewed GM8 arm64 time IPC instructions; reject unknown inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile


FIXES = (
    {
        'path': 'vendor/bin/time_daemon',
        'sha256': 'c9865b7cdc62c87c3213e8672fb53bdef204c7afd36c4e5837f87de54dfb631f',
        # Peer address is never used. accept(fd, NULL, NULL) avoids passing
        # the uninitialized socklen_t at fp-0x48 into move_addr_to_user().
        'edits': ((0x3dc4, 'e1430091', 'e1031faa'),
                  (0x3dc8, 'a22301d1', 'e2031faa')),
    },
    {
        'path': 'vendor/lib64/libtime_genoff.so',
        'sha256': '0e19d0e21d5e2b66e1e556ba5aa2b9d914093485eefe33aabf5f284011ef13b0',
        # __sendto_chk(fd, buf, len, buflen, flags, addr, addrlen): w4 is flags.
        # Per-call MSG_NOSIGNAL preserves errno instead of killing the daemon.
        'edits': tuple((offset, 'e4031f2a', '04008852')
                       for offset in (0xa64, 0xba0, 0xc98, 0xf9c, 0x1078)),
    },
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def transform(data, entry):
    """Accept only the complete known original or its exact repaired image."""
    if len(data) < 64 or data[:5] != b'\x7fELF\x02' or data[5] != 1 or data[18:20] != b'\xb7\x00':
        raise ValueError('Expected the reviewed little-endian arm64 ELF: ' + entry['path'])
    original = bytearray(data)
    states = []
    for offset, old_hex, new_hex in entry['edits']:
        old, new = bytes.fromhex(old_hex), bytes.fromhex(new_hex)
        actual = data[offset:offset + len(old)]
        if actual not in (old, new):
            raise ValueError('Unexpected instructions: ' + entry['path'])
        states.append(actual == new)
        original[offset:offset + len(old)] = old
    if any(states) and not all(states):
        raise ValueError('Partially modified time IPC image: ' + entry['path'])
    if digest(original) != entry['sha256']:
        raise ValueError('Unknown time IPC image; no automatic rewrite: ' + entry['path'])
    patched = bytearray(original)
    for offset, old_hex, new_hex in entry['edits']:
        patched[offset:offset + len(bytes.fromhex(old_hex))] = bytes.fromhex(new_hex)
    return bytes(patched), all(states)


def repair(root, check=False):
    root = Path(root)
    plans = []
    # Validate all inputs before changing either file. Reject symlink traversal.
    for entry in FIXES:
        path = root / entry['path']
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Missing or symlinked vendor input: ' + str(path))
        before = path.read_bytes()
        after, already = transform(before, entry)
        if check and not already:
            raise ValueError('Time IPC repair missing: ' + entry['path'])
        plans.append((path, before, after, stat.S_IMODE(path.stat().st_mode), entry))
    report = []
    for path, before, after, mode, entry in plans:
        if before != after and not check:
            fd, temporary = tempfile.mkstemp(prefix='.gm8-time-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as out:
                    out.write(after)
                    out.flush()
                    os.fsync(out.fileno())
                    os.fchmod(out.fileno(), mode)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        report.append({'path': entry['path'], 'input_sha256': digest(before),
                       'output_sha256': digest(after), 'changed': before != after,
                       'instruction_edits': len(entry['edits'])})
    return {'schema': 1, 'files': report,
            'scope': 'reviewed arm64 time daemon and arm64 time_genoff sender only',
            'device_validated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--vendor-root', type=Path)
    parser.add_argument('--target-files', type=Path)
    parser.add_argument('--record', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.target_files:
        if args.vendor_root:
            parser.error('--vendor-root and --target-files are mutually exclusive')
        files = []
        with zipfile.ZipFile(args.target_files) as archive:
            for entry in FIXES:
                member = 'VENDOR/' + entry['path'].removeprefix('vendor/')
                data = archive.read(member)
                after, already = transform(data, entry)
                if not already:
                    raise ValueError('Packaged time IPC image is not repaired: ' + member)
                files.append({'path': member, 'sha256': digest(after)})
        result = {'schema': 1, 'target_files': str(args.target_files), 'files': files,
                  'device_validated': False}
    else:
        root = args.vendor_root or args.top / 'vendor/gm/GM8_sprout/proprietary'
        result = repair(root, args.check)
    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
