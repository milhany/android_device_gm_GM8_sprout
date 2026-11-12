# SDK33 restart and Bluetooth follow-up

## Confirmed findings

The November 12 device bugreport contains 15 system_server tombstones with the
same SIGABRT path:

```
AppProfiler.reportMemUsage
  Debug.getGpuTotalUsageKb
  libmeminfo::ReadProcessGpuUsageKb
  BpfMap constructor
  abort
```

The earlier GPU collector guard did not cover libmeminfo's independent readers.
The SDK33 runtime stack now also patches `system/memory/libmeminfo`:
`ReadPerProcessGpuMem` and `ReadProcessGpuUsageKb` return unavailable before
constructing BpfMap when `ro.kernel.ebpf.supported=false`. The total-GPU API
delegates to the second function and is covered too. No successful zero usage
is fabricated, the global BPF constructor is unchanged, and eBPF-capable devices
retain the existing reader behavior. Host/APEX/VNDK branches are unchanged.

Bluetooth Config logs show only GATT enabled; A2DP Source, AVRCP Target and HFP
Audio Gateway are disabled. SDK33 moved these selections to BluetoothProperties
sysprops, which were absent from the GM8 product. Explicit classic phone profile
properties now enable music, headset calls, media controls, phonebook/message
server, HID, object push and PAN roles. No LE Audio role is advertised.

The Bluetooth audio 2.0 provider registers successfully and AudioFlinger loads
the Bluetooth audio module. Failed probes for 2.1/2.2 or the optional alternate
implementation are not evidence that the working 2.0 provider is absent.

## Still open

| Finding | Evidence and next boundary |
| --- | --- |
| Keystore/Keymaster lockup | The matching vmlinux identifies app_access_lock at both blocked QSEE sites. The predecessor's multi-listener group-exit deadlock is reproduced and a scoped owner-identity repair is staged in the paired kernel. See QSEE-GROUP-EXIT-20.0.md. The trace omits active listener ownership; real firmware acceptance and the reason for service exit remain open. |
| LCD backlight | Disabling three display settings together restored blanking, but this did not isolate the cause. The permanent ambient-display suppression was withdrawn; see DISPLAY-SLEEP-20.0.md. |
| mm-pp-dpps | One separate null-PC SIGSEGV exists in this proprietary display-processing daemon. The stack does not identify a failed symbol. No blob replacement, daemon removal or panel command rewrite is justified by that trace alone. |
| Bluetooth package state | PackageManager repeatedly warns about the Bluetooth shared UID. Recheck after the restart loop is removed; do not edit packages.xml or format data to hide it. |

Application exceptions during repeated system_server death and restart do not
by themselves establish independent application bugs.

Before rebuilding the kernel, preserve a read-only capture from the current
build with `bash device/gm/GM8_sprout/tools/collect-qsee-symbols-20.0.sh`.
It records the existing kernel release, vmlinux hash and four QSEE function
disassemblies using GNU 4.9-compatible address ranges. It checks the two blocked
function layouts against this bugreport, without claiming full binary identity.
A layout mismatch means the old kernel binary is still needed for exact
instruction correlation. The printed qsee-build.txt contains no signing keys.

## Validation and installation boundary

The paired runtime installer checks every project before changing any source,
including libmeminfo, and supports a repeat run or a published predecessor.
Host checks exercise the actual GPU reader bodies with an aborting legacy BPF
fixture, normal map reads and failures, and host/APEX/VNDK compile branches.
Bluetooth checks compile the real A2DP/HFP/AVRCP selector methods with explicit
sysprop fixtures and validate the configured names against SDK33 definitions.
These checks are not an Android build or successful headset/device test.

Use the complete runtime build, then sign its new target-files with the existing
first-boot signing workflow. A boot-image-only update cannot contain this
libmeminfo or product-property change. No new key set or data format is needed
for the existing same-key Android 13 installation.

After updating and a full reboot, check repeated lock/wake cycles, leave the
phone running beyond the previous trigger, and exercise the memory-reporting
path (`adb shell dumpsys meminfo`). Check the three principal profile values:

```sh
adb shell getprop bluetooth.profile.a2dp.source.enabled
adb shell getprop bluetooth.profile.hfp.ag.enabled
adb shell getprop bluetooth.profile.avrcp.target.enabled
```

All should be `true`; then verify music, calls and media controls on the paired
device. Profile selection is fixed in source; connection and audio acceptance
remain a hardware test. Existing secure display settings are not reset by OTA.

## Reviewed primary sources

- AOSP `android-13.0.0_r75`, system/memory/libmeminfo/sysmeminfo.cpp.
- AOSP `android-13.0.0_r75`, system/libsysprop/srcs/android/sysprop/BluetoothProperties.sysprop.
- LineageOS `lineage-20.0`, packages/modules/Bluetooth A2dpService, HeadsetService,
  AvrcpTargetService and btservice/Config.java.
