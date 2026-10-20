#!/usr/bin/env python3
"""Prepare private keys and sign/verify an existing GM8 user target-files ZIP.

Prepares a clean-install release requiring a manual Format Data. Never flashes,
edits packages.xml, disables signature checks or generates an automatic wipe OTA.
"""
import argparse
import contextlib
import getpass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import struct
import subprocess
import tempfile
import zipfile

SPECIAL = {'PRESIGNED', 'EXTERNAL'}
ROLES = {'testkey': 'releasekey', 'devkey': 'releasekey', 'platform': 'platform',
         'shared': 'shared', 'media': 'media', 'networkstack': 'networkstack'}


def run(args, data=None):
    return subprocess.run([str(a) for a in args], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def props(text):
    return dict(line.split('=', 1) for line in text.splitlines()
                if '=' in line and not line.startswith('#'))


def text(z, name):
    if z.getinfo(name).file_size > 2 * 1024 * 1024:
        raise ValueError(f'Metadata too large: {name}')
    return z.read(name).decode()


def records(value):
    result = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        row = dict(item.split('=', 1) for item in shlex.split(line))
        name = row['name']
        if name in result:
            # apkcerts includes identical module names for different variants.
            old = result[name]
            if any(row.get(k) != old.get(k) for k in row if k != 'partition'):
                raise ValueError(f'Conflicting certificate metadata: {name}')
        result[name] = row
    return result


def cert_der(path):
    return run(['openssl', 'x509', '-in', path, '-outform', 'DER'])


def cert_pub(path):
    pem = run(['openssl', 'x509', '-in', path, '-pubkey', '-noout'])
    return run(['openssl', 'pkey', '-pubin', '-outform', 'DER'], pem)


def private_directory(path, top):
    path = Path(path).expanduser().resolve()
    if path == top or top in path.parents:
        raise ValueError('Private keys must be outside the Android source checkout')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError(f'Key directory must be owned by you with mode 0700: {path}')
    return path


def source_certificate(top, name):
    path = (top / name).resolve()
    if top not in path.parents or not path.is_file():
        raise ValueError(f'Missing source public certificate: {name}')
    return path


def host_tools(top):
    host = top / 'out/host/linux-x86'
    for name in ('deapexer', 'debugfs_static', 'sign_target_files_apks',
                 'ota_from_target_files', 'avbtool', 'apksigner'):
        if not (host / 'bin' / name).is_file():
            raise ValueError(f'Missing {host / "bin" / name}; run m otatools first')
    os.environ['PATH'] = str(host / 'bin') + os.pathsep + os.environ['PATH']
    jdk = top / 'prebuilts/jdk/jdk11/linux-x86/bin'
    if (jdk / 'java').exists():
        os.environ['PATH'] = str(jdk) + os.pathsep + os.environ['PATH']
    return host


def copy_entry(z, name, dest):
    with z.open(name) as source, Path(dest).open('wb') as output:
        shutil.copyfileobj(source, output)


@contextlib.contextmanager
def apex_files(z, entry, host):
    with tempfile.TemporaryDirectory(prefix='gm8-release-apex-') as temporary:
        directory = Path(temporary)
        outer = directory / Path(entry).name
        copy_entry(z, entry, outer)
        apex = outer
        if entry.endswith('.capex'):
            apex = directory / 'original.apex'
            with zipfile.ZipFile(outer) as capex:
                copy_entry(capex, 'original_apex', apex)
        payload = directory / 'contents'
        run([host / 'bin/deapexer', '--debugfs_path', host / 'bin/debugfs_static',
             'extract', apex, payload])
        yield outer, apex, payload


def archive_metadata(z):
    if len(z.namelist()) != len(set(z.namelist())):
        raise ValueError('Duplicate target-files ZIP entries')
    build = props(text(z, 'SYSTEM/build.prop'))
    if (build.get('ro.build.version.sdk') != '32' or build.get('ro.build.type') != 'user'
            or build.get('ro.build.product') != 'GM8_sprout'):
        raise ValueError('Expected GM8_sprout Android SDK 32 user target files')
    misc = props(text(z, 'META/misc_info.txt'))
    if misc.get('ab_update') != 'true':
        raise ValueError('Expected an A/B OTA device')
    if misc.get('avb_enable') == 'true' or misc.get('verity') == 'true':
        raise ValueError('Partition AVB/verity signing needs an explicit additional key plan')
    return misc, records(text(z, 'META/apkcerts.txt')), records(text(z, 'META/apexkeys.txt'))


def inventory(top, target, keys, host):
    with zipfile.ZipFile(target) as z:
        misc, apk_meta, apex_meta = archive_metadata(z)
        dev = misc['default_system_dev_certificate']
        devdir = str(Path(dev).parent)
        certificates, identities, apks, apexes, payloads = {}, {}, [], [], {}

        def certificate(name):
            if name in SPECIAL:
                if name == 'EXTERNAL':
                    raise ValueError('EXTERNAL component requires explicit signing review')
                return None
            if name in certificates:
                return certificates[name]['key']
            old = source_certificate(top, name)
            der = cert_der(old)
            identity = hashlib.sha256(der).hexdigest()
            stem = str(Path(name).name).removesuffix('.x509.pem')
            role = ROLES.get(stem) if str(Path(name).parent) == devdir else None
            key = identities.setdefault(identity, str(keys / (role or 'certs/' + identity)))
            certificates[name] = {'key': key, 'old_sha256': identity}
            return key

        # Register standard roles first, keeping cert aliases mapped identically.
        for role in ('testkey', 'platform', 'shared', 'media', 'networkstack'):
            source = f'{devdir}/{role}.x509.pem'
            if (top / source).is_file():
                certificate(source)
        ota_key = certificate(dev + '.x509.pem')
        for name in text(z, 'META/otakeys.txt').split():
            certificate(name)

        def add_apk(entry, name, content_hash, inside=None):
            row = apk_meta.get(name)
            if row is None:
                raise ValueError(f'No APK key metadata for {name}')
            key = certificate(row['certificate'])
            apks.append({'entry': entry, 'name': name, 'inside': inside,
                         'key': key, 'original_sha256': content_hash})

        for entry in z.namelist():
            if entry.endswith(('.apk', '.apk.gz')):
                name = Path(entry).name.removesuffix('.gz')
                # Hash only PRESIGNED APKs; other signatures will be verified anew.
                h = hashlib.sha256(z.read(entry)).hexdigest() if apk_meta[name]['certificate'] == 'PRESIGNED' else None
                add_apk(entry, name, h)
            elif entry.endswith(('.apex', '.capex')):
                name = Path(entry).name.removesuffix('.capex').removesuffix('.apex') + '.apex'
                row = apex_meta[name]
                container = certificate(row['container_certificate'])
                if row['public_key'] == 'PRESIGNED' or row['private_key'] == 'PRESIGNED':
                    if container is not None:
                        raise ValueError(f'Only one APEX key is PRESIGNED: {name}')
                    apexes.append({'entry': entry, 'name': name, 'key': None,
                                   'original_sha256': hashlib.sha256(z.read(entry)).hexdigest()})
                    continue
                if container is None:
                    raise ValueError(f'Only one APEX key is PRESIGNED: {name}')
                with apex_files(z, entry, host) as (_, apex, payload):
                    with zipfile.ZipFile(apex) as az:
                        public = az.read('apex_pubkey')
                    bits = struct.unpack('!I', public[:4])[0]
                    if bits not in (2048, 4096):
                        raise ValueError(f'Unsupported APEX payload key size: {bits}')
                    identity = hashlib.sha256(public).hexdigest()
                    key = str(keys / 'apex-payload' / identity)
                    payloads[key] = bits
                    apexes.append({'entry': entry, 'name': name, 'key': container,
                                   'payload_key': key + '.pem', 'payload_bits': bits})
                    for apk in sorted(payload.rglob('*.apk')):
                        if apk.is_symlink() or not apk.is_file():
                            raise ValueError(f'Unexpected embedded APK: {apk}')
                        h = digest(apk) if apk_meta[apk.name]['certificate'] == 'PRESIGNED' else None
                        add_apk(entry, apk.name, h, str(apk.relative_to(payload)))
        return {'version': 1, 'target': str(target), 'target_sha256': digest(target),
                'key_dir': str(keys), 'ota_key': ota_key, 'certificates': certificates,
                'payloads': payloads, 'apks': apks, 'apexes': apexes}


def key_password(confirm=False):
    # Refuse getpass's non-terminal fallback, which can echo a secret into logs.
    with open('/dev/tty', 'r'):
        pass
    password = getpass.getpass('Release key password (blank = unencrypted PK8 keys): ')
    if password != password.strip() or '\n' in password or ']]]' in password:
        raise ValueError('Password must not contain newlines, ]]] or surrounding whitespace')
    if confirm and getpass.getpass('Repeat release key password: ') != password:
        raise ValueError('Passwords do not match')
    return password


def validate_private(base, password):
    cmd = ['openssl', 'pkcs8', '-inform', 'DER', '-in', base + '.pk8']
    cmd += ['-passin', 'stdin'] if password else ['-nocrypt']
    pem = run(cmd, (password + '\n').encode() if password else None)
    pub = run(['openssl', 'pkey', '-pubout', '-outform', 'DER'], pem)
    if pub != cert_pub(base + '.x509.pem'):
        raise ValueError(f'Private key/certificate mismatch: {base}')


def generate_keys(plan, password, subject):
    for base in sorted({c['key'] for c in plan['certificates'].values()}):
        cert, private = Path(base + '.x509.pem'), Path(base + '.pk8')
        for path in (cert, private):
            if path.is_symlink():
                raise ValueError(f'Refusing a key symlink: {path}')
        if cert.exists() or private.exists():
            if not (cert.exists() and private.exists()):
                raise ValueError(f'Incomplete key pair; preserving it for review: {base}')
            validate_private(base, password)
            continue
        cert.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cert.parent, prefix='.key-') as td:
            raw = Path(td) / 'key.pem'
            run(['openssl', 'genrsa', '-out', raw, '4096'])
            run(['openssl', 'req', '-new', '-x509', '-sha256', '-key', raw,
                 '-days', '10000', '-subj', subject, '-out', Path(td) / 'cert.pem'])
            cmd = ['openssl', 'pkcs8', '-topk8', '-in', raw, '-outform', 'DER',
                   '-out', Path(td) / 'key.pk8']
            cmd += ['-v1', 'PBE-SHA1-3DES', '-passout', 'stdin'] if password else ['-nocrypt']
            run(cmd, (password + '\n').encode() if password else None)
            os.replace(Path(td) / 'cert.pem', cert)
            os.replace(Path(td) / 'key.pk8', private)
        validate_private(base, password)
    for base, bits in sorted(plan['payloads'].items()):
        key = Path(base + '.pem')
        if key.is_symlink():
            raise ValueError(f'Refusing a payload key symlink: {key}')
        if key.exists():
            run(['openssl', 'rsa', '-in', key, '-check', '-noout'])
        else:
            key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=key.parent, prefix='.key-') as td:
                temporary = Path(td) / 'payload.pem'
                run(['openssl', 'genrsa', '-out', temporary, str(bits)])
                os.replace(temporary, key)
        modulus = run(['openssl', 'rsa', '-in', key, '-modulus', '-noout']).split(b'=', 1)[1]
        if int(modulus, 16).bit_length() != bits:
            raise ValueError(f'Payload key size mismatch: {key}')


