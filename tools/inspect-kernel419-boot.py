#!/usr/bin/env python3
"""Inspect a GM8 boot image and recorded 4.19 output without repacking/flashing."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib


PARTITION_SIZE = 64 * 1024 * 1024
ARTIFACTS = ("arch/arm64/boot/Image.gz", "arch/arm64/boot/Image.gz-dtb",
             "arch/arm64/boot/dts/gm/gm8_sprout.dtb", ".config")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, page):
    return (value + page - 1) // page * page


def boot_info(data):
    if len(data) < 1632 or len(data) > PARTITION_SIZE or data[:8] != b"ANDROID!":
        raise ValueError("Expected a complete Android boot image, at most 64 MiB")
    fields = struct.unpack_from("<10I", data, 8)
    ksize, kaddr, rsize, raddr, ssize, saddr, tags, page, version, osver = fields
    if version not in (0, 1, 2):
        raise ValueError("Expected legacy GM8 boot header v0/v1/v2; found " + str(version))
    if page != 2048:
        raise ValueError("Expected the GM8 2048-byte boot page size")
    header_size = (1632, 1648, 1660)[version]
    if len(data) < header_size or not ksize or not rsize:
        raise ValueError("Incomplete boot header or empty kernel/recovery ramdisk")
    components = {}
    cursor = page
    for name, size in (("kernel", ksize), ("ramdisk", rsize), ("second", ssize)):
        if cursor + size > len(data):
            raise ValueError("Truncated boot component: " + name)
        components[name] = data[cursor:cursor + size]
        cursor += align(size, page)
    if version:
        dtbo_size, dtbo_offset, declared_size = struct.unpack_from("<IQI", data, 1632)
        if declared_size != header_size:
            raise ValueError("Unexpected declared boot header size")
        if dtbo_size:
            if dtbo_offset != cursor or cursor + dtbo_size > len(data):
                raise ValueError("Unexpected or truncated recovery DTBO layout")
            components["recovery_dtbo"] = data[cursor:cursor + dtbo_size]
            cursor += align(dtbo_size, page)
        elif dtbo_offset:
            raise ValueError("Nonzero recovery DTBO offset for an empty component")
    if version == 2:
        dtb_size, dtb_addr = struct.unpack_from("<IQ", data, 1648)
        if not dtb_size or cursor + dtb_size > len(data):
            raise ValueError("Missing or truncated header-v2 DTB")
        components["dtb"] = data[cursor:cursor + dtb_size]
        cursor += align(dtb_size, page)
    # Require complete padded components before interpreting a signing trailer.
    if cursor > len(data):
        raise ValueError("Truncated boot component padding")
    tail = data[cursor:]
    nonzero_tail = tail.strip(b"\0")
    trailer = "zero padding only" if not nonzero_tail else "unrecognized nonzero trailer"
    if nonzero_tail == b"SEANDROIDENFORCE":
        trailer = "SEANDROIDENFORCE marker"
    if len(data) >= 64 and data[-64:-60] == b"AVBf":
        trailer = "AVB footer; repacking requires explicit signing treatment"
    text = lambda value: value.split(b"\0", 1)[0].decode("utf-8", errors="replace")
    cmdline = text(data[64:576]) + text(data[608:1632])
    return {
        "sha256": sha(data), "file_bytes": len(data), "header_version": version,
        "page_size": page, "kernel_address": hex(kaddr),
        "ramdisk_address": hex(raddr), "second_address": hex(saddr),
        "tags_address": hex(tags), "board": text(data[48:64]),
        "os_version": "%d.%d.%d" % (osver >> 25, (osver >> 18) & 127,
                                      (osver >> 11) & 127),
        "os_patch_level": "%04d-%02d" % (2000 + ((osver & 2047) >> 4), osver & 15),
        "cmdline": cmdline, "payload_end": cursor,
        "trailer": trailer, "trailer_bytes": len(tail),
        "components": {name: {"bytes": len(blob), "sha256": sha(blob)}
                       for name, blob in components.items()},
    }, components


def ramdisk_info(data):
    if data.startswith(b"\x1f\x8b"):
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = decoder.decompress(data, PARTITION_SIZE + 1)
        if len(raw) > PARTITION_SIZE or not decoder.eof or decoder.unused_data:
            raise ValueError("Ramdisk exceeds 64 MiB, is truncated or has extra gzip members")
        compression = "gzip"
    elif data.startswith((b"070701", b"070702")):
        raw, compression = data, "none"
    else:
        return {"compression": "unrecognized (no extraction attempted)",
                "cpio_verified": False}
    cursor, selected, count = 0, {}, 0
    while cursor + 110 <= len(raw):
        header = raw[cursor:cursor + 110]
        if header[:6] not in (b"070701", b"070702"):
            raise ValueError("Malformed ramdisk newc header")
        fields = [int(header[pos:pos + 8], 16) for pos in range(6, 110, 8)]
        size, namesize = fields[6], fields[11]
        start = cursor + 110
        if not namesize or start + namesize > len(raw) or raw[start + namesize - 1] != 0:
            raise ValueError("Malformed ramdisk entry name")
        name = raw[start:start + namesize - 1].decode("utf-8", errors="replace")
        start = align(start + namesize, 4)
        if start + size > len(raw):
            raise ValueError("Truncated ramdisk entry")
        if name == "TRAILER!!!":
            return {"compression": compression, "cpio_verified": True,
                    "uncompressed_bytes": len(raw), "entry_count": count,
                    "boot_entries": selected}
        clean_name = name.removeprefix("./")
        if (clean_name in ("init", "system/bin/init", "init.rc", "default.prop",
                           "prop.default") or "fstab" in clean_name):
            blob = raw[start:start + size]
            entry = {"bytes": size, "mode": oct(fields[1]), "sha256": sha(blob)}
            if fields[1] & 0o170000 == 0o120000:
                entry["symlink"] = blob.decode("utf-8", errors="replace")
            if "fstab" in clean_name and size <= 16384:
                entry["contents"] = blob.decode("utf-8", errors="replace")
            selected[clean_name] = entry
        cursor = align(start + size, 4)
        count += 1
        if count > 100000:
            raise ValueError("Too many ramdisk entries")
    raise ValueError("Ramdisk cpio trailer not found")


def kernel_info(out):
    record = json.loads((out / "gm8-kernel419-build.json").read_text())
    patch = Path(__file__).resolve().parents[1] / "kernel419/0001-gm8-board-bringup.patch"
    if record.get("patch_sha256") != sha(patch.read_bytes()):
        raise ValueError("Kernel build record belongs to a different port checkpoint")
    blobs = {}
    for name in ARTIFACTS:
        blob = (out / name).read_bytes()
        if record.get("artifacts", {}).get(name) != sha(blob):
            raise ValueError("Kernel artifact does not match its build record: " + name)
        blobs[name] = blob
    zipped, dtb = blobs[ARTIFACTS[0]], blobs[ARTIFACTS[2]]
    if zipped + dtb != blobs[ARTIFACTS[1]]:
        raise ValueError("Image.gz-dtb is not the recorded Image.gz plus GM8 DTB")
    if len(dtb) < 40 or dtb[:4] != b"\xd0\x0d\xfe\xed" or struct.unpack_from(
            ">I", dtb, 4)[0] != len(dtb):
        raise ValueError("Unexpected appended DTB layout")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    image = decoder.decompress(zipped, 128 * 1024 * 1024 + 1)
    if len(image) > 128 * 1024 * 1024 or not decoder.eof or decoder.unused_data:
        raise ValueError("Invalid or oversized kernel gzip stream")
    if len(image) < 64 or image[56:60] != b"ARM\x64":
        raise ValueError("Missing ARM64 Image header")
    offset, size, flags = struct.unpack_from("<QQQ", image, 8)
    if not size or size < len(image) or flags & 1:
        raise ValueError("Unexpected ARM64 Image size or endianness")
    return {"upstream_revision": record["revision"],
            "patch_sha256": record["patch_sha256"],
            "image_gz_dtb_bytes": len(blobs[ARTIFACTS[1]]),
            "image_gz_dtb_sha256": sha(blobs[ARTIFACTS[1]]),
            "image_file_bytes": len(image), "image_memory_bytes": size,
            "text_offset": hex(offset), "flags": hex(flags)}


def inspect(boot, out):
    info, parts = boot_info(boot)
    kernel = kernel_info(out)
    start = int(info["kernel_address"], 16)
    end = start + kernel["image_memory_bytes"]
    rstart = int(info["ramdisk_address"], 16)
    rend = rstart + len(parts["ramdisk"])
    overlaps = start < rend and rstart < end
    warnings = []
    if overlaps:
        warnings.append("Header load addresses would overlap the new Image memory and ramdisk; "
                        "do not reuse this layout without reviewing bootloader relocation.")
    if (start - int(kernel["text_offset"], 16)) % (2 * 1024 * 1024):
        warnings.append("Header kernel address does not satisfy the new ARM64 text_offset; "
                        "the bootloader's actual placement must be established.")
    if info["trailer"] != "zero padding only":
        warnings.append("Base image has a trailer that must be reviewed before repacking.")
    return {"base_boot": info, "ramdisk": ramdisk_info(parts["ramdisk"]),
            "kernel419": kernel,
            "layout_check": {"assumption": "literal boot-header addresses, without relocation",
                             "kernel_range": [hex(start), hex(end)],
                             "ramdisk_range": [hex(rstart), hex(rend)],
                             "overlap": overlaps},
            "warnings": warnings, "hardware_tested": False,
            "boot_image_produced": False, "flash_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-boot", type=Path, required=True)
    parser.add_argument("--kernel-out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = inspect(args.base_boot.expanduser().read_bytes(),
                         args.kernel_out.expanduser())
    except (OSError, ValueError, KeyError, struct.error, zlib.error) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
