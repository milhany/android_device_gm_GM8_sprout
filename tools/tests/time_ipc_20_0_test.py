#!/usr/bin/env python3
"""Test reviewed ELF inputs, the real kernel address-copy body, and IPC SIGPIPE."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('time_fix', TOOLS / 'fixup-time-ipc-20.0.py')
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)

SOCKET_TEST = r'''
#include <assert.h>
#include <errno.h>
#include <signal.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>
/* Verbatim move_addr_to_user body from the paired GM8 kernel net/socket.c,
 * with host user-access/audit shims. A live accept syscall is not emulated. */
#define __user
#define BUG_ON(v) assert(!(v))
#define get_user(v, p) ((v) = *(p), 0)
#define __put_user(v, p) (*(p) = (v), 0)
#define audit_sockaddr(n, p) ((void)(n), (void)(p), 0)
#define copy_to_user(dst, src, n) (memcpy((dst), (src), (n)), 0)
static int move_addr_to_user(struct sockaddr_storage *kaddr, int klen,
                             void __user *uaddr, int __user *ulen)
{
    int err;
    int len;
    BUG_ON(klen > sizeof(struct sockaddr_storage));
    err = get_user(len, ulen);
    if (err)
        return err;
    if (len > klen)
        len = klen;
    if (len < 0)
        return -EINVAL;
    if (len) {
        if (audit_sockaddr(klen, kaddr))
            return -ENOMEM;
        if (copy_to_user(uaddr, kaddr, len))
            return -EFAULT;
    }
    return __put_user(klen, ulen);
}
int main(void) {
    struct sockaddr_storage peer = {0}, source = {0};
    int invalid = -1, valid = sizeof(peer), pair[2];
    char request[32] = {0}, received[32];
    int client, accepted, status;
    pid_t child;
    assert(move_addr_to_user(&source, 2, &peer, &invalid) == -EINVAL);
    assert(move_addr_to_user(&source, 2, &peer, &valid) == 0 && valid == 2);
    assert(socketpair(AF_UNIX, SOCK_STREAM, 0, pair) == 0);
    client = pair[0]; close(pair[1]); /* Model the rejected accepted endpoint. */
    child = fork(); assert(child >= 0);
    if (!child) {
        signal(SIGPIPE, SIG_DFL);
        (void)send(client, request, sizeof(request), 0);
        (void)send(client, request, sizeof(request), 0);
        _exit(99);
    }
    assert(waitpid(child, &status, 0) == child);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGPIPE);
    close(client);
    assert(socketpair(AF_UNIX, SOCK_STREAM, 0, pair) == 0);
    client = pair[0]; accepted = pair[1];
    assert(send(client, request, sizeof(request), MSG_NOSIGNAL) == sizeof(request));
    assert(recv(accepted, received, sizeof(received), MSG_WAITALL) == sizeof(received));
    assert(memcmp(request, received, sizeof(request)) == 0);
    close(accepted);
    errno = 0;
    assert(send(client, request, sizeof(request), MSG_NOSIGNAL) == -1);
    assert(errno == EPIPE || errno == ECONNRESET);
    close(client);
    puts("PASS: actual kernel address-copy rejects negative length; real IPC reproduces SIGPIPE; NOSIGNAL preserves roundtrip/error return");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor-root', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='gm8-time-ipc-test-') as temp:
        temp = Path(temp)
        vendor = temp / 'vendor-inputs'
        for entry in fix.FIXES:
            dst = vendor / entry['path']
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.vendor_root / entry['path'], dst)
        result = fix.repair(vendor)
        outputs = {entry['path']: (vendor / entry['path']).read_bytes() for entry in fix.FIXES}
        fix.repair(vendor, check=True)
        again = fix.repair(vendor)
        assert not any(item['changed'] for item in again['files'])
        for entry in fix.FIXES:
            original = bytearray(outputs[entry['path']])
            for offset, old, new in entry['edits']:
                assert original[offset:offset + 4] == bytes.fromhex(new)
                original[offset:offset + 4] = bytes.fromhex(old)
            assert fix.digest(original) == entry['sha256']
        packaged = temp / 'target-files.zip'
        with zipfile.ZipFile(packaged, 'w') as archive:
            for entry in fix.FIXES:
                archive.writestr('VENDOR/' + entry['path'].removeprefix('vendor/'), outputs[entry['path']])
        subprocess.run(['python3', str(TOOLS / 'fixup-time-ipc-20.0.py'),
                        '--target-files', str(packaged), '--check'],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Unknown second input must refuse before rewriting a pristine first file.
        for entry in fix.FIXES:
            original = bytearray(outputs[entry['path']])
            for offset, old, new in entry['edits']:
                original[offset:offset + 4] = bytes.fromhex(old)
            (vendor / entry['path']).write_bytes(original)
        first, second = (vendor / e['path'] for e in fix.FIXES)
        before_first = first.read_bytes()
        with zipfile.ZipFile(packaged, 'w') as archive:
            for entry in fix.FIXES:
                archive.writestr('VENDOR/' + entry['path'].removeprefix('vendor/'),
                                 (vendor / entry['path']).read_bytes())
        before_zip = packaged.read_bytes()
        rejected = subprocess.run(['python3', str(TOOLS / 'fixup-time-ipc-20.0.py'),
                                   '--target-files', str(packaged), '--check'],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert rejected.returncode != 0 and packaged.read_bytes() == before_zip
        corrupt = bytearray(second.read_bytes()); corrupt[-1] ^= 1; second.write_bytes(corrupt)
        try:
            fix.repair(vendor)
            raise AssertionError('Unknown binary accepted')
        except ValueError:
            pass
        assert first.read_bytes() == before_first
        script = (temp / 'sockets.c'); script.write_text(SOCKET_TEST)
        binary = temp / 'sockets'
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
                        str(script), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=10)
        print('PASS: reviewed ELF instruction edits, idempotence, full-image identity, packaged-byte checks and pre-mutation rejection')
        for item in result['files']:
            print(item['path'], item['output_sha256'])


if __name__ == '__main__':
    main()
