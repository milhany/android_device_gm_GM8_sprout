#!/usr/bin/env python3
"""Prepare and compile the standalone GM8 4.19 board-port checkpoint."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

DEVICE = Path(__file__).resolve().parents[1]
PORT = DEVICE / "kernel419"
UPSTREAM = "https://github.com/LineageOS/android_kernel_xiaomi_msm8937.git"
REVISION = "e24963ba7e7376ad052179723a22b316e73af7d9"
PATCH = PORT / "0001-gm8-board-bringup.patch"


def run(args, cwd=None, capture=False, env=None):
    return subprocess.run([str(x) for x in args], cwd=cwd, check=True,
                          text=True, capture_output=capture, env=env).stdout


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_check(source):
    root = Path(run(["git", "rev-parse", "--show-toplevel"], source, True).strip())
    if root.resolve() != source:
        raise ValueError("--source must be the kernel repository root")
    head = run(["git", "rev-parse", "HEAD"], source, True).strip()
    if head != REVISION:
        raise ValueError(f"Expected pinned upstream {REVISION}; found {head}")
    # This also checks newly added files, without relying on a stale stamp.
    run(["git", "apply", "--reverse", "--check", PATCH], source)


def prepare(source):
    if source.exists():
        source_check(source)
        print(f"Port patch already present: {source}")
        return
    source.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--depth=1", "--single-branch", "--no-checkout",
         "--branch=lineage-22.2", UPSTREAM, source])
    # Fetch the immutable revision even when the remote branch has moved.
    run(["git", "fetch", "--depth=1", "origin", REVISION], source)
    run(["git", "checkout", "--detach", REVISION], source)
    run(["git", "apply", "--check", PATCH], source)
    run(["git", "apply", "--index", PATCH], source)
    source_check(source)
    print(f"Prepared {source}; changes are staged for inspection.")
    print("Board-port checkpoint only; peripheral driver porting remains.")


def fdt(dtb, node, prop, kind="x"):
    return run(["fdtget", "-t", kind, dtb, node, prop], capture=True).strip()


def verify(dtb):
    if not shutil.which("fdtget"):
        raise ValueError("Install device-tree-compiler to provide fdtget")
    if not dtb.is_file():
        raise ValueError(f"DTB missing: {dtb}")
    expected = {
        ("/", "qcom,msm-id"): [313, 0],
        ("/", "qcom,board-id"): [8, 0],
        ("/", "qcom,pmic-id"): [0x10019, 0, 0, 0],
        ("/reserved-memory/other_ext_region@0", "reg"):
            [0, 0x84a00000, 0, 0x1e00000],
        ("/reserved-memory/modem_region@0", "reg"):
            [0, 0x86800000, 0, 0x6a00000],
        ("/reserved-memory/adsp_fw_region@0", "reg"):
            [0, 0x8d200000, 0, 0x1100000],
        ("/reserved-memory/wcnss_fw_region@0", "reg"):
            [0, 0x8e300000, 0, 0x700000],
        ("/reserved-memory/ramoops@9ff00000", "reg"):
            [0, 0x9ff00000, 0, 0x100000],
        ("/soc/i2c@78b5000", "reg"): [0x78b5000, 0x600],
        ("/soc/i2c@78b5000/tps65132@3e", "reg"): [0x3e],
        ("/soc/i2c@7af5000/bq2560x@6B", "ti,bq2560x,ta-vreg"): [4400],
        ("/soc/i2c@7af5000/bq2560x@6B", "ti,bq2560x,ta-ichg"): [1980],
        ("/soc/i2c@7af5000/bq2560x@6B", "qcom,thermal-mitigation"):
            [1980, 1500, 1000, 500, 0],
        ("/soc/qcom,mdss_mdp@1a00000/qcom,mdss_dsi_ft8006m_720p_video",
         "qcom,mdss-dsi-panel-width"): [720],
        ("/soc/qcom,mdss_mdp@1a00000/qcom,mdss_dsi_ft8006m_720p_video",
         "qcom,mdss-dsi-panel-height"): [1440],
    }
    for (node, prop), value in expected.items():
        actual = [int(cell, 16) for cell in fdt(dtb, node, prop).split()]
        if actual != value:
            raise ValueError(f"Unexpected {node}:{prop}: {actual} != {value}")
    compatibles = fdt(dtb, "/", "compatible", "s").split()
    if "gm,gm8-sprout" not in compatibles:
        raise ValueError("GM8 board compatible missing")
    print("DTB checks passed: GM8 selectors, memory, panel, bias bus and charger limits.")
    print("These checks do not establish bootability or peripheral operation.")


def build(args, source):
    source_check(source)
    out = args.out.expanduser().resolve()
    if out == source or source in out.parents:
        raise ValueError("Use a separate output directory outside the kernel source")
    if out == DEVICE or DEVICE in out.parents:
        raise ValueError("Keep experimental output outside the device repository")
    env = os.environ.copy()
    if args.llvm_bin:
        env["PATH"] = str(args.llvm_bin.expanduser().resolve()) + os.pathsep + env["PATH"]
    required = ["git", "make", "clang", "ld.lld", "llvm-ar", "llvm-nm",
                "llvm-objcopy", "llvm-objdump", "llvm-readelf", "llvm-strip",
                "aarch64-linux-gnu-as", "arm-linux-gnueabihf-as",
                "aarch64-linux-gnu-gcc", "arm-linux-gnueabihf-gcc",
                "bison", "flex", "bc", "cpio", "perl", "fdtget"]
    missing = [tool for tool in required if not shutil.which(tool, path=env["PATH"])]
    if missing:
        raise ValueError("Missing host tools: " + ", ".join(missing))
    out.mkdir(parents=True, exist_ok=True)
    command = ["make", "-C", source, f"O={out}", "ARCH=arm64", "LLVM=1",
               "LLVM_IAS=1", "CROSS_COMPILE=aarch64-linux-gnu-",
               "CROSS_COMPILE_ARM32=arm-linux-gnueabihf-"]
    run(command + ["gm8_defconfig"], env=env)
    run(command + [f"-j{args.jobs}", "Image.gz-dtb", "dtbs"], env=env)
    dtb = out / "arch/arm64/boot/dts/gm/gm8_sprout.dtb"
    verify(dtb)
    names = ["arch/arm64/boot/Image.gz", "arch/arm64/boot/Image.gz-dtb",
             "arch/arm64/boot/dts/gm/gm8_sprout.dtb", ".config"]
    metadata = {
        "upstream": UPSTREAM, "revision": REVISION,
        "patch_sha256": digest(PATCH),
        "compiler": run(["clang", "--version"], capture=True, env=env).splitlines()[0],
        "hardware_tested": False, "flash_ready": False,
        "artifacts": {name: digest(out / name) for name in names},
    }
    record = out / "gm8-kernel419-build.json"
    record.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Build record: {record}")
    print("No Android boot image or OTA was produced; this checkpoint is not flash-ready.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare", help="clone pinned upstream and stage board patch")
    prep.add_argument("--source", required=True, type=Path)
    compile_parser = sub.add_parser("build", help="compile standalone kernel and GM8 DTB")
    compile_parser.add_argument("--source", required=True, type=Path)
    compile_parser.add_argument("--out", required=True, type=Path)
    compile_parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 1, 8))
    compile_parser.add_argument("--llvm-bin", type=Path)
    check = sub.add_parser("verify", help="check board selectors and fixed memory regions")
    check.add_argument("--dtb", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "verify":
        verify(args.dtb.expanduser().resolve())
    elif args.action == "prepare":
        prepare(args.source.expanduser().resolve())
    else:
        if args.jobs < 1:
            raise ValueError("--jobs must be positive")
        build(args, args.source.expanduser().resolve())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
