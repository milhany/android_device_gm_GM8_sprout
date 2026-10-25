#!/usr/bin/env python3
"""Cross-check temporary boot packing against Lineage mkbootimg."""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fails(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError("Unsafe or stale input was accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mkbootimg", type=Path, required=True)
    parser.add_argument("--kernel-out", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    packer = load("packer", here.parent / "pack-kernel419-boot.py")
    inspector = packer.load_inspector()
    fixtures = load("fixtures", here / "test-kernel419-boot-inspection.py")
    out = args.kernel_out.resolve()
    with tempfile.TemporaryDirectory(prefix="gm8-pack-test-") as directory:
        root = Path(directory)
        initrd = gzip.compress(fixtures.cpio_entry("init", b"/system/bin/init", 0o120750)
                               + fixtures.cpio_entry("TRAILER!!!", b"", 0), mtime=0)
        (root / "ramdisk").write_bytes(initrd)
        old = bytearray(64)
        old[56:60] = b"ARM\x64"
        command = [sys.executable, str(args.mkbootimg.resolve()), "--header_version", "0",
                   "--pagesize", "2048", "--base", "0x80000000", "--tags_offset", "0x100",
                   "--kernel", str(root / "kernel"), "--ramdisk", str(root / "ramdisk"),
                   "--os_version", "12.0.0", "--os_patch_level", "2025-03"]
        new_raw = gzip.decompress((out / inspector.ARTIFACTS[0]).read_bytes())
        dtb = (out / inspector.ARTIFACTS[2]).read_bytes()
        for encoding, baseline, expected in (
                ("gzip", gzip.compress(old), (out / inspector.ARTIFACTS[1]).read_bytes()),
                ("raw", bytes(old), new_raw + dtb),
                ("wrapped", b"UNCOMPRESSED_IMG" + struct.pack("<I", len(old)) + old,
                 b"UNCOMPRESSED_IMG" + struct.pack("<I", len(new_raw)) + new_raw + dtb)):
            (root / "kernel").write_bytes(baseline)
            subprocess.run(command + ["--cmdline", "androidboot.hardware=qcom buildvariant=user",
                                      "--output", str(root / "base.img")], check=True)
            base = (root / "base.img").read_bytes()
            report = inspector.inspect(base, out)
            assert report["layout_check"]["overlap"]
            result, record = packer.pack(base, out, report, inspector)
            info, parts = inspector.boot_info(result)
            assert parts["kernel"] == expected and parts["ramdisk"] == initrd
            assert info["kernel_address"] == "0x80080000"
            assert info["ramdisk_address"] == "0x83000000"
            assert info["os_version"] == "12.0.0" and info["os_patch_level"] == "2025-03"
            assert record["ramdisk_preserved_byte_identical"] and not record["warnings"]
            (root / "kernel").write_bytes(expected)
            subprocess.run(command + ["--kernel_offset", "0x80000", "--ramdisk_offset", "0x3000000",
                                      "--cmdline", info["cmdline"], "--output", str(root / "reference.img")],
                           check=True)
            assert result == (root / "reference.img").read_bytes()
            assert base == (root / "base.img").read_bytes()
        print("PASS: gzip/raw/wrapped candidates byte-identical to independent mkbootimg output")
        stale = dict(report, flash_ready=True)
        fails(lambda: packer.pack(base, out, stale, inspector))
        signed = base + b"unrecognized signature"
        signed_report = inspector.inspect(signed, out)
        fails(lambda: packer.pack(signed, out, signed_report, inspector))
        broken = bytearray(base)
        broken[576] ^= 1
        broken_report = inspector.inspect(bytes(broken), out)
        fails(lambda: packer.pack(bytes(broken), out, broken_report, inspector))
        broken = bytearray(base)
        broken[2048:2068] = b"unknown kernel data!"
        struct.pack_into("<I", broken, 8, len(baseline))
        _, components = inspector.boot_info(bytes(broken))
        broken[576:608] = packer.image_id(components["kernel"], components["ramdisk"], True)
        broken_report = inspector.inspect(bytes(broken), out)
        fails(lambda: packer.pack(bytes(broken), out, broken_report, inspector))
        original_address = packer.RAMDISK_ADDRESS
        packer.RAMDISK_ADDRESS = 0x81000000
        fails(lambda: packer.pack(base, out, report, inspector))
        packer.RAMDISK_ADDRESS = original_address
        print("PASS: stale reports, signing trailers, corrupt identifiers, unknown encodings and overlap refused")
        (root / "inspection.json").write_text(json.dumps(report))
        output = root / "candidate"
        cli = [sys.executable, str(here.parent / "pack-kernel419-boot.py"),
               "--base-boot", str(root / "base.img"), "--inspection", str(root / "inspection.json"),
               "--kernel-out", str(out), "--output-dir", str(output)]
        subprocess.run(cli, check=True, capture_output=True, text=True)
        backup = output / "gm8-working-3.18-boot.img"
        image = output / "gm8-kernel419-test-boot.img"
        assert backup.read_bytes() == base
        image_sha = inspector.sha(image.read_bytes())
        assert subprocess.run(cli, capture_output=True).returncode != 0
        assert inspector.sha(image.read_bytes()) == image_sha
        assert backup.read_bytes() == base
        print("PASS: CLI saves the exact working boot, verified candidate and report; existing output preserved")


if __name__ == "__main__":
    main()
