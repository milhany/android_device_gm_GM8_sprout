#!/usr/bin/env python3
"""Check the packaged legacy perf dependency before release signing."""
import argparse
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zipfile


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
    return len(required)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-files', type=Path, required=True)
    args = parser.parse_args()
    try:
        count = check(args.target_files)
    except (OSError, ValueError, KeyError, struct.error, UnicodeError, ET.ParseError,
            zipfile.BadZipFile) as error:
        parser.exit(1, f'Runtime packaging check failed: {error}\n')
    print(f'PASS: packaged AArch64 perf dependency resolves {count} IPerf imports; manifest registered')
    print('This check does not establish Android linker namespace or hardware operation.')


if __name__ == '__main__':
    main()
