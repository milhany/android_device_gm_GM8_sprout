#!/usr/bin/env python3
"""Real sign-file regression with a poisoned legacy Perl environment."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--kernel', type=Path,
                    default=Path(__file__).resolve().parents[5] / 'kernel/gm/msm8937')
args = parser.parse_args()
kernel = args.kernel.resolve()
source = (kernel / 'Makefile').read_text()
command = re.search(r'^mod_sign_cmd = .*scripts/sign-file.*$', source, re.M).group()
assert command.startswith('mod_sign_cmd = $(PERL) '), command


def run(argv, **kwargs):
    return subprocess.run([str(a) for a in argv], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


with tempfile.TemporaryDirectory(prefix='gm8-perl-test-') as temporary:
    root = Path(temporary)
    shim = root / 'bin'
    shim.mkdir()
    fake = shim / 'perl'
    fake.write_text('#!/bin/sh\necho legacy-Perl-selected >&2\nexit 86\n')
    fake.chmod(0o755)
    poison = root / 'old-perl-lib/Getopt'
    poison.mkdir(parents=True)
    (poison / 'Std.pm').write_text('die "incompatible legacy PERL5LIB loaded";\n')
    env = dict(os.environ, PATH=str(shim) + os.pathsep + os.environ['PATH'],
               PERL5LIB=str(poison.parent))
    private = root / 'signing_key.pem'
    cert = root / 'signing_key.x509'
    public = root / 'public.pem'
    run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-x509', '-sha256',
         '-days', '1', '-subj', '/CN=GM8 module signing fixture',
         '-addext', 'subjectKeyIdentifier=hash', '-keyout', private,
         '-outform', 'DER', '-out', cert])
    public.write_bytes(run(['openssl', 'pkey', '-in', private, '-pubout']).stdout)
    module = root / 'fixture.ko'
    original = b'Synthetic module content for host signature verification\n'
    module.write_bytes(original)
    makefile = root / 'Makefile'
    prelude = ('PERL = /usr/bin/env -u PERL5LIB /usr/bin/perl\n'
               f'srctree = {kernel}\nCONFIG_MODULE_SIG_HASH = sha256\n'
               f'MODSECKEY = {private}\nMODPUBKEY = {cert}\n')
    recipe = f'\n.PHONY: sign\nsign:\n\t$(mod_sign_cmd) {module}\n'
    # The old line demonstrably ignores PERL and selects the broken binary.
    makefile.write_text(prelude + command.replace('$(PERL)', 'perl', 1) + recipe)
    old = subprocess.run(['make', '-f', str(makefile), 'sign'], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert old.returncode != 0 and b'legacy-Perl-selected' in old.stderr
    assert module.read_bytes() == original
    makefile.write_text(prelude + command + recipe)
    run(['make', '-f', makefile, 'sign'], env=env)
    data = module.read_bytes()
    magic = b'~Module signature appended~\n'
    assert data.startswith(original) and data.endswith(magic)
    footer = len(data) - len(magic) - 12
    algo, digest, identity, name_len, key_len, sig_len = struct.unpack(
        '!BBBBB3xI', data[footer:footer + 12])
    assert (algo, digest, identity) == (1, 4, 1)
    signature = data[len(original) + name_len + key_len:footer]
    assert len(signature) == sig_len
    assert struct.unpack('!H', signature[:2])[0] == len(signature) - 2
    sig = root / 'signature.bin'
    sig.write_bytes(signature[2:])
    recovered = run(['openssl', 'pkeyutl', '-verifyrecover', '-pubin',
                     '-inkey', public, '-in', sig]).stdout
    sha256_prefix = bytes.fromhex('3031300d060960864801650304020105000420')
    assert recovered == sha256_prefix + hashlib.sha256(original).digest()

print('PASS: old command selects legacy Perl; fixed command signs through system '
      'Perl despite poisoned PATH/PERL5LIB; appended RSA/SHA-256 signature verified')
