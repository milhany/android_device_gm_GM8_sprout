#!/usr/bin/env python3
"""Check native services, Wi-Fi registration and the packaged kernel before signing."""
import argparse
import importlib.util
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib


def require_hal(manifest, name, version, interface):
    entries = [h for h in manifest.findall('hal') if h.findtext('name') == name]
    if len(entries) != 1 or entries[0].findtext('transport') != 'hwbinder':
        raise ValueError(f'Missing unique hwbinder manifest entry: {name}')
    hal = entries[0]
    found = (version in [v.text for v in hal.findall('version')] and
             any(i.findtext('name') == interface and
                 'default' in [n.text for n in i.findall('instance')]
                 for i in hal.findall('interface')))
    found = found or f'@{version}::{interface}/default' in [
        f.text for f in hal.findall('fqname')]
    if not found:
        raise ValueError(f'Missing manifest instance: {name}@{version}::{interface}/default')


def require_service(text, name, binary, interface=None):
    found = False
    interfaces = []
    current = None
    for line in text.splitlines():
        words = line.split('#', 1)[0].split()
        if not words:
            continue
        if not line[0].isspace():
            current = None
            if words[0] == 'service' and len(words) >= 3 and words[1] == name:
                if found or words[2] != binary:
                    raise ValueError(f'Duplicate or mismatched init service: {name}')
                found = True
                current = name
        elif current == name and words[0] == 'interface':
            interfaces.append(' '.join(words[1:]))
    if not found or (interface is not None and interface not in interfaces):
        raise ValueError(f'Missing init service/interface: {name} {interface or binary}')


def require_arm_executable(data, name):
    if len(data) < 52 or data[:4] != b'\x7fELF' or data[5] != 1:
        raise ValueError(f'Invalid native service ELF: {name}')
    machine = struct.unpack_from('<H', data, 18)[0]
    if (data[4], machine) not in ((1, 40), (2, 183)):
        raise ValueError(f'Expected ARM/AArch64 service: {name}')
    if (data[4] == 2 and len(data) < 64) or struct.unpack_from('<H', data, 16)[0] not in (2, 3):
        raise ValueError(f'Invalid executable header: {name}')


def gunzip_first(data, limit):
    stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
    result = stream.decompress(data, limit + 1)
    if len(result) > limit or not stream.eof:
        raise ValueError('Truncated or oversized kernel gzip stream')
    return result


def extract_config(kernel):
    image = gunzip_first(kernel, 128 * 1024 * 1024) if kernel[:2] == b'\x1f\x8b' else kernel
    marker = b'IKCFG_ST\x1f\x8b\x08'
    start = image.find(marker)
    if start < 0:
        raise ValueError('Packaged kernel has no readable IKCONFIG; refusing an unverified boot')
    return gunzip_first(image[start + 8:], 1024 * 1024)


def check_packaged_kernel(path, expected_config):
    with zipfile.ZipFile(path) as archive:
        kernel = archive.read('BOOT/kernel')
        config = extract_config(kernel)
        if config.strip() != expected_config.strip():
            raise ValueError('Packaged kernel IKCONFIG differs from the freshly built .config')
        if 'IMAGES/boot.img' in archive.namelist():
            boot = archive.read('IMAGES/boot.img')
            if len(boot) < 44 or boot[:8] != b'ANDROID!':
                raise ValueError('Invalid packaged Android boot header')
            size = struct.unpack_from('<I', boot, 8)[0]
            page = struct.unpack_from('<I', boot, 36)[0]
            if page not in (2048, 4096, 8192, 16384) or boot[page:page + size] != kernel:
                raise ValueError('IMAGES/boot.img does not contain the checked BOOT/kernel')
    spec = importlib.util.spec_from_file_location(
        'gm8_kernel_check', Path(__file__).with_name('check-kernel-17.1.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check(config.decode('utf-8'))


def symbols(data, label):
    if (len(data) < 64 or data[:6] != b'\x7fELF\x02\x01' or
            struct.unpack_from('<H', data, 16)[0] != 3 or
            struct.unpack_from('<H', data, 18)[0] != 183):
        raise ValueError(f'Expected AArch64 shared ELF for {label}')
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count = struct.unpack_from('<HH', data, 58)
    if size != 64 or offset + size * count > len(data):
        raise ValueError(f'Invalid ELF section table: {label}')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * size)
                for i in range(count)]
    required, exported = set(), set()
    for section in sections:
        if section[1] != 11:  # SHT_DYNSYM
            continue
        if section[6] >= count or section[9] != 24:
            raise ValueError(f'Invalid dynamic symbol table: {label}')
        strings = sections[section[6]]
        string_end = strings[4] + strings[5]
        end = section[4] + section[5]
        if end > len(data) or string_end > len(data):
            raise ValueError(f'Truncated dynamic symbols: {label}')
        table = data[strings[4]:string_end]
        for pos in range(section[4], end, 24):
            name, info, _, index, _, _ = struct.unpack_from('<IBBHQQ', data, pos)
            if name >= len(table):
                raise ValueError(f'Invalid symbol name: {label}')
            symbol = table[name:].split(b'\0', 1)[0].decode('ascii')
            if info >> 4 not in (1, 2):
                continue
            (required if index == 0 else exported).add(symbol)
    return required, exported


