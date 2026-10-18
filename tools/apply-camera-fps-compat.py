#!/usr/bin/env python3
"""Apply/check the GM8 Snapchat FPS experiment without resetting source files."""

import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo = args.top.resolve() / "frameworks/av"
    patch = (Path(__file__).resolve().parents[1] /
             "patches/frameworks_av/0001-gm8-snapchat-fixed-fps-test.patch")
    source = repo / "services/camera/libcameraservice/api2/CameraDeviceClient.cpp"
    if not source.is_file():
        print(f"Missing camera framework source: {source}", file=sys.stderr)
        return 1

    def git_apply(*flags):
        return subprocess.run(["git", "apply", *flags, str(patch)], cwd=repo,
                              capture_output=True, text=True)

    if git_apply("--reverse", "--check").returncode == 0:
        print("GM8 Snapchat FPS compatibility patch is already applied.")
        return 0
    if args.check:
        print("GM8 camera FPS patch is missing or differs; run python3 "
              "device/gm/GM8_sprout/tools/apply-camera-fps-compat.py", file=sys.stderr)
        return 1
    result = git_apply("--check")
    if result.returncode:
        print("Camera framework source does not match; no files changed.\n" + result.stderr,
              file=sys.stderr)
        return 1
    result = git_apply()
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    print("Applied GM8 Snapchat FPS experiment; keep this local change across syncs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