def public_map(plan):
    result = []
    for source, mapping in sorted(plan['certificates'].items()):
        cert = mapping['key'] + '.x509.pem'
        new_der = cert_der(cert)
        result.append(dict(mapping, source_certificate=source,
                           new_sha256=hashlib.sha256(new_der).hexdigest()))
    return result


def apk_verify(path, expected, host):
    output = run([host / 'bin/apksigner', 'verify', '--print-certs', path]).decode()
    found = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]+)$', output, re.M)
    if [v.lower() for v in found] != [expected]:
        raise ValueError(f'Unexpected signer certificate: {path}')


def verify_target(plan, signed, host):
    checked = 0
    with zipfile.ZipFile(signed) as z:
        build = props(text(z, 'SYSTEM/build.prop'))
        if (build.get('ro.build.type') != 'user' or build.get('ro.build.tags') != 'release-keys'
                or build.get('ro.build.product') != 'GM8_sprout'
                or build.get('ro.build.version.sdk') != '32'):
            raise ValueError('Signed output must remain user with release-keys tags')
        expected = {c['key']: hashlib.sha256(cert_der(c['key'] + '.x509.pem')).hexdigest()
                    for c in plan['certificates'].values()}
        with tempfile.TemporaryDirectory(prefix='gm8-release-verify-') as td:
            for apk in (a for a in plan['apks'] if a['inside'] is None):
                path = Path(td) / apk['name']
                data = z.read(apk['entry'])
                if apk['key'] is None:
                    if hashlib.sha256(data).hexdigest() != apk['original_sha256']:
                        raise ValueError(f'PRESIGNED APK changed: {apk["entry"]}')
                else:
                    path.write_bytes(gzip.decompress(data) if apk['entry'].endswith('.gz') else data)
                    apk_verify(path, expected[apk['key']], host)
                checked += 1
        for apex in plan['apexes']:
            if apex['key'] is None:
                if hashlib.sha256(z.read(apex['entry'])).hexdigest() != apex['original_sha256']:
                    raise ValueError('PRESIGNED APEX changed')
                continue
            with apex_files(z, apex['entry'], host) as (outer, inner, payload):
                apk_verify(outer, expected[apex['key']], host)
                if outer != inner:
                    apk_verify(inner, expected[apex['key']], host)
                with zipfile.ZipFile(inner) as az:
                    image = payload.parent / 'verify-payload.img'
                    copy_entry(az, 'apex_payload.img', image)
                    public = az.read('apex_pubkey')
                wanted_public = run([host / 'bin/avbtool', 'extract_public_key',
                                     '--key', apex['payload_key'], '--output', '/dev/stdout'])
                if public != wanted_public:
                    raise ValueError(f'APEX payload public key mismatch: {apex["name"]}')
                run([host / 'bin/avbtool', 'verify_image', '--image', image,
                     '--key', apex['payload_key'], '--accept_zeroed_hashtree'])
                for apk in (a for a in plan['apks'] if a['entry'] == apex['entry'] and a['inside']):
                    path = payload / apk['inside']
                    if apk['key'] is None:
                        if digest(path) != apk['original_sha256']:
                            raise ValueError('Embedded PRESIGNED APK changed')
                    else:
                        apk_verify(path, expected[apk['key']], host)
                    checked += 1
        otacerts = [n for n in z.namelist() if n.endswith('/otacerts.zip')]
        if not otacerts:
            raise ValueError('No OTA trust store found in signed target files')
        expected_der = cert_der(plan['ota_key'] + '.x509.pem')
        for entry in otacerts:
            with zipfile.ZipFile(io.BytesIO(z.read(entry))) as certs:
                ders = [run(['openssl', 'x509', '-outform', 'DER'], certs.read(n)) for n in certs.namelist()]
                if not ders or any(der != expected_der for der in ders):
                    raise ValueError(f'Unexpected OTA trust-store certificates: {entry}')
    return checked


