#!/usr/bin/env python3
"""Create a GM8 4.19 temporary-boot candidate from an inspected working image."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys


KERNEL_ADDRESS = 0x80080000
RAMDISK_ADDRESS = 0x83000000
FIRMWARE_START = 0x84a00000


def load_inspector():
    path = Path(__file__).with_name("inspect-kernel419-boot.py")
    spec = importlib.util.spec_from_file_location("gm8_boot_inspector", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def image_id(kernel, ramdisk, legacy_dt_size):
    # Android v0 identifier, including Lineage's optional legacy --dt size.
    digest = hashlib.sha1()
    for data in (kernel, ramdisk, b""):
        digest.update(data)
        digest.update(struct.pack("<I", len(data)))
    if legacy_dt_size:
        digest.update(bytes(4))
    return digest.digest() + bytes(12)


def payload_for_base(base_kernel, out, inspector):
    compressed = (out / inspector.ARTIFACTS[0]).read_bytes()
    dtb = (out / inspector.ARTIFACTS[2]).read_bytes()
    if base_kernel.startswith(b"\x1f\x8b"):
        return compressed + dtb, "gzip Image + DTB"
    image = gzip.decompress(compressed)  # Stream/size already checked by inspector.
    if base_kernel.startswith(b"UNCOMPRESSED_IMG"):
        size = struct.unpack_from("<I", base_kernel, 16)[0]
        if size < 64 or size > len(base_kernel) - 20 or base_kernel[76:80] != b"ARM\x64":
            raise ValueError("Unrecognized stock UNCOMPRESSED_IMG wrapper")
        return b"UNCOMPRESSED_IMG" + struct.pack("<I", len(image)) + image + dtb, \
            "UNCOMPRESSED_IMG wrapper + Image + DTB"
    if base_kernel[56:60] == b"ARM\x64":
        return image + dtb, "raw ARM64 Image + DTB"
    raise ValueError("Unrecognized base kernel encoding; first bytes: " + base_kernel[:20].hex())


def pack(base, out, previous, inspector):
    actual = inspector.inspect(base, out)
    if actual != previous:
        raise ValueError("Inputs no longer match the saved boot-inspection report")
    info, parts = inspector.boot_info(base)
    if info["header_version"] != 0 or parts["second"] or info["trailer"] != "zero padding only":
        raise ValueError("This candidate packer requires v0, no second image, no signing trailer")
    entries = actual["ramdisk"].get("boot_entries", {})
    if not actual["ramdisk"].get("cpio_verified") or entries.get("init", {}).get("symlink") != "/system/bin/init":
        raise ValueError("Expected the inspected GM8 recovery-as-boot ramdisk")
    if int(info["tags_address"], 16) != 0x80000100:
        raise ValueError("Unexpected GM8 DTB/tags address")
    modes = [mode for mode in (False, True)
             if image_id(parts["kernel"], parts["ramdisk"], mode) == base[576:608]]
    if len(modes) != 1:
        raise ValueError("Unrecognized base image identifier; refusing to guess its format")
    kernel = actual["kernel419"]
    end = KERNEL_ADDRESS + kernel["image_memory_bytes"]
    rend = RAMDISK_ADDRESS + len(parts["ramdisk"])
    dtb_size = (out / inspector.ARTIFACTS[2]).stat().st_size
    if ((KERNEL_ADDRESS - int(kernel["text_offset"], 16)) % 0x200000
            or end > RAMDISK_ADDRESS or rend > FIRMWARE_START
            or 0x80000100 + dtb_size > KERNEL_ADDRESS):
        raise ValueError("Image, ramdisk or DTB does not fit the GM8 candidate load layout")
    payload, encoding = payload_for_base(parts["kernel"], out, inspector)
    header = bytearray(base[:2048])
    struct.pack_into("<I", header, 8, len(payload))
    struct.pack_into("<I", header, 12, KERNEL_ADDRESS)
    struct.pack_into("<I", header, 20, RAMDISK_ADDRESS)
    header[576:608] = image_id(payload, parts["ramdisk"], modes[0])
    # Only diagnostic parameters are added; root/verity/slot policy stays intact.
    cmdline = info["cmdline"] + " panic=10 loglevel=7"
    encoded = cmdline.encode()
    if len(encoded) > 1534:
        raise ValueError("No room for diagnostic kernel command line")
    header[64:576] = encoded[:511].ljust(512, b"\0")
    header[608:1632] = encoded[511:].ljust(1024, b"\0")
    pad = lambda blob: blob + bytes(-len(blob) % 2048)
    candidate = bytes(header) + pad(payload) + pad(parts["ramdisk"])
    if len(candidate) > inspector.PARTITION_SIZE:
        raise ValueError("Candidate exceeds the GM8 64 MiB boot partition limit")
    checked = inspector.inspect(candidate, out)
    if checked["warnings"] or checked["layout_check"]["overlap"]:
        raise ValueError("Candidate did not pass its final header/layout inspection")
    _, new_parts = inspector.boot_info(candidate)
    if new_parts["ramdisk"] != parts["ramdisk"]:
        raise ValueError("Recovery ramdisk preservation check failed")
    checked.update({"purpose": "temporary fastboot boot candidate; not an OTA",
                    "base_boot_sha256": info["sha256"], "kernel_encoding": encoding,
                    "boot_image_produced": True, "flash_ready": False,
                    "bootloader_relocation_verified": False,
                    "ramdisk_preserved_byte_identical": True,
                    "firmware_start": hex(FIRMWARE_START),
                    "image_identifier_format": "Lineage v0 + legacy dt size" if modes[0] else "AOSP v0"})
    return candidate, checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-boot", type=Path, required=True)
    parser.add_argument("--kernel-out", type=Path, required=True)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        inspector = load_inspector()
        base = args.base_boot.expanduser().read_bytes()
        previous = json.loads(args.inspection.expanduser().read_text())
        candidate, report = pack(base, args.kernel_out.expanduser(), previous, inspector)
        output = args.output_dir.expanduser()
        output.mkdir(parents=True, exist_ok=False)
        backup = output / "gm8-working-3.18-boot.img"
        image = output / "gm8-kernel419-test-boot.img"
        backup.write_bytes(base)
        image.write_bytes(candidate)
        (output / "boot-candidate.json").write_text(json.dumps(report, indent=2) + "\n")
    except (OSError, ValueError, KeyError, struct.error) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1
    print(f"Candidate: {image}")
    print(f"Working boot backup: {backup}")
    print(f"Size: {len(candidate)} / {inspector.PARTITION_SIZE} bytes")
    print(f"SHA256: {inspector.sha(candidate)}")
    print("PASS: recorded artifacts, header identifier, byte-identical ramdisk and non-overlapping layout")
    print("Phone boot, bootloader placement and peripherals remain unverified. No device was flashed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
