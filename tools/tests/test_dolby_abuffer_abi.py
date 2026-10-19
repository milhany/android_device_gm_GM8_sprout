#!/usr/bin/env python3
"""Execute the actual stock/fixed ARM accessors against Android 11 ABuffer data.

Host dependencies: pip install unicorn pyelftools
GM8_VENDOR_TREE may point at a standalone vendor checkout.
"""

import importlib.util
import json
import os
from pathlib import Path
import struct
import unittest

from elftools.elf.elffile import ELFFile
import unicorn as uc
from unicorn import arm_const as arm, arm64_const as a64


DEVICE = Path(__file__).resolve().parents[2]
VENDOR = Path(os.environ.get("GM8_VENDOR_TREE", DEVICE.parents[2] / "vendor/gm/GM8_sprout"))
SPEC = json.loads((DEVICE / "configs/audio/dolby_abuffer_fixups.json").read_text())
MODULE = importlib.util.spec_from_file_location("fixup", DEVICE / "tools/fixup-stock-dolby.py")
FIXUP = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(FIXUP)


class AbufferRegression(unittest.TestCase):
    # start/end VA, input object register, resulting pointer registers, size register.
    SITES = {
        "lib64": [
            (0x5b94, 0x5ba0, a64.UC_ARM64_REG_X9, [a64.UC_ARM64_REG_X0], None),
            (0x5ce0, 0x5cec, a64.UC_ARM64_REG_X9, [a64.UC_ARM64_REG_X0], None),
            (0x5e60, 0x5e70, a64.UC_ARM64_REG_X9, [a64.UC_ARM64_REG_X1], a64.UC_ARM64_REG_W2),
            (0x5f3c, 0x5f48, a64.UC_ARM64_REG_X10,
             [a64.UC_ARM64_REG_X24, a64.UC_ARM64_REG_X25], a64.UC_ARM64_REG_W21),
        ],
        "lib": [
            (0x4700, 0x4708, arm.UC_ARM_REG_R0, [arm.UC_ARM_REG_R0], None),
            (0x47c8, 0x47d0, arm.UC_ARM_REG_R0, [arm.UC_ARM_REG_R0], None),
            (0x48c2, 0x48cc, arm.UC_ARM_REG_R0, [arm.UC_ARM_REG_R1], arm.UC_ARM_REG_R2),
            (0x490a, 0x4912, arm.UC_ARM_REG_R0,
             [arm.UC_ARM_REG_R9, arm.UC_ARM_REG_R11], arm.UC_ARM_REG_R6),
        ],
    }

    def load(self, abi):
        path = VENDOR / "proprietary/vendor" / abi / "libdlbmemoryservice.so"
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            segments = [(p["p_offset"], p["p_vaddr"], p["p_filesz"])
                        for p in elf.iter_segments() if p["p_type"] == "PT_LOAD"]
        return path.read_bytes(), segments

    def offset(self, segments, address):
        return next(off + address - va for off, va, size in segments if va <= address < va + size)

    def run_fragment(self, abi, site, data, segments, capacity, offset, length):
        start, end, source, destinations, length_register = site
        pos = self.offset(segments, start)
        code = bytes(data[pos:pos + end - start])
        machine = uc.Uc(uc.UC_ARCH_ARM64, uc.UC_MODE_ARM) if abi == "lib64" else \
            uc.Uc(uc.UC_ARCH_ARM, uc.UC_MODE_THUMB)
        pc, obj, payload = 0x10000, 0x20000, 0x40000
        machine.mem_map(pc, 0x1000)
        machine.mem_map(obj, 0x1000)
        machine.mem_write(pc, code)
        # AOSP API 30 layout after removal of mMediaBufferBase. RefBase and
        # sp<AMessage> occupy the first three pointers, followed by these fields.
        width = 8 if abi == "lib64" else 4
        pack = "<Q" if width == 8 else "<I"
        for index, value in enumerate([payload, capacity, offset, length]):
            machine.mem_write(obj + (3 + index) * width, struct.pack(pack, value))
        machine.reg_write(source, obj)
        machine.emu_start(pc | (1 if abi == "lib" else 0), pc + len(code))
        address = sum(machine.reg_read(r) for r in destinations)
        size = None if length_register is None else machine.reg_read(length_register)
        return address, size

    def test_real_instructions_reproduce_crash_and_fix_all_accessors(self):
        for abi, sites in self.SITES.items():
            fixed, segments = self.load(abi)
            original = bytearray(fixed)
            for patch in SPEC["abis"][abi]["patches"]:
                pos = self.offset(segments, int(patch["address"], 16))
                new = bytes.fromhex(patch["after"])
                self.assertEqual(fixed[pos:pos + len(new)], new)
                original[pos:pos + len(new)] = bytes.fromhex(patch["before"])
            for site in sites:
                for capacity, offset, length in [(12, 0, 12), (100, 7, 31),
                                                  (8192, 128, 4096), (1, 0, 1), (64, 4, 60)]:
                    with self.subTest(abi=abi, site=hex(site[0]), size=length):
                        bad, _ = self.run_fragment(abi, site, original, segments, capacity, offset, length)
                        good, size = self.run_fragment(abi, site, fixed, segments, capacity, offset, length)
                        self.assertEqual(bad, capacity + length)
                        if length == 12:
                            self.assertEqual(bad, 0x18)  # log(7).txt's exact fault address
                        self.assertEqual(good, 0x40000 + offset)
                        if size is not None:
                            self.assertEqual(size, length)

    def test_fixup_is_idempotent_and_rejects_unknown_code(self):
        for abi in self.SITES:
            fixed, segments = self.load(abi)
            self.assertEqual(FIXUP.fix_abuffer(fixed), fixed)
            corrupted = bytearray(fixed)
            pos = self.offset(segments, int(SPEC["abis"][abi]["patches"][0]["address"], 16))
            corrupted[pos] ^= 1
            with self.assertRaises(ValueError):
                FIXUP.fix_abuffer(corrupted)

    def test_callback_hashes_are_in_the_stock_interface(self):
        # The minimal Java callback must identify itself as stock DMS's interface.
        interface = VENDOR / "proprietary/vendor/lib64/vendor.dolby.hardware.dms@1.0.so"
        client = DEVICE / "dolby/src/org/lineageos/gm8/dolby/StockDmsClient.java"
        import re
        hashes = re.findall(r'hash\("([0-9a-f]{64})"\)', client.read_text())
        self.assertEqual(len(hashes), 2)
        native = interface.read_bytes()
        for value in hashes:
            self.assertIn(bytes.fromhex(value), native)


if __name__ == "__main__":
    unittest.main()
