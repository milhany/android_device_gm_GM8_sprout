#!/usr/bin/env python3
"""Host regressions: real OpenSSL keys/CMS plus target-files signing-plan fixtures."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

script = Path(__file__).resolve().parents[1] / 'release-19.1.py'
spec = importlib.util.spec_from_file_location('gm8release', script)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def expect_failure(call, exception=ValueError):
    try:
        call()
    except exception:
        return
    raise AssertionError('Expected rejection')


def old_key(base):
    base.parent.mkdir(parents=True, exist_ok=True)
    release.run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-x509',
                 '-sha256', '-days', '1', '-subj', '/CN=GM8 Host Fixture',
                 '-keyout', str(base) + '.pem', '-out', str(base) + '.x509.pem'])


def zip_bytes(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        for name, value in entries.items():
            z.writestr(name, value)
    return data.getvalue()


def ota_fixture(path, metadata, key, cert):
    unsigned = zip_bytes({'META-INF/com/android/metadata': metadata, 'payload.bin': b'payload fixture'})
    content = path.parent / 'content'
    content.write_bytes(unsigned[:-2])
    signature = release.run(['openssl', 'cms', '-sign', '-binary', '-in', content,
                             '-signer', cert, '-inkey', key, '-outform', 'DER',
                             '-nosmimecap', '-noattr', '-md', 'sha256'])
    # Same detached whole-file ZIP footer convention as Android SignApk.
    comment_size = len(signature) + 6
    footer = struct.pack('<HHH', len(signature) + 6, 0xffff, comment_size)
    path.write_bytes(unsigned[:-2] + struct.pack('<H', comment_size) + signature + footer)


with tempfile.TemporaryDirectory(prefix='gm8-release-test-') as temporary:
    root = Path(temporary)
    top = root / 'android'
    top.mkdir()
    keys = root / 'keys'
    keys.mkdir(mode=0o700)
    security = top / 'build/make/target/product/security'
    old_key(security / 'testkey')
    # An alias certificate must not be split into a second release identity.
    shutil.copyfile(security / 'testkey.x509.pem', security / 'shared.x509.pem')
    old_key(top / 'packages/example/resource-cert')
    default = 'build/make/target/product/security/testkey.x509.pem'
    alias = 'build/make/target/product/security/shared.x509.pem'
    custom = 'packages/example/resource-cert.x509.pem'
    apkcerts = '\n'.join([
        f'name="System.apk" certificate="{default}" private_key="test.pk8" partition="system"',
        f'name="Alias.apk" certificate="{alias}" private_key="test.pk8" partition="system"',
        f'name="Embedded.apk" certificate="{custom}" private_key="resource.pk8" partition="system"',
        'name="GmsCore.apk" certificate="PRESIGNED" private_key="" partition="system"',
        'name="UnusedTest.apk" certificate="cts/not-installed.x509.pem" private_key="missing.pk8" partition="data"'])
    apexcerts = '\n'.join([
        f'name="com.android.example.apex" public_key="example.pubkey" private_key="example.pem" container_certificate="{default}" container_private_key="test.pk8" partition="system"',
        'name="com.android.apex.cts.shim.apex" public_key="PRESIGNED" private_key="PRESIGNED" container_certificate="PRESIGNED" container_private_key="PRESIGNED" partition="system"'])
    target = root / 'target.zip'
    build = 'ro.build.type=user\nro.build.tags=test-keys\nro.build.product=GM8_sprout\nro.build.version.sdk=32\n'
    entries = {'SYSTEM/build.prop': build,
               'META/misc_info.txt': 'ab_update=true\ndefault_system_dev_certificate=build/make/target/product/security/testkey\n',
               'META/apkcerts.txt': apkcerts, 'META/apexkeys.txt': apexcerts,
               'META/otakeys.txt': '', 'SYSTEM/app/System.apk': b'app',
               'SYSTEM/app/Alias.apk': b'alias', 'SYSTEM/priv-app/GmsCore.apk': b'presigned-google',
               'SYSTEM/apex/com.android.example.apex': b'apex fixture',
               'SYSTEM/apex/com.android.apex.cts.shim.apex': b'presigned-shim'}
    target.write_bytes(zip_bytes(entries))

    @contextlib.contextmanager
    def fixture_apex(z, entry, host):
        with tempfile.TemporaryDirectory(dir=root) as td:
            directory = Path(td)
            outer = directory / 'example.apex'
            outer.write_bytes(zip_bytes({'apex_pubkey': struct.pack('!I', 4096) + b'fixture',
                                         'apex_payload.img': b'payload'}))
            payload = directory / 'contents'
            (payload / 'app').mkdir(parents=True)
            (payload / 'app/Embedded.apk').write_bytes(b'embedded')
            yield outer, outer, payload

    real_apex = release.apex_files
    release.apex_files = fixture_apex
    plan = release.inventory(top, target, keys, root)
    assert len(plan['apks']) == 4 and len(plan['apexes']) == 2
    assert any(a['inside'] == 'app/Embedded.apk' for a in plan['apks'])
    assert plan['certificates'][default]['key'] == plan['certificates'][alias]['key']
    assert 'cts/not-installed.x509.pem' not in plan['certificates']
    assert plan['apexes'][0]['key'] == plan['ota_key']
    assert plan['apexes'][1]['key'] is None
    assert next(a for a in plan['apks'] if a['name'] == 'GmsCore.apk')['key'] is None
    assert list(plan['payloads'].values()) == [4096]
    expect_failure(lambda: release.private_directory(top / 'private-keys', top))
    expect_failure(lambda: release.source_certificate(top, '../keys/outside.pem'))
    expect_failure(lambda: release.records('name="a.apk" certificate="one"\nname="a.apk" certificate="two"'))
    saved_umask = os.umask(0o077)
    try:
        release.generate_keys(plan, 'host-fixture-password', '/CN=GM8 Release Fixture')
        before = {str(p): release.digest(p) for p in keys.rglob('*') if p.is_file()}
        release.generate_keys(plan, 'host-fixture-password', '/CN=GM8 Release Fixture')
        assert before == {str(p): release.digest(p) for p in keys.rglob('*') if p.is_file()}
        for p in keys.rglob('*'):
            if p.is_file():
                assert p.stat().st_mode & 0o077 == 0
        expect_failure(lambda: release.validate_private(plan['ota_key'], 'wrong-password'),
                       subprocess.CalledProcessError)
        exported = release.public_map(plan)
        assert all(c['old_sha256'] != c['new_sha256'] for c in exported)
        assert 'PRIVATE KEY' not in json.dumps(exported)
        # The blank-password path also produces a reusable valid key pair.
        unencrypted = {'certificates': {'one': {'key': str(keys / 'no-password')}}, 'payloads': {}}
        release.generate_keys(unencrypted, '', '/CN=GM8 Unencrypted Fixture')
        release.validate_private(str(keys / 'no-password'), '')
    finally:
        os.umask(saved_umask)

    # Real cryptographic whole-OTA verification, including wrong cert, modified
    # payload, wipe/downgrade flags and device assertions.
    ota = root / 'ota.zip'
    metadata = 'ota-type=AB\npre-device=GM8_sprout,GM8_d_sprout\n'
    ota_fixture(ota, metadata, security / 'testkey.pem', security / 'testkey.x509.pem')
    assert release.verify_ota(ota, security / 'testkey.x509.pem')['ota-type'] == 'AB'
    expect_failure(lambda: release.verify_ota(ota, top / 'packages/example/resource-cert.x509.pem'),
                   subprocess.CalledProcessError)
    tampered = bytearray(ota.read_bytes())
    position = tampered.index(b'payload fixture')
    tampered[position] ^= 1
    ota.write_bytes(tampered)
    expect_failure(lambda: release.verify_ota(ota, security / 'testkey.x509.pem'),
                   subprocess.CalledProcessError)
    for extra in ('ota-wipe=yes\n', 'ota-downgrade=yes\n', 'pre-device=another_phone\n'):
        ota_fixture(ota, metadata + extra, security / 'testkey.pem', security / 'testkey.x509.pem')
        expect_failure(lambda: release.verify_ota(ota, security / 'testkey.x509.pem'))

    # Fake only the Android binary execution to test our verification decisions.
    # Actual Android signing/image rebuilding still needs the owner's checkout.
    signed = root / 'signed.zip'
    certificates = [c for c in exported if c['source_certificate'] == default]
    expected = certificates[0]['new_sha256']
    entries['SYSTEM/build.prop'] = build.replace('test-keys', 'release-keys')
    entries['SYSTEM/etc/security/otacerts.zip'] = zip_bytes({'releasekey.x509.pem': Path(plan['ota_key'] + '.x509.pem').read_bytes()})
    signed.write_bytes(zip_bytes(entries))
    original_run = release.run
    calls = []

    def verify_commands(args, data=None):
        calls.append([str(a) for a in args])
        name = Path(args[0]).name
        if name == 'apksigner':
            return f'Signer #1 certificate SHA-256 digest: {expected}\n'.encode()
        if name == 'avbtool' and args[1] == 'extract_public_key':
            return struct.pack('!I', 4096) + b'fixture'
        if name == 'avbtool':
            return b''
        return original_run(args, data)

    # This fixture uses one signer for APK checks; all production checks use
    # their per-key identity. Test that PRESIGNED changes fail independently.
    single_key_plan = json.loads(json.dumps(plan))
    for apk in single_key_plan['apks']:
        if apk['key'] is not None:
            apk['key'] = plan['ota_key']
    release.run = verify_commands
    assert release.verify_target(single_key_plan, signed, root) == 4
    assert any('verify_image' in call for call in calls)
    entries['SYSTEM/priv-app/GmsCore.apk'] = b'changed-google'
    signed.write_bytes(zip_bytes(entries))
    expect_failure(lambda: release.verify_target(single_key_plan, signed, root))
    release.run = original_run
    release.apex_files = real_apex

    output = root / 'release-output'
    output.mkdir()
    binary_calls = []
    password_files = []
    actual_subprocess = subprocess.run
    actual_verify = release.verify_target

    def signing_binaries(argv, *args, **kwargs):
        binary = Path(argv[0]).name
        if binary not in ('sign_target_files_apks', 'ota_from_target_files'):
            return actual_subprocess(argv, *args, **kwargs)
        binary_calls.append([str(a) for a in argv])
        pwfile = Path(kwargs['env']['ANDROID_PW_FILE'])
        password_files.append(pwfile)
        assert pwfile.stat().st_mode & 0o077 == 0
        assert '[[[ host-fixture-password ]]]' in pwfile.read_text()
        assert 'host-fixture-password' not in ' '.join(str(a) for a in argv)
        if binary == 'sign_target_files_apks':
            Path(argv[-1]).write_bytes(zip_bytes({'IMAGES/boot.img': b'ANDROID!fixture-boot'}))
        else:
            raw_key = root / 'temporary-signing-key.pem'
            raw_key.write_bytes(release.run(['openssl', 'pkcs8', '-inform', 'DER',
                '-in', plan['ota_key'] + '.pk8', '-passin', 'stdin'], b'host-fixture-password\n'))
            ota_fixture(Path(argv[-1]), metadata, raw_key, plan['ota_key'] + '.x509.pem')
        return subprocess.CompletedProcess(argv, 0)

    subprocess.run = signing_binaries
    release.verify_target = lambda *args: 4
    try:
        release.sign(plan, output, root, 'host-fixture-password')
    finally:
        subprocess.run = actual_subprocess
        release.verify_target = actual_verify
    first, second = binary_calls
    assert '-o' in first and '-d' in first
    assert '--extra_apks' in first and '--extra_apex_payload_key' in first
    assert any(arg == 'com.android.example.apex=' + plan['apexes'][0]['payload_key'] for arg in first)
    assert all(not p.exists() for p in password_files)
    assert '--wipe_user_data' not in second and '--downgrade' not in second
    result = json.loads((output / 'release-verification.json').read_text())
    assert result['install_mode'] == 'clean' and result['requires_format_data']
    assert not result['migration_required'] and result['signing_verified']
    assert (output / 'gm8-19.1-user-release-boot.img').read_bytes() == b'ANDROID!fixture-boot'
    expect_failure(lambda: release.sign(plan, output, root, 'host-fixture-password'))

print('PASS: installed/embedded inventory, cert aliases, PRESIGNED preservation, '
      'encrypted/reused keys, actual CMS signature pinning/tamper detection, '
      'signing argument/password-file lifecycle and non-wipe OTA guards')