def verify_ota(path, cert):
    with zipfile.ZipFile(path) as z:
        info = props(text(z, 'META-INF/com/android/metadata'))
        if (info.get('ota-type') != 'AB' or info.get('ota-wipe') == 'yes'
                or info.get('ota-downgrade') == 'yes'):
            raise ValueError('OTA is not a normal non-wiping full A/B upgrade')
        devices = set(re.split(r'[,|]', info.get('pre-device', '')))
        if not devices or not devices <= {'GM8_sprout', 'GM8_d_sprout'}:
            raise ValueError('OTA device assertion does not match GM8')
        if 'payload.bin' not in z.namelist():
            raise ValueError('OTA payload missing')
    # Android whole-file ZIP signature: the last six bytes locate the detached
    # PKCS#7 signature; the signed prefix excludes the EOCD comment length.
    with Path(path).open('rb') as source, tempfile.TemporaryDirectory(prefix='gm8-ota-cms-') as td:
        size = source.seek(0, 2)
        source.seek(-6, 2)
        offset, marker, comment = struct.unpack('<HHH', source.read(6))
        if marker != 0xffff or offset <= 6 or offset > comment or comment + 22 > size:
            raise ValueError('Invalid OTA signature footer')
        source.seek(size - comment - 22)
        eocd = source.read(comment + 22)
        if eocd[:4] != b'PK\x05\x06' or b'PK\x05\x06' in eocd[4:]:
            raise ValueError('Ambiguous OTA ZIP end record')
        source.seek(size - offset)
        signature = Path(td) / 'signature.der'
        signature.write_bytes(source.read(offset - 6))
        content = Path(td) / 'signed-content'
        source.seek(0)
        remaining = size - comment - 2
        with content.open('wb') as output:
            while remaining:
                block = source.read(min(1024 * 1024, remaining))
                if not block:
                    raise ValueError('Truncated signed OTA')
                output.write(block)
                remaining -= len(block)
        run(['openssl', 'cms', '-verify', '-binary', '-inform', 'DER', '-in', signature,
             '-content', content, '-certfile', cert, '-nointern', '-noverify', '-out', '/dev/null'])
    return info


