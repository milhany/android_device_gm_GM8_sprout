#!/usr/bin/env python3
"""Read-only GM8 source checks; the Android build remains the module/ABI gate."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[4],
                        help="Android source root (default: inferred from device/gm/GM8_sprout)")
    parser.add_argument("--source-only", action="store_true",
                        help="check device/vendor inputs only; does not satisfy the build gate")
    args = parser.parse_args()
    top = args.top.resolve()
    device = top / "device/gm/GM8_sprout"
    vendor = top / "vendor/gm/GM8_sprout"
    errors = []
    warnings = []

    # The modem advertises RadioConfig 1.1 but rejects its preferred-data
    # command. Do not silently build the property without its framework hook.
    if not args.source_only:
        for helper in ("apply-radio-compat.py", "apply-wifi-keystore-compat.py",
                       "apply-legacy-network-compat.py"):
            check = subprocess.run(
                [sys.executable, str(device / "tools" / helper), "--top", str(top), "--check"],
                capture_output=True, text=True)
            if check.returncode:
                errors.append(check.stderr.strip() or f"GM8 {helper} check failed.")
        version_file = top / "build/core/version_defaults.mk"
        version = re.search(r"^\s*PLATFORM_SDK_VERSION\s*:?=\s*(\d+)\s*$",
                            version_file.read_text() if version_file.is_file() else "", re.M)
        if not version or version[1] != "32":
            errors.append("This branch requires a LineageOS 19.1 / Android 12.1 (SDK 32) source tree.")

        kernel_config = top / "kernel/gm/msm8937/arch/arm64/configs/msm8937-perf_defconfig"
        config = kernel_config.read_text() if kernel_config.is_file() else ""
        for feature in ("CONFIG_NETFILTER_XT_MATCH_QTAGUID", "CONFIG_NETFILTER_XT_MATCH_QUOTA2",
                        "CONFIG_NETFILTER_XT_MATCH_POLICY", "CONFIG_NETFILTER_XT_TARGET_MARK"):
            if not re.search(r"^" + feature + r"=y$", config, re.M):
                errors.append(f"Legacy network accounting requires built-in {feature}.")

    system_props = device / "system.prop"
    if not system_props.is_file() or not re.search(
            r"^ro\.kernel\.ebpf\.supported=false$", system_props.read_text(), re.M):
        errors.append("GM8 3.18 requires ro.kernel.ebpf.supported=false and its paired patches.")

    required = [
        "build/envsetup.sh",
        "build/target/product/product_launched_with_o.mk",
        "vendor/lineage/config/common_full_phone.mk",
        "device/lineage/sepolicy/common/sepolicy.mk",
        "device/qcom/sepolicy-legacy-um/SEPolicy.mk",
        "hardware/qcom-caf/common/fwk-detect/Android.bp",
        "hardware/qcom-caf/bootctrl/Android.bp",
        "tools/extract-utils/extract_utils.sh",
        "device/gm/GM8_sprout/lineage_GM8_sprout.mk",
        "device/gm/GM8_sprout/thermal/Android.bp",
        "device/gm/GM8_sprout/thermal/Sensors.cpp",
        "device/gm/GM8_sprout/thermal/Thermal.cpp",
        "vendor/gm/GM8_sprout/GM8_sprout-vendor.mk",
        "kernel/gm/msm8937/Makefile",
        "kernel/gm/msm8937/arch/arm64/configs/msm8937-perf_defconfig",
        "prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/bin/aarch64-linux-android-gcc",
    ]
    for path in required if not args.source_only else ():
        if not (top / path).is_file():
            errors.append(f"Missing dependency: {path}")
    for version in (28, 29, 30, 31) if not args.source_only else ():
        if not (top / f"prebuilts/vndk/v{version}").is_dir():
            errors.append(f"Missing VNDK snapshot: prebuilts/vndk/v{version}")
    if not args.source_only and not any((top / path).is_file() for path in (
            "vendor/gapps/arm64/arm64-vendor.mk", "vendor/partner_gms/products/gms.mk")):
        errors.append("GApps are required; run setup-gapps.sh with a recorded Android 12.1 commit.")
    if not args.source_only:
        # The ARM64 device snapshot includes the matching 32-bit ARMv8 ABI.
        for arch in ("arm", "arm64"):
            for variant in ("full", "lite"):
                path = (f"prebuilts/vndk/v29/arm64/arch-{arch}-armv8-a/shared/vndk-core/"
                        f"libprotobuf-cpp-{variant}.so")
                if not (top / path).is_file():
                    errors.append(f"Missing legacy protobuf ABI: {path}")

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

    try:
        power = json.loads((device / "configs/powerhint.json").read_text())
        nodes = {node["Name"]: node for node in power["Nodes"]}
        if len(nodes) != len(power["Nodes"]):
            errors.append("Duplicate powerhint node names.")
        for action in power["Actions"]:
            if action["Node"] not in nodes or action["Value"] not in nodes[action["Node"]]["Values"]:
                errors.append(f"Unknown powerhint node/value: {action}")
            if not isinstance(action["Duration"], int) or action["Duration"] < 0:
                errors.append(f"Invalid powerhint duration: {action}")
        if not any(action["PowerHint"] == "LOW_POWER" for action in power["Actions"]):
            errors.append("Missing LOW_POWER profile required by GM8's power HAL.")
        if "ro.hardware.thermal=gm8" not in (device / "vendor.prop").read_text().splitlines():
            errors.append("GM8 thermal sensor module is not selected in vendor.prop.")
    except (ValueError, KeyError, OSError) as exc:
        errors.append(f"Invalid power/thermal configuration: {exc}")

    dolby_manifest = vendor / "dolby/stock-manifest.json"
    if not dolby_manifest.is_file():
        errors.append("Missing stock Dolby manifest; sync the matching GM8 vendor branch.")
    else:
        try:
            for entry in json.loads(dolby_manifest.read_text())["files"]:
                blob = vendor / "proprietary" / entry["path"]
                if not blob.is_file() or hashlib.sha256(blob.read_bytes()).hexdigest() != entry["sha256"]:
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

    # QTI moved from product to system_ext. Copying the files without fixing
    # their embedded paths leaves DPM unstartable and shared Java libraries missing.
    for path in (vendor / "proprietary/system_ext/etc").rglob("*"):
        if path.suffix not in (".xml", ".rc", ".conf"):
            continue
        if re.search(r"/(?:system/)?product/", path.read_text()):
            errors.append(f"Stale QTI product path after relocation: {path.relative_to(vendor)}")

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

    thermal = vendor / "proprietary/vendor/etc/thermal-engine.conf"
    if thermal.is_file() and not any(line.split("#", 1)[0].strip()
                                     for line in thermal.read_text().splitlines()):
        warnings.append("thermal-engine.conf has no mitigation policy; thermal.gm8 reports sensors only. Verify kernel/firmware protection on hardware.")
    props = device / "vendor.prop"
    if props.is_file():
        match = re.search(r"^ro\.product\.first_api_level=(\d+)$", props.read_text(), re.M)
        launch = top / "build/target/product/product_launched_with_o.mk"
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
    if args.source_only:
        print("Device/vendor input checks passed. Full preflight, m nothing and Android builds remain required.")
    else:
        print("Source checks passed. Next run m nothing and a full target-files build; review every warning in docs/PREBUILD.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
