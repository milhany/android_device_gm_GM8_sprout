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
import tempfile

DEVICE = Path(__file__).resolve().parents[1]
PORT = DEVICE / "kernel419"
UPSTREAM = "https://github.com/LineageOS/android_kernel_xiaomi_msm8937.git"
REVISION = "e24963ba7e7376ad052179723a22b316e73af7d9"
PATCH = PORT / "0001-gm8-board-bringup.patch"
POWER_UPGRADE = PORT / "upgrades/d06c76c-power.patch"
TOUCH_UPGRADE = PORT / "upgrades/9530763-touch.patch"


def run(args, cwd=None, capture=False, env=None):
    try:
        return subprocess.run([str(x) for x in args], cwd=cwd, check=True,
                              text=True, capture_output=capture, env=env).stdout
    except subprocess.CalledProcessError as error:
        if capture and error.stderr:
            print(error.stderr, end="", file=sys.stderr)
        raise


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_check(source, quiet=False):
    root = Path(run(["git", "rev-parse", "--show-toplevel"], source, True).strip())
    if root.resolve() != source:
        raise ValueError("--source must be the kernel repository root")
    head = run(["git", "rev-parse", "HEAD"], source, True).strip()
    if head != REVISION:
        raise ValueError(f"Expected pinned upstream {REVISION}; found {head}")
    # This also checks newly added files, without relying on a stale stamp.
    if quiet:
        subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)],
                       cwd=source, check=True, text=True, capture_output=True)
    else:
        run(["git", "apply", "--reverse", "--check", PATCH], source)


def upgrade_known_checkpoint(source):
    """Recognize an exact older port and apply one checked cumulative delta."""
    if Path(run(["git", "rev-parse", "--show-toplevel"], source, True).strip()).resolve() != source:
        return False
    if run(["git", "rev-parse", "HEAD"], source, True).strip() != REVISION:
        return False
    if subprocess.run(["git", "diff", "--quiet"], cwd=source).returncode:
        return False
    actual_index = run(["git", "write-tree"], source, True).strip()
    with tempfile.TemporaryDirectory(prefix="gm8-port-upgrade-") as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        run(["git", "read-tree", REVISION], source, env=env)
        run(["git", "apply", "--cached", PATCH], source, env=env)
        current_tree = run(["git", "write-tree"], source, True, env).strip()
        for name, reversals in [("9530763", [TOUCH_UPGRADE]),
                                ("d06c76c", [TOUCH_UPGRADE, POWER_UPGRADE])]:
            run(["git", "read-tree", current_tree], source, env=env)
            for patch in reversals:
                run(["git", "apply", "--cached", "--reverse", patch], source, env=env)
            baseline_tree = run(["git", "write-tree"], source, True, env).strip()
            if actual_index != baseline_tree:
                continue
            baseline = run(["git", "diff", "--cached", "--binary", REVISION],
                           source, True, env)
            check = subprocess.run(["git", "apply", "--reverse", "--check", "-"],
                                   input=baseline, cwd=source, text=True, capture_output=True)
            if check.returncode:
                continue
            delta = run(["git", "diff", "--binary", baseline_tree, current_tree],
                        source, True, env)
            subprocess.run(["git", "apply", "--index", "--check", "-"],
                           input=delta, cwd=source, text=True, check=True)
            subprocess.run(["git", "apply", "--index", "-"],
                           input=delta, cwd=source, text=True, check=True)
            source_check(source)
            print(f"Upgraded the exact {name} checkpoint in place: {source}")
            return True
    return False


def prepare(source):
    if source.exists():
        try:
            source_check(source, quiet=True)
        except (ValueError, subprocess.CalledProcessError) as error:
            if upgrade_known_checkpoint(source):
                return
            raise ValueError("Existing source does not match this checkpoint. "
                             "For an older port, keep that checkout and choose a new "
                             "--source directory (for example gm8-kernel419-v2). "
                             "No reset was performed.") from error
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
    run([sys.executable, DEVICE / "tools/tests/test-gm8-power419.py",
         "--kernel", source, "--dtb", dtb, "--config", out / ".config"], env=env)
    run([sys.executable, DEVICE / "tools/tests/test-gm8-touch419.py",
         "--kernel", source, "--dtb", dtb, "--config", out / ".config"], env=env)
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
