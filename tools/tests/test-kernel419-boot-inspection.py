#!/usr/bin/env python3
"""Check the inspector against real mkbootimg output and recorded kernel files."""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


def expect_error(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError("Malformed input was accepted")


def cpio_entry(name, data, mode=0o100644):
    name = name.encode() + b"\0"
    fields = [1, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name), 0]
    header = b"070701" + b"".join(f"{v:08x}".encode() for v in fields)
    blob = header + name
    blob += b"\0" * (-len(blob) % 4)
    blob += data
    return blob + b"\0" * (-len(blob) % 4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mkbootimg", type=Path, required=True)
    parser.add_argument("--kernel-out", type=Path, required=True)
    args = parser.parse_args()
    script = Path(__file__).resolve().parents[1] / "inspect-kernel419-boot.py"
    spec = importlib.util.spec_from_file_location("boot_inspection", script)
    inspection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspection)
    out = args.kernel_out.resolve()
    with tempfile.TemporaryDirectory(prefix="gm8-boot-inspection-") as directory:
        root = Path(directory)
        ramdisk = (cpio_entry("init", b"/system/bin/init", 0o120777)
                   + cpio_entry("fstab.qcom", b"/dev/block/by-name/system / ext4 ro wait,slotselect\n")
                   + cpio_entry("TRAILER!!!", b"", 0))
        compressed = gzip.compress(ramdisk, mtime=0)
        (root / "kernel").write_bytes(b"baseline kernel fixture")
        (root / "ramdisk").write_bytes(compressed)
        (root / "dtbo").write_bytes(b"recovery DTBO fixture")
        (root / "dtb").write_bytes((out / inspection.ARTIFACTS[2]).read_bytes())
        cmdline = "androidboot.hardware=qcom " + "test=" + "x" * 800
        images = []
        for version in (0, 1, 2):
            image = root / f"boot-v{version}.img"
            command = [sys.executable, str(args.mkbootimg.resolve()),
                       "--header_version", str(version), "--kernel", str(root / "kernel"),
                       "--ramdisk", str(root / "ramdisk"), "--base", "0x80000000",
                       "--kernel_offset", "0x80000", "--ramdisk_offset", "0x1000000",
                       "--tags_offset", "0x100", "--pagesize", "2048", "--board", "GM8",
                       "--os_version", "12.1.0", "--os_patch_level", "2026-10",
                       "--cmdline", cmdline, "--output", str(image)]
            if version:
                command += ["--recovery_dtbo", str(root / "dtbo")]
            if version == 2:
                command += ["--dtb", str(root / "dtb")]
            subprocess.run(command, check=True)
            data = image.read_bytes()
            before = inspection.sha(data)
            info, parts = inspection.boot_info(data)
            assert info["header_version"] == version
            assert info["cmdline"] == cmdline and info["board"] == "GM8"
            assert info["os_version"] == "12.1.0" and info["os_patch_level"] == "2026-10"
            assert parts["ramdisk"] == compressed
            if version:
                assert parts["recovery_dtbo"] == b"recovery DTBO fixture"
            if version == 2:
                assert parts["dtb"] == (root / "dtb").read_bytes()
            report = inspection.inspect(data, out)
            assert report["layout_check"]["overlap"]
            assert report["ramdisk"]["cpio_verified"]
            assert report["ramdisk"]["boot_entries"]["init"]["symlink"] == "/system/bin/init"
            assert not report["boot_image_produced"] and not report["flash_ready"]
            assert inspection.sha(image.read_bytes()) == before
            images.append(data)
        print("PASS: mkbootimg v0/v1/v2 headers, split cmdline, components and read-only inspection")
        info, parts = inspection.boot_info(images[0] + b"SEANDROIDENFORCE")
        assert info["trailer"] == "SEANDROIDENFORCE marker"
        info, _ = inspection.boot_info(images[0] + b"AVBf" + bytes(60))
        assert info["trailer"].startswith("AVB footer")
        info, _ = inspection.boot_info(images[0] + b"unknown signature")
        assert info["trailer"] == "unrecognized nonzero trailer"
        for data in (images[0][:100], images[0][:-1], b"NOTBOOT!" + images[0][8:]):
            expect_error(lambda data=data: inspection.boot_info(data))
        for offset, value in ((40, 3), (36, 4096), (8, 0xffffffff), (16, 0)):
            data = bytearray(images[0])
            struct.pack_into("<I", data, offset, value)
            expect_error(lambda data=data: inspection.boot_info(bytes(data)))
        expect_error(lambda: inspection.ramdisk_info(gzip.compress(ramdisk[:-120])))
        expect_error(lambda: inspection.ramdisk_info(compressed + compressed))
        print("PASS: truncated/unsupported headers, signing trailers and malformed ramdisks")
        data = bytearray(images[0])
        struct.pack_into("<I", data, 20, 0x83000000)
        assert not inspection.inspect(bytes(data), out)["layout_check"]["overlap"]
        data = bytearray(images[0])
        struct.pack_into("<I", data, 12, 0x80008000)
        assert any("text_offset" in w for w in inspection.inspect(bytes(data), out)["warnings"])
        # Bind inspection to the recorded build rather than accepting loose artifacts.
        record = json.loads((out / "gm8-kernel419-build.json").read_text())
        bad = root / "bad-record"
        bad.mkdir()
        record["patch_sha256"] = "0" * 64
        (bad / "gm8-kernel419-build.json").write_text(json.dumps(record))
        expect_error(lambda: inspection.kernel_info(bad))
        record = json.loads((out / "gm8-kernel419-build.json").read_text())
        record["artifacts"][inspection.ARTIFACTS[0]] = "0" * 64
        (bad / "gm8-kernel419-build.json").write_text(json.dumps(record))
        for name in inspection.ARTIFACTS:
            path = bad / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(out / name)
        expect_error(lambda: inspection.kernel_info(bad))
        print("PASS: actual Image memory extent, load alignment and build/hash mismatch refusal")


if __name__ == "__main__":
    main()
