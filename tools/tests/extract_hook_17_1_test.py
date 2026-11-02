#!/usr/bin/env python3
"""Verify Q argument handling and all Dolby blob hooks without extracting blobs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='gm8-q-extract-') as name:
    top = Path(name)
    device = top / 'device/gm/GM8_sprout'
    (device / 'tools').mkdir(parents=True)
    helper = top / 'vendor/lineage/build/tools/extract_utils.sh'
    helper.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'extract-files.sh', device / 'extract-files.sh')
    (device / 'proprietary-files.txt').touch()
    (device / 'setup-makefiles.sh').write_text('#!/bin/bash\ntouch "$GM8_TEST_RESULT/makefiles-called"\n')
    (device / 'setup-makefiles.sh').chmod(0o755)
    (device / 'tools/fixup-stock-dolby.py').write_text('''import json,os,sys
from pathlib import Path
p=Path(os.environ['GM8_TEST_RESULT'])/'fixups.jsonl'
with p.open('a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
''')
    helper.write_text('''PATCHELF=/fixture/patchelf
setup_vendor() {
    test "$5" = false
}
extract() {
    test "$2" = /input/rom
    test "$3" = --kang
    test "$4" = --section
    test "$5" = audio
    for blob in vendor/lib/libdlbdsservice.so vendor/lib64/libdlbdsservice.so vendor/lib/libdlbmemoryservice.so vendor/lib64/libdlbmemoryservice.so; do
        blob_fixup "$blob" "$GM8_TEST_RESULT/$(basename "$blob")"
    done
}
''')
    env = dict(os.environ, GM8_TEST_RESULT=str(top))
    subprocess.run(['bash', str(device / 'extract-files.sh'), '-n', '-k', '-s', 'audio', '/input/rom'],
                   env=env, check=True)
    calls = [json.loads(line) for line in (top / 'fixups.jsonl').read_text().splitlines()]
    assert len(calls) == 4 and all(c[1:] == ['--patchelf', '/fixture/patchelf'] for c in calls)
    assert (top / 'makefiles-called').is_file()

print('PASS: Q extraction options preserved; all four Dolby fixups run in blob_fixup, without touching vendor data')
