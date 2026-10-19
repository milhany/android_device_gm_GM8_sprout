#!/usr/bin/env python3
"""Isolate stock GM8 protobuf dependencies from Android 12 platform libraries."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def abi(path, libdir):
    with path.open("rb") as stream:
        header = stream.read(20)
    expected = (1, 40) if libdir == "lib" else (2, 183)
    if (len(header) != 20 or header[:4] != b"\x7fELF" or header[5] != 1 or
            (header[4], int.from_bytes(header[18:20], "little")) != expected):
        raise ValueError(f"Not a matching little-endian ARM ELF: {path}")


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".gm8-protobuf-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--patchelf")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--blob", type=Path, help="single extracted blob to fix")
    parser.add_argument("--relative-path", help="stock vendor/... path for --blob")
    args = parser.parse_args()
    if bool(args.blob) != bool(args.relative_path):
        parser.error("--blob and --relative-path must be supplied together")
    top = args.top.resolve()
    device = Path(__file__).resolve().parents[1]
    if not args.blob:
        version = top / "build/core/version_defaults.mk"
        if not version.is_file() or not re.search(
                r"^\s*PLATFORM_SDK_VERSION\s*:?=\s*32\s*$", version.read_text(), re.M):
            raise ValueError("Legacy protobuf fixup requires Android 12.1 / SDK 32.")
    candidates = [args.patchelf] if args.patchelf else [
        os.environ.get("PATCHELF"),
        str(top / "prebuilts/extract-tools/linux-x86/bin/patchelf-0_9"),
        shutil.which("patchelf"),
    ]
    patchelf = next((shutil.which(p) for p in candidates if p and shutil.which(p)), None)
    if not patchelf:
        raise ValueError("Missing patchelf; sync prebuilts/extract-tools or pass --patchelf.")

    def elf(*options):
        return subprocess.check_output([patchelf, *map(str, options)], text=True).strip()

    manifest = json.loads((device / "configs/legacy-protobuf.json").read_text())["files"]
    if args.blob:
        manifest = [item for item in manifest if item["path"] == args.relative_path]
        if len(manifest) != 1:
            raise ValueError("Blob path is not in the reviewed legacy protobuf manifest.")
    changes = []
    report = {"patchelf": elf("--version"), "libraries": [], "files": []}
    with tempfile.TemporaryDirectory(prefix="gm8-protobuf-") as temp_name:
        temp = Path(temp_name)
        if not args.blob:
            for arch, libdir in (("arm", "lib"), ("arm64", "lib64")):
                for variant in ("full", "lite"):
                    original = f"libprotobuf-cpp-{variant}.so"
                    renamed = f"libprotobuf-cpp-{variant}-v29.so"
                    source = (top / "prebuilts/vndk/v29/arm64" /
                              f"arch-{arch}-armv8-a/shared/vndk-core" / original)
                    abi(source, libdir)
                    if elf("--print-soname", source) != original:
                        raise ValueError(f"Unexpected snapshot SONAME: {source}")
                    staged = temp / f"{arch}-{renamed}"
                    shutil.copy2(source, staged)
                    elf("--set-soname", renamed, staged)
                    abi(staged, libdir)
                    if elf("--print-soname", staged) != renamed:
                        raise ValueError(f"Failed to isolate snapshot SONAME: {source}")
                    before_needed = elf("--print-needed", source).splitlines()
                    if before_needed != elf("--print-needed", staged).splitlines():
                        raise ValueError(f"Snapshot dependencies changed: {source}")
                    output = device / "generated/legacy-protobuf" / libdir / renamed
                    data = staged.read_bytes()
                    before = output.read_bytes() if output.is_file() else None
                    if before != data:
                        changes.append((output, before, data, 0o644))
                    report["libraries"].append({"path": str(output), "soname": renamed,
                                                "source_sha256": digest(source.read_bytes()),
                                                "sha256": digest(data)})
        for index, entry in enumerate(manifest):
            relative = entry["path"]
            blob = args.blob if args.blob else top / "vendor/gm/GM8_sprout/proprietary" / relative
            libdir = "lib64" if relative.startswith("vendor/lib64/") else "lib"
            abi(blob, libdir)
            old = f"libprotobuf-cpp-{entry['variant']}.so"
            new = f"libprotobuf-cpp-{entry['variant']}-v29.so"
            needed = elf("--print-needed", blob).splitlines()
            before = blob.read_bytes()
            mode = stat.S_IMODE(blob.stat().st_mode)
            if old in needed:
                if new in needed or digest(before) != entry["sha256"]:
                    raise ValueError(f"Stock blob differs from reviewed input; no files changed: {relative}")
                staged = temp / f"blob-{index}.so"
                shutil.copy2(blob, staged)
                elf("--replace-needed", old, new, staged)
                expected = [new if name == old else name for name in needed]
                if elf("--print-needed", staged).splitlines() != expected:
                    raise ValueError(f"Unexpected dependency rewrite: {relative}")
                if elf("--print-soname", staged) != elf("--print-soname", blob):
                    raise ValueError(f"Vendor blob SONAME changed: {relative}")
                abi(staged, libdir)
                data = staged.read_bytes()
                changes.append((blob, before, data, mode))
                needed = expected
            elif new in needed:
                data = before
            else:
                raise ValueError(f"Expected protobuf dependency missing: {relative}")
            report["files"].append({"path": relative, "sha256": digest(data), "needed": needed})

    if args.check and changes:
        raise ValueError("Legacy protobuf fixups are missing or stale; run tools/fixup-legacy-protobuf.py.")
    applied = []
    try:
        for path, before, data, mode in changes:
            atomic_write(path, data, mode)
            applied.append((path, before, mode))
    except OSError:
        for path, before, mode in reversed(applied):
            if before is None:
                path.unlink()
            else:
                atomic_write(path, before, mode)
        raise
    if args.record:
        atomic_write(args.record, (json.dumps(report, indent=2) + "\n").encode(), 0o644)
    print(f"GM8 legacy protobuf fixups ready ({len(changes)} file(s) updated).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
