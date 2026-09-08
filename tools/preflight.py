#!/usr/bin/env python3
"""Read-only GM8 source checks; the Android build remains the module/ABI gate."""

import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[4],
                        help="Android source root (default: inferred from device/gm/GM8_sprout)")
    args = parser.parse_args()
    top = args.top.resolve()
    device = top / "device/gm/GM8_sprout"
    vendor = top / "vendor/gm/GM8_sprout"
    errors = []
    warnings = []

    required = [
        "build/envsetup.sh",
        "build/target/product/product_launched_with_o_mr1.mk",
        "vendor/lineage/config/lineage_sdk_common.mk",
        "device/lineage/sepolicy/common/sepolicy.mk",
        "device/qcom/sepolicy-legacy-um/SEPolicy.mk",
        "hardware/qcom-caf/common/fwk-detect/Android.bp",
        "tools/extract-utils/extract_utils.sh",
        "device/gm/GM8_sprout/gm_GM8_sprout.mk",
        "vendor/gm/GM8_sprout/GM8_sprout-vendor.mk",
        "kernel/gm/msm8937/Makefile",
        "kernel/gm/msm8937/arch/arm64/configs/msm8937-perf_defconfig",
        "prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/bin/aarch64-linux-android-gcc",
    ]
    for path in required:
        if not (top / path).is_file():
            errors.append(f"Missing dependency: {path}")
    for version in (27, 28, 29):
        if not (top / f"prebuilts/vndk/v{version}").is_dir():
            errors.append(f"Missing VNDK snapshot: prebuilts/vndk/v{version}")
    if not any((top / path).is_file() for path in (
            "vendor/gapps/arm64/arm64-vendor.mk", "vendor/partner_gms/products/gms.mk")):
        errors.append("GApps are required; run setup-gapps.sh with a recorded Android 11 commit.")

    xml_count = 0
    for path in device.rglob("*.xml"):
        try:
            ET.parse(path)
            xml_count += 1
        except ET.ParseError as exc:
            errors.append(f"Invalid XML: {path.relative_to(top)}: {exc}")
    for path in device.rglob("*.json"):
        try:
            json.loads(path.read_text())
        except (ValueError, OSError) as exc:
            errors.append(f"Invalid JSON: {path.relative_to(top)}: {exc}")

    # Check literal copy inputs in these two trees. Make conditionals, generated
    # outputs, inherited products and module providers are checked by `m nothing`.
    copies = 0
    for makefile, local_path in ((device / "device.mk", "device/gm/GM8_sprout"),
                                 (vendor / "GM8_sprout-vendor.mk", "vendor/gm/GM8_sprout")):
        if not makefile.is_file():
            continue
        for line_number, line in enumerate(makefile.read_text().splitlines(), 1):
            line = line.split("#", 1)[0].replace("$(LOCAL_PATH)", local_path)
            for source in re.findall(r"(?:^|\s)([^\s:]+):[^\s]+", line):
                if not source.startswith(("device/gm/GM8_sprout/", "vendor/gm/GM8_sprout/")):
                    continue
                if "$" in source:
                    continue
                copies += 1
                if not (top / source).is_file():
                    errors.append(f"Missing copy input at {makefile.relative_to(top)}:{line_number}: {source}")

    if not any((device / name).is_file() for name in (
            "default_wallpaper.jpg", "wallpaper.jpg", "wallpaper/default_wallpaper.jpg")):
        warnings.append("Stock wallpaper is absent; the framework wallpaper fallback will be used.")
    thermal = vendor / "proprietary/vendor/etc/thermal-engine.conf"
    if thermal.is_file() and not any(line.split("#", 1)[0].strip()
                                     for line in thermal.read_text().splitlines()):
        warnings.append("thermal-engine.conf has no policy; verify the active thermal implementation on hardware.")
    props = device / "vendor.prop"
    if props.is_file():
        match = re.search(r"^ro\.product\.first_api_level=(\d+)$", props.read_text(), re.M)
        launch = top / "build/target/product/product_launched_with_o_mr1.mk"
        if match and launch.is_file():
            shipping = re.search(r"^PRODUCT_SHIPPING_API_LEVEL\s*:?=\s*(\d+)", launch.read_text(), re.M)
            if shipping and match[1] != shipping[1]:
                warnings.append(f"First API mismatch: vendor.prop={match[1]}, launch product={shipping[1]}; verify stock launch metadata before release.")

    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print(f"Checked {xml_count} XML files and {copies} literal device/vendor copy inputs.")
    if errors:
        print(f"Preflight failed: {len(errors)} error(s).", file=sys.stderr)
        return 1
    print("Source checks passed. Next run m nothing and a full target-files build; review every warning in docs/PREBUILD.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
