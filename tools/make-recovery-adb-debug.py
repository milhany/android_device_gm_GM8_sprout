#!/usr/bin/env python3
"""Create a separate GM8 pstore boot image with recovery ADB authentication off."""

import argparse
import gzip
import hashlib
import os
from pathlib import Path
import struct
import tempfile
import zlib


def align(size, page):
    return (size + page - 1) // page * page


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_cpio(raw):
    entries = []
    pos = 0
    while pos + 110 <= len(raw):
        header = raw[pos:pos + 110]
        require(header[:6] == b"070701", "Expected a newc recovery ramdisk")
        size = int(header[54:62], 16)
        namesize = int(header[94:102], 16)
        require(namesize > 0, "Invalid CPIO name length")
        end_name = pos + 110 + namesize
        start_data = align(end_name, 4)
        end_data = start_data + size
        require(end_data <= len(raw), "Truncated CPIO entry")
        name_bytes = raw[pos + 110:end_name]
        require(name_bytes[-1:] == b"\0", "Unterminated CPIO name")
        name = name_bytes[:-1].decode("utf-8")
        entries.append((header, name_bytes, raw[start_data:end_data]))
        pos = align(end_data, 4)
        if name == "TRAILER!!!":
            require(not any(raw[pos:]), "Unexpected data after CPIO trailer")
            return entries
    raise ValueError("Missing CPIO trailer")


def patch_ramdisk(raw):
    entries = read_cpio(raw)
    matches = [i for i, entry in enumerate(entries) if entry[1] == b"prop.default\0"]
    require(len(matches) == 1, "Expected exactly one recovery prop.default")
    index = matches[0]
    header, name, data = entries[index]
    require(int(header[14:22], 16) & 0o170000 == 0o100000,
            "Recovery prop.default must be a regular file")
    lines = data.decode("utf-8").splitlines()
    require("ro.build.product=GM8_sprout" in lines, "Not a GM8 recovery image")
    require("ro.debuggable=1" in lines, "This helper requires a userdebug recovery")
    overrides = {"ro.adb.secure": "0", "ro.adb.secure.recovery": "0", "service.adb.root": "1"}
    lines = [line for line in lines if line.split("=", 1)[0] not in overrides]
    lines += [key + "=" + value for key, value in overrides.items()]
    entries[index] = (header, name, ("\n".join(lines) + "\n").encode("utf-8"))
    out = bytearray()
    for header, name, data in entries:
        new_header = bytearray(header)
        new_header[54:62] = f"{len(data):08x}".encode("ascii")
        out.extend(new_header)
        out.extend(name)
        out.extend(b"\0" * (align(len(out), 4) - len(out)))
        out.extend(data)
        out.extend(b"\0" * (align(len(out), 4) - len(out)))
    out.extend(b"\0" * (align(len(out), 512) - len(out)))
    return bytes(out)


def boot_id(kernel, ramdisk, second, lineage):
    digest = hashlib.sha1()
    for payload in (kernel, ramdisk, second):
        digest.update(payload)
        digest.update(struct.pack("<I", len(payload)))
    if lineage:
        digest.update(struct.pack("<I", 0))  # Lineage's unused legacy --dt field.
    return digest.digest()


def patch_image(image):
    require(len(image) >= 2048 and image[:8] == b"ANDROID!", "Not an Android boot image")
    kernel_size, _, ramdisk_size, _, second_size, _, _, page, version = struct.unpack_from(
        "<9I", image, 8)
    require(version == 0 and page == 2048, "Only GM8 v0 / 2048-byte-page boot images are supported")
    kernel_start = page
    ramdisk_start = kernel_start + align(kernel_size, page)
    second_start = ramdisk_start + align(ramdisk_size, page)
    end = second_start + align(second_size, page)
    require(end <= len(image), "Truncated boot image")
    require(not any(image[end:]), "Signed/trailing-data image: refusing to invalidate its signature")
    kernel = image[kernel_start:kernel_start + kernel_size]
    ramdisk = image[ramdisk_start:ramdisk_start + ramdisk_size]
    second = image[second_start:second_start + second_size]
    lineage = None
    for candidate in (True, False):
        if boot_id(kernel, ramdisk, second, candidate) == image[576:596]:
            lineage = candidate
            break
    require(lineage is not None, "Boot header SHA1 does not match its payloads")
    kernel_raw = zlib.decompress(kernel, 31)  # Ignore the appended DTBs.
    require(kernel_raw[56:60] == b"ARM\x64", "Expected an ARM64 kernel")
    config_offset = kernel_raw.find(b"IKCFG_ST")
    require(config_offset >= 0, "Kernel has no embedded configuration")
    config = zlib.decompress(kernel_raw[config_offset + 8:], 31).decode("utf-8").splitlines()
    for key in ("PSTORE", "PSTORE_RAM", "PSTORE_CONSOLE"):
        require("CONFIG_" + key + "=y" in config, "Build the pstore kernel first: missing " + key)
    new_ramdisk = gzip.compress(patch_ramdisk(gzip.decompress(ramdisk)), mtime=0)
    header = bytearray(image[:page])
    struct.pack_into("<I", header, 16, len(new_ramdisk))
    header[576:608] = boot_id(kernel, new_ramdisk, second, lineage) + bytes(12)
    out = bytearray(header)
    for payload in (kernel, new_ramdisk, second):
        out.extend(payload)
        out.extend(bytes(align(len(out), page) - len(out)))
    require(len(out) <= 64 * 1024 * 1024, "Debug image exceeds GM8's boot partition")
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(args.input.resolve() != args.output.resolve(), "Keep the original image: use another output path")
    result = patch_image(args.input.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(result)
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            temporary.replace(args.output)
        finally:
            temporary.unlink(missing_ok=True)
    print("Recovery ADB authentication disabled in:", args.output)
    print("Kernel, appended DTBs, command line and load addresses preserved.")
    print("sha256:", hashlib.sha256(result).hexdigest())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, zlib.error) as exc:
        raise SystemExit("ERROR: " + str(exc))
