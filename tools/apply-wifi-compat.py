#!/usr/bin/env python3
"""Apply/check the paired GM8 kernel and supplicant WPA3-Personal patches."""

import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    device = Path(__file__).resolve().parents[1]
    projects = [
        ("kernel/gm/msm8937", "include/net/cfg80211.h",
         "patches/kernel_gm_msm8937/0001-gm8-wpa3-sae-external-auth.patch"),
        ("external/wpa_supplicant_8", "src/drivers/driver_nl80211.c",
         "patches/external_wpa_supplicant_8/0001-gm8-sae-connect-owner.patch"),
        ("kernel/gm/msm8937", "include/net/cfg80211.h",
         "patches/kernel_gm_msm8937/0002-gm8-recover-sae-auth-timeout.patch"),
        ("external/wpa_supplicant_8", "src/drivers/driver_nl80211.c",
         "patches/external_wpa_supplicant_8/0002-gm8-log-external-auth-result.patch"),
    ]
    missing = []
    for path, marker, relative_patch in projects:
        repo = args.top.resolve() / path
        patch = device / relative_patch
        if not (repo / marker).is_file():
            print(f"Missing WPA3 source: {repo / marker}", file=sys.stderr)
            return 1
        result = subprocess.run(["git", "apply", "--reverse", "--check", str(patch)],
                                cwd=repo, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"GM8 WPA3 patch already applied: {path}: {patch.name}")
            continue
        result = subprocess.run(["git", "apply", "--check", str(patch)], cwd=repo,
                                capture_output=True, text=True)
        if result.returncode:
            print(f"Incompatible/local changes in {path}; no patches applied.\n"
                  + result.stderr, file=sys.stderr)
            return 1
        missing.append((repo, patch))
    if args.check and missing:
        print("GM8 WPA3 patches missing; run python3 "
              "device/gm/GM8_sprout/tools/apply-wifi-compat.py", file=sys.stderr)
        return 1
    # Check both repositories before modifying either one.
    for repo, patch in missing:
        result = subprocess.run(["git", "apply", str(patch)], cwd=repo,
                                capture_output=True, text=True)
        if result.returncode:
            print(f"Could not apply {patch.name}; inspect source before retrying.\n"
                  + result.stderr, file=sys.stderr)
            return 1
        print(f"Applied GM8 WPA3 patch: {repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
