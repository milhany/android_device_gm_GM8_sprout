#!/usr/bin/env python3
"""Apply/check the GM8 Lineage 19.1 process-group compatibility patch without resetting files."""

import argparse
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--check", action="store_true", help="only check that the patch is applied")
    args = parser.parse_args()
    top = args.top.resolve()
    version = top / "build/core/version_defaults.mk"
    if not version.is_file() or not re.search(
            r"^\s*PLATFORM_SDK_VERSION\s*:?=\s*32\s*$", version.read_text(), re.M):
        print("Processgroup compatibility requires Android 12.1 / SDK 32.", file=sys.stderr)
        return 1
    repo = top / "system/core"
    patch = Path(__file__).resolve().parents[1] / "patches/system_core/0001-gm8-cgroup-v1-process-tracking.patch"
    if not (repo / "libprocessgroup/processgroup.cpp").is_file():
        print(f"Missing processgroup source: {repo}", file=sys.stderr)
        return 1

    def git_apply(*flags):
        return subprocess.run(["git", "apply", *flags, str(patch)], cwd=repo,
                              capture_output=True, text=True)

    if git_apply("--reverse", "--check").returncode == 0:
        print("GM8 cgroup v1 process-tracking patch is already applied.")
        return 0
    if args.check:
        print("GM8 processgroup patch is missing or differs; run python3 "
              "device/gm/GM8_sprout/tools/apply-processgroup-compat.py", file=sys.stderr)
        return 1
    result = git_apply("--check")
    if result.returncode:
        print("Processgroup source does not match the patch; no files changed.\n" + result.stderr,
              file=sys.stderr)
        return 1
    result = git_apply()
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    print("Applied GM8 cgroup v1 process-tracking patch; keep this local change across syncs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