def sign(plan, output, host, password):
    if digest(plan['target']) != plan['target_sha256']:
        raise ValueError('Target-files changed since key preparation')
    signed = output / 'signed-target_files.zip'
    ota = output / 'gm8-19.1-user-release.zip'
    boot = output / 'gm8-19.1-user-release-boot.img'
    if signed.exists() or ota.exists() or boot.exists():
        raise ValueError('Output already exists; use a new output directory to preserve it')
    mapping = public_map(plan)
    for base in sorted({c['key'] for c in plan['certificates'].values()}):
        validate_private(base, password)
    cmd = [host / 'bin/sign_target_files_apks', '-p', host, '-o', '-d', plan['key_dir']]
    for old, new in sorted(plan['certificates'].items()):
        cmd.extend(['-k', old.removesuffix('.x509.pem') + '=' + new['key']])
    for apex in plan['apexes']:
        if apex['key'] is not None:
            cmd.extend(['--extra_apks', apex['name'] + '=' + apex['key'],
                        '--extra_apex_payload_key', apex['name'] + '=' + apex['payload_key']])
    cmd.extend([plan['target'], signed])
    # Password file format is the exact Android 12.1 PasswordManager format.
    # Keep it private, outside logs, and remove it after both signing commands.
    with tempfile.TemporaryDirectory(dir=plan['key_dir'], prefix='.passwords-') as td:
        pwfile = Path(td) / 'passwords'
        with os.fdopen(os.open(pwfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            stream.write(''.join(f'[[[ {password} ]]] {c["key"]}\n' for c in mapping))
        env = dict(os.environ, ANDROID_PW_FILE=str(pwfile))
        env.pop('ANDROID_SECURE_STORAGE_CMD', None)
        subprocess.run([str(a) for a in cmd], check=True, env=env)
        checked = verify_target(plan, signed, host)
        subprocess.run([str(host / 'bin/ota_from_target_files'), '-p', str(host), '-k',
                        plan['ota_key'], str(signed), str(ota)], check=True, env=env)
    metadata = verify_ota(ota, plan['ota_key'] + '.x509.pem')
    with zipfile.ZipFile(signed) as archive:
        if archive.getinfo('IMAGES/boot.img').file_size > 64 * 1024 * 1024:
            raise ValueError('Signed boot image exceeds the GM8 64 MiB boot partition')
        with archive.open('IMAGES/boot.img') as image:
            if image.read(8) != b'ANDROID!':
                raise ValueError('Unexpected signed boot image header')
        copy_entry(archive, 'IMAGES/boot.img', boot)
    result = {'apks_checked': checked, 'apexes_in_archive': len(plan['apexes']),
              'signed_target_sha256': digest(signed), 'ota_sha256': digest(ota),
              'boot_sha256': digest(boot), 'ota_metadata': metadata,
              'install_mode': 'clean', 'requires_format_data': True,
              'migration_required': False, 'signing_verified': True,
              'device_tested': False}
    (output / 'release-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Verified signed OTA: {ota}')
    print(f'Matching signed recovery-as-boot image: {boot}')
    print('CLEAN INSTALL: back up phone data, use the matching recovery and manually Format Data before installation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'sign'))
    parser.add_argument('--top', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--target-files', type=Path)
    parser.add_argument('--key-dir', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--subject', default='/C=TR/O=GM8 Community/CN=GM8 Release')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        top = args.top.resolve()
        host = host_tools(top)
        output = args.output_dir.expanduser().resolve()
        if output == top or top in output.parents:
            raise ValueError('Release output must be outside the Android checkout')
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        plan_file = output / 'release-plan.json'
        if args.stage == 'prepare':
            if args.target_files is None or args.key_dir is None:
                raise ValueError('prepare requires --target-files and --key-dir')
            if plan_file.exists():
                raise ValueError('Plan exists; use its sign stage or a new output directory')
            keys = private_directory(args.key_dir, top)
            plan = inventory(top, args.target_files.expanduser().resolve(), keys, host)
            password = key_password(confirm=True)
            generate_keys(plan, password, args.subject)
            # Public certificate identities pin the generated keys for sign.
            plan['public_keys'] = public_map(plan)
            plan['payload_key_sha256'] = {key: digest(key + '.pem') for key in plan['payloads']}
            plan_file.write_text(json.dumps(plan, indent=2) + '\n')
            (output / 'public-key-map.json').write_text(json.dumps(plan['public_keys'], indent=2) + '\n')
            print(f'Prepared {len(plan["apks"])} actual APKs (including embedded APKs), '
                  f'{len(plan["apexes"])} actual APEXes. Plan: {plan_file}')
            print('Back up the private key directory separately; never publish it.')
        else:
            plan = json.loads(plan_file.read_text())
            private_directory(plan['key_dir'], top)
            if public_map(plan) != plan['public_keys'] or any(
                    digest(key + '.pem') != value for key, value in plan['payload_key_sha256'].items()):
                raise ValueError('Signing keys changed since preparation')
            sign(plan, output, host, key_password())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f'ERROR: {error}\n')


if __name__ == '__main__':
    main()
