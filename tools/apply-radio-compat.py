#!/usr/bin/env python3
"""Apply/check the GM8 Lineage 18.1 radio compatibility patch without resetting files."""

import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--check", action="store_true", help="only check that the patch is applied")
    args = parser.parse_args()
    repo = args.top.resolve() / "frameworks/opt/telephony"
    patch = Path(__file__).resolve().parents[1] / "patches/frameworks_opt_telephony/0001-gm8-legacy-data-switch.patch"
    if not (repo / "src/java/com/android/internal/telephony/RadioConfig.java").is_file():
        print(f"Missing telephony source: {repo}", file=sys.stderr)
        return 1

    def git_apply(*flags):
        return subprocess.run(["git", "apply", *flags, str(patch)], cwd=repo,
                              capture_output=True, text=True)

    if git_apply("--reverse", "--check").returncode == 0:
        print("GM8 legacy data-switch framework patch is already applied.")
        return 0
    if args.check:
        print("GM8 radio patch is missing or differs; run python3 "
              "device/gm/GM8_sprout/tools/apply-radio-compat.py", file=sys.stderr)
        return 1
    result = git_apply("--check")
    if result.returncode:
        print("Telephony source does not match the patch; no files changed.\n" + result.stderr,
              file=sys.stderr)
        return 1
    result = git_apply()
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    print("Applied GM8 legacy data-switch framework patch; keep this local change across syncs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
