#!/usr/bin/env python3
"""Relocate GM8's stock Dolby storage without changing the DS1 audio algorithm."""

import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blob", type=Path)
    parser.add_argument("--patchelf", default="patchelf")
    args = parser.parse_args()
    blob = args.blob
    data = blob.read_bytes()
    if not data.startswith(b"\x7fELF"):
        parser.error("Expected an ELF shared library")
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
