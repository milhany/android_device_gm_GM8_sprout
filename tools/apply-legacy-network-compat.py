#!/usr/bin/env python3
"""Restore the paired Android 12.1 legacy BPF-loader/netd paths for GM8."""

import argparse
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--check", action="store_true", help="verify without modifying sources")
    args = parser.parse_args()
    top = args.top.resolve()
    version = top / "build/core/version_defaults.mk"
    if not version.is_file() or not re.search(
            r"^\s*PLATFORM_SDK_VERSION\s*:?=\s*32\s*$", version.read_text(), re.M):
        print("Legacy network compatibility requires Android 12.1 / SDK 32.", file=sys.stderr)
        return 1

    device = Path(__file__).resolve().parents[1]
    patches = [
        ("system/bpf", device / "patches/system_bpf/0001-gm8-legacy-bpf-loader.patch"),
        ("system/netd", device / "patches/system_netd/0001-gm8-legacy-traffic-accounting.patch"),
    ]

    def apply(repo, patch, *flags):
        return subprocess.run(["git", "apply", *flags, str(patch)], cwd=repo,
                              capture_output=True, text=True)

    pending = []
    for project, patch in patches:
        repo = top / project
        if not repo.is_dir() or not patch.is_file():
            print(f"Missing network source or patch: {project}", file=sys.stderr)
            return 1
        if apply(repo, patch, "--reverse", "--check").returncode == 0:
            continue
        result = apply(repo, patch, "--check")
        if result.returncode:
            print(f"{project} differs from the legacy patch; no files changed.\n"
                  + result.stderr, file=sys.stderr)
            return 1
        pending.append((repo, patch))

    if args.check and pending:
        print("GM8 legacy network patches are missing; run "
              "python3 device/gm/GM8_sprout/tools/apply-legacy-network-compat.py", file=sys.stderr)
        return 1
    # Validate both projects before modifying either. Never reset local work.
    applied = []
    for repo, patch in pending:
        result = apply(repo, patch)
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            for previous_repo, previous_patch in reversed(applied):
                rollback = apply(previous_repo, previous_patch, "--reverse")
                if rollback.returncode:
                    print("Rollback failed; inspect local network changes:\n" + rollback.stderr,
                          file=sys.stderr)
            return 1
        applied.append((repo, patch))
    print("GM8 legacy network patches applied." if pending else
          "GM8 legacy network patches are already applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
