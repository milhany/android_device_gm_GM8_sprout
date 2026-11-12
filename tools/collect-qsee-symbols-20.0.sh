#!/usr/bin/env bash
# Read the existing kernel build; never rebuild, flash or access signing keys.
set -euo pipefail
script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
top="$(cd "$script/../../../.." && pwd)"
cd "$top"
python3 - "$top" <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import subprocess
import sys
import tempfile

top = Path(sys.argv[1])
obj = top / 'out/target/product/GM8_sprout/obj/KERNEL_OBJ'
image = obj / 'vmlinux'
prefix = top / 'prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/bin/aarch64-linux-android-'
nm, dump = Path(str(prefix) + 'nm'), Path(str(prefix) + 'objdump')
for path in (image, nm, dump):
    if not path.is_file():
        raise SystemExit('Missing existing build input: ' + str(path))
symbols = {}
text = subprocess.check_output([str(nm), '-S', '--defined-only', str(image)], text=True)
wanted = ('qseecom_release', 'qseecom_ioctl', '__qseecom_process_incomplete_cmd',
          '__qseecom_abort_legacy_listener')
for line in text.splitlines():
    fields = line.split()
    if len(fields) == 4 and fields[3] in wanted:
        if fields[3] in symbols:
            raise SystemExit('Ambiguous symbol: ' + fields[3])
        symbols[fields[3]] = (int(fields[0], 16), int(fields[1], 16))
for name in wanted[:2]:
    if name not in symbols:
        raise SystemExit('Missing required symbol: ' + name)
for name, (_, size) in symbols.items():
    if not 0 < size < 1024 * 1024:
        raise SystemExit('Missing or invalid symbol: ' + name)
# These addresses and lengths come from the blocked-task traces, not guesses
# about the lock named by a current source line. A mismatch is still reported.
expected = {'qseecom_release': (0xffffffc0005a39ac, 0x200),
            'qseecom_ioctl': (0xffffffc0005a8030, 0x176c)}
match = all(symbols[name] == value for name, value in expected.items())
parent = top.parent / 'gm8-20.0-records'
parent.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
output = Path(tempfile.mkdtemp(prefix=stamp + '-qsee-symbols-', dir=parent)) / 'qsee-build.txt'
hasher = hashlib.sha256()
with image.open('rb') as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        hasher.update(chunk)
with output.open('w') as report:
    report.write('GM8 existing-build QSEE symbol capture\n')
    report.write('vmlinux SHA256: ' + hasher.hexdigest() + '\n')
    release = obj / 'include/config/kernel.release'
    report.write('kernel.release: ' + (release.read_text().strip() if release.is_file() else 'unavailable') + '\n')
    report.write('Matches November 12 bugreport QSEE symbol layout: ' + str(match) + '\n')
    report.write('Layout matching is not proof that the complete binary is identical.\n')
    for name in wanted:
        if name not in symbols:
            report.write('\n' + name + ': no standalone symbol (possibly inlined)\n')
            continue
        address, size = symbols[name]
        report.write('\n' + name + ': ' + hex(address) + ', size ' + hex(size) + '\n')
        report.flush()
        # GCC 4.9 binutils rejects --disassemble=symbol. Use address ranges.
        subprocess.run([str(dump), '-d', '-l', '--start-address=' + hex(address),
                        '--stop-address=' + hex(address + size), str(image)],
                       stdout=report, check=True)
print('Existing-build report: ' + str(output))
print('Bugreport QSEE symbol layout matches: ' + str(match))
print('No build, image, device or signing-key operation was performed.')
if not match:
    print('This build differs from the reported kernel; preserve the matching earlier vmlinux if available.')
PY
