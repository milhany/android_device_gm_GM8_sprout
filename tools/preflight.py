#!/usr/bin/env python3
"""Read-only GM8 source checks; the Android build remains the module/ABI gate."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import subprocess
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[4],
                        help="Android source root (default: inferred from device/gm/GM8_sprout)")
    parser.add_argument("--metadata-only", action="store_true",
                        help="check source/XML and tracked input paths, not proprietary blob bytes or build dependencies")
    args = parser.parse_args()
    top = args.top.resolve()
    device = top / "device/gm/GM8_sprout"
    vendor = top / "vendor/gm/GM8_sprout"
    errors = []
    warnings = []

    if not args.metadata_only:
        version_file = top / "build/core/version_defaults.mk"
        version = version_file.read_text() if version_file.is_file() else ""
        if not re.search(r"^\s*PLATFORM_SDK_VERSION\s*:?=\s*29\s*$", version, re.M):
            errors.append("17.1 requires a separate Android 10 / SDK 29 checkout.")
    required = [
        "build/envsetup.sh",
        "build/target/product/product_launched_with_o_mr1.mk",
        "vendor/lineage/config/common_full_phone.mk",
        "device/lineage/sepolicy/common/sepolicy.mk",
        "device/qcom/sepolicy-legacy-um/sepolicy.mk",
        "hardware/qcom-caf/common/fwk-detect/Android.bp",
        "device/gm/GM8_sprout/lineage_GM8_sprout.mk",
        "vendor/gm/GM8_sprout/GM8_sprout-vendor.mk",
        "kernel/gm/msm8937/Makefile",
        "kernel/gm/msm8937/arch/arm64/configs/msm8937-perf_defconfig",
        "prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/bin/aarch64-linux-android-gcc",
    ]
    for path in required if not args.metadata_only else ():
        if not (top / path).is_file():
            errors.append(f"Missing dependency: {path}")
    for version in (27, 28) if not args.metadata_only else ():
        if not (top / f"prebuilts/vndk/v{version}").is_dir():
            errors.append(f"Missing VNDK snapshot: prebuilts/vndk/v{version}")
    # Initial bring-up is vanilla. Android 11/12 Google-apps trees are forbidden.
    product = (device / "lineage_GM8_sprout.mk").read_text()
    if re.search(r"^\$\(call inherit-product, vendor/(?:gapps|partner_gms)/", product, re.M):
        errors.append("Do not inherit unverified Google apps in this Android 10 baseline.")
    make = (device / "device.mk").read_text()
    for bad in ("android.hardware.audio@6.0-impl", "android.hardware.audio.effect@6.0-impl",
                "android.hardware.drm@1.3-service.clearkey", "android.hardware.soundtrigger@2.2-service"):
        if bad in make:
            errors.append("Android 11-only module in 17.1 product: " + bad)
    if "ro.lmk.use_psi=" in (device / "system.prop").read_text():
        errors.append("Do not import the unvalidated 19.1 LMKD experiment into this baseline.")
    manifest = ET.parse(device / "configs/vintf/manifest.xml").getroot()
    for name in ("android.hardware.audio", "android.hardware.audio.effect"):
        versions = [h.findtext("version") for h in manifest.findall("hal") if h.findtext("name") == name]
        if versions != ["5.0"]:
            errors.append("Expected Android 10 audio HIDL 5.0: " + name)
    vendor_inputs = set()
    if args.metadata_only:
        vendor_inputs = set(subprocess.check_output(
            ["git", "-C", str(vendor), "ls-tree", "-r", "--name-only", "HEAD"], text=True).splitlines())

    def available(path):
        if path.is_file():
            return True
        return args.metadata_only and path.is_relative_to(vendor) and str(path.relative_to(vendor)) in vendor_inputs

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

    dolby_manifest = vendor / "dolby/stock-manifest.json"
    if not dolby_manifest.is_file():
        errors.append("Missing stock Dolby manifest; sync the matching GM8 vendor branch.")
    else:
        try:
            for entry in json.loads(dolby_manifest.read_text())["files"]:
                blob = vendor / "proprietary" / entry["path"]
                if not available(blob) or (not args.metadata_only and
                        hashlib.sha256(blob.read_bytes()).hexdigest() != entry["sha256"]):
                    errors.append(f"Missing or mismatched stock Dolby blob: {entry['path']}")
        except (ValueError, KeyError, OSError) as exc:
            errors.append(f"Invalid stock Dolby manifest: {exc}")

    effects = device / "configs/audio/audio_effects.xml"
    try:
        root = ET.parse(effects).getroot()
        ns = {"a": "http://schemas.android.com/audio/audio_effects_conf/v2_0"}
        libraries = {entry.attrib["name"] for entry in root.findall("a:libraries/a:library", ns)}
        for effect in root.findall("a:effects/a:effect", ns):
            if effect.attrib.get("library") not in libraries:
                errors.append(f"Unknown audio effect library: {effect.attrib}")
    except (ET.ParseError, OSError, KeyError) as exc:
        errors.append(f"Cannot validate audio effect libraries: {exc}")

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
                if not available(top / source):
                    errors.append(f"Missing copy input at {makefile.relative_to(top)}:{line_number}: {source}")

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
    if args.metadata_only:
        print("Metadata checks passed; binary hashes, Android modules, build and hardware are NOT validated.")
    else:
        print("Source checks passed. Next run m nothing and target-files; this is not a hardware validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
