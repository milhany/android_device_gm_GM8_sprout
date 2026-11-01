#!/usr/bin/env python3
"""Relocate GM8's stock Dolby storage without changing the DS1 audio algorithm."""

import argparse
import json
from pathlib import Path
import struct
import subprocess


def fix_abuffer(data):
    """Patch only the audited API-27 inline accessors in this exact stock ELF."""
    config = Path(__file__).resolve().parents[1] / "configs/audio/dolby_abuffer_fixups.json"
    elf64 = data[4] == 2
    if data[4] not in (1, 2) or data[5] != 1:
        raise ValueError("Unsupported Dolby ELF encoding")
    header = struct.unpack_from("<HHIQQQIHHHHHH" if elf64 else "<HHIIIIIHHHHHH", data, 16)
    abi = "lib64" if elf64 else "lib"
    entry = json.loads(config.read_text())["abis"][abi]
    if header[1] != (183 if elf64 else 40):
        raise ValueError("Unexpected Dolby ELF machine")
    segments = []
    build_id = None
    for index in range(header[9]):
        p = struct.unpack_from("<IIQQQQQQ" if elf64 else "<IIIIIIII", data,
                               header[4] + index * header[8])
        offset, address, size = (p[2], p[3], p[5]) if elf64 else (p[1], p[2], p[4])
        if p[0] == 1:
            segments.append((offset, address, size))
        elif p[0] == 4:
            pos = offset
            while pos + 12 <= offset + size:
                namesz, descsz, kind = struct.unpack_from("<III", data, pos)
                name = data[pos + 12:pos + 12 + namesz].rstrip(b"\0")
                desc = pos + 12 + ((namesz + 3) & ~3)
                if name == b"GNU" and kind == 3:
                    build_id = data[desc:desc + descsz].hex()
                pos = desc + ((descsz + 3) & ~3)
    if build_id != entry["build_id"]:
        raise ValueError("Unsupported Dolby build ID; no instructions changed")
    result = bytearray(data)
    for patch in entry["patches"]:
        address = int(patch["address"], 16)
        candidates = [offset + address - va for offset, va, size in segments
                      if va <= address < va + size]
        if len(candidates) != 1:
            raise ValueError(f"Unmapped Dolby instruction {address:#x}")
        offset = candidates[0]
        before, after = bytes.fromhex(patch["before"]), bytes.fromhex(patch["after"])
        if len(before) != len(after) or result[offset:offset + len(before)] not in (before, after):
            raise ValueError(f"Unexpected Dolby instruction {address:#x}; refusing to patch")
        result[offset:offset + len(after)] = after
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blob", type=Path)
    parser.add_argument("--patchelf", default="patchelf")
    args = parser.parse_args()
    blob = args.blob
    data = blob.read_bytes()
    if not data.startswith(b"\x7fELF"):
        parser.error("Expected an ELF shared library")
    if b"libdlbmemoryservice.so\0" in data:
        data = fix_abuffer(data)
    for old, new in (
        (b"/system/etc/dolby/dax-default.xml", b"/vendor/etc/dolby/dax-default.xml"),
        (b"/data/misc/media/", b"/data/vendor/ds/"),
    ):
        assert len(new) <= len(old)
        data = data.replace(old + b"\0", new + b"\0" * (len(old) + 1 - len(new)))
    # Neither stock library imports ICU symbols. Its obsolete, unused DT_NEEDED
    # must not pull Android 8 ICU into Android 11's vendor linker namespace.
    symbols = subprocess.check_output(["readelf", "--dyn-syms", "-W", str(blob)], text=True)
    if any(" UND " in line and "_58" in line for line in symbols.splitlines()):
        parser.error("This blob imports ICU 58; refusing to remove its dependency")
    needed = subprocess.check_output([args.patchelf, "--print-needed", str(blob)], text=True)
    blob.write_bytes(data)
    if "libicuuc.so" in needed.splitlines():
        subprocess.run([args.patchelf, "--remove-needed", "libicuuc.so", str(blob)], check=True)


if __name__ == "__main__":
    main()