def check(path):
    with zipfile.ZipFile(path) as archive:
        service = archive.read('VENDOR/bin/hw/vendor.qti.hardware.perf@1.0-service')
        library = archive.read('VENDOR/lib64/vendor.qti.hardware.perf@1.0.so')
        undefined, _ = symbols(service, 'perf service')
        _, exported = symbols(library, 'perf library')
        required = {s for s in undefined if '_ZN6vendor3qti8hardware4perf4V1_05IPerf' in s}
        if not required or not required <= exported:
            raise ValueError('Unresolved legacy IPerf imports: ' + str(sorted(required - exported)))
        manifest = ET.fromstring(archive.read('VENDOR/etc/vintf/manifest.xml'))
        perf = [h for h in manifest.findall('hal')
                if h.findtext('name') == 'vendor.qti.hardware.perf']
        if len(perf) != 1 or perf[0].findtext('transport') != 'hwbinder':
            raise ValueError('Missing unique hwbinder perf manifest entry')
        found = ('1.0' in [v.text for v in perf[0].findall('version')] and
                 any(i.findtext('name') == 'IPerf' and i.findtext('instance') == 'default'
                     for i in perf[0].findall('interface')))
        found = found or '@1.0::IPerf/default' in [f.text for f in perf[0].findall('fqname')]
        if not found:
            raise ValueError('Missing IPerf 1.0/default manifest instance')
        fingerprint = [h for h in manifest.findall('hal')
                       if h.findtext('name') == 'android.hardware.biometrics.fingerprint']
        if len(fingerprint) != 1 or fingerprint[0].findtext('transport') != 'hwbinder':
            raise ValueError('Missing unique hwbinder fingerprint manifest entry')
        hal = fingerprint[0]
        found = ('2.1' in [v.text for v in hal.findall('version')] and
                 any(i.findtext('name') == 'IBiometricsFingerprint' and
                     'default' in [n.text for n in i.findall('instance')]
                     for i in hal.findall('interface')))
        found = found or '@2.1::IBiometricsFingerprint/default' in [
            f.text for f in hal.findall('fqname')]
        if not found:
            raise ValueError('Missing IBiometricsFingerprint 2.1/default manifest instance')
        for name, version, interface in (
                ('android.hardware.wifi', '1.3', 'IWifi'),
                ('android.hardware.wifi.supplicant', '1.2', 'ISupplicant'),
                ('android.hardware.wifi.hostapd', '1.1', 'IHostapd')):
            require_hal(manifest, name, version, interface)
        for name in ('android.hardware.wifi@1.0-service', 'wpa_supplicant', 'hostapd'):
            require_arm_executable(archive.read('VENDOR/bin/hw/' + name), name)
        init = archive.read('VENDOR/etc/init/hw/init.qcom.rc').decode('utf-8')
        require_service(init, 'wpa_supplicant', '/vendor/bin/hw/wpa_supplicant',
                        'android.hardware.wifi.supplicant@1.2::ISupplicant default')
        require_service(init, 'hostapd_fst', '/vendor/bin/hw/hostapd',
                        'android.hardware.wifi.hostapd@1.1::IHostapd default')
        wifi_rc = archive.read('VENDOR/etc/init/android.hardware.wifi@1.0-service.rc').decode('utf-8')
        require_service(wifi_rc, 'vendor.wifi_hal_legacy',
                        '/vendor/bin/hw/android.hardware.wifi@1.0-service')
    return len(required)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-files', type=Path, required=True)
    parser.add_argument('--kernel-config', type=Path, required=True)
    args = parser.parse_args()
    try:
        count = check(args.target_files)
        check_packaged_kernel(args.target_files, args.kernel_config.read_bytes())
    except (OSError, ValueError, KeyError, struct.error, UnicodeError, ET.ParseError,
            zipfile.BadZipFile, zlib.error) as error:
        parser.exit(1, f'Runtime packaging check failed: {error}\n')
    print(f'PASS: packaged AArch64 perf dependency resolves {count} IPerf imports; manifest registered')
    print('PASS: Q Wi-Fi services/manifest/init interfaces and matching packaged kernel IKCONFIG')
    print('This check does not establish Android linker namespace or hardware operation.')


if __name__ == '__main__':
    main()
