# GM8 performance audit against LineageOS MSM8937 sources

## Reference versions and scope

GM8 baseline: device c6b42bb3cceae6ce4c3bb7faf269ed775862f8a8, vendor
a22c80f76f1bc90d07d627bd43af8e959e3b22bc, kernel
79997531c5a3b9cf52d608c09e1c584e379f1ff9. The SoC is 313/MSM8940;
msm8937 is the CAF family name. Both clusters are Cortex-A53, with the faster
GM8 policy on CPUs 0-3 and the lower-frequency policy on CPUs 4-7.

| Reference | Pinned commit | Comparison role |
|---|---|---|
| LineageOS/android_device_motorola_msm8937-common, lineage-17.1 | 0f4cb8cfb6826da610ef1ab8b5ea2615e89df942 | Same Android generation; its referenced kernel/motorola/msm8953 lineage-17.1 Makefile is also 3.18.124 |
| LineageOS/android_device_xiaomi_msm8937-common, lineage-16.0 | 84a0e414d9a4402902de9bef9899ae4223ed0476 | HMP/cpuset and vendor-stack reference; Android 9, not a Q drop-in |
| LineageOS/android_device_xiaomi_santoni, lineage-16.0 | f5aaaa4a43cf1e848ad51593c80a35a90c897fb1 | MSM8940 device-specific additions; no 17.1 branch was found in these LineageOS Xiaomi repositories |

Reviewed board/product configuration, properties, init/fstab/post-boot paths,
power hints, relevant kernel configuration, media declarations and the supplied
runtime logs/memory/dexopt/top snapshots. This is a source comparison, not a
full Android build, binary ABI certification or hardware acceptance test. A
reference's presence under LineageOS does not mean its settings fit GM8.

## Findings and decisions

| Area | Evidence | Decision |
|---|---|---|
| CPU placement | The actual GM8 capture reports foreground, background, system-background, restricted and top-app all 0-7. Q init creates these as all-CPU placeholders and explicitly requires device specialization. The GM8 vendor SoC-313 path configures HMP but does not specialize those masks. Xiaomi's power rc assigns background/system-background to 4-6 and keeps top-app 0-7. | Candidate: background/system-background/restricted 4-7; foreground/top-app 0-7. Keep all four power cores available rather than copy Xiaomi's CPU7 reservation. This reduces eligible background CPUs; it does not guarantee a measured speedup or fix every launch. |
| Power HAL | Motorola Q selects Qualcomm power@1.2 and powerhint.xml; GM8 uses custom power@1.3/libperfmgr plus stock media perf clients. Motorola also makes the msm_performance CPU-min endpoint read-only. | Investigate competing requests with live values. Do not copy opcodes or endpoint permissions, disable media clients, extend every boost or change voltages without evidence. |
| Kernel/scheduler | Motorola's reference kernel is also 3.18.124. GM8 has QHMP, cpusets, memcg/swap accounting and CFQ groups; unsupported SchedTune actions were already removed. | Android 10 plus kernel 3.18 alone is not a diagnosis. Preserve the proven CPU topology and limits. A 4.19 port is not a prerequisite for this experiment. |
| Heap/RAM | GM8 stock-derived 16m/192m/512m/.75/4m/8m; Motorola common uses a 256m growth limit. Runtime reports about 1.47 GiB used and 1.48 GiB Free RAM including cached processes/kernel pages. | No evidence here for shrinking the heap, enabling low_ram or increasing cache killing. Free RAM in dumpsys is not identical to MemAvailable. |
| ZRAM/reclaim | 1 GiB logical ZRAM, about 86.5 MiB physical for 271 MiB swapped data. Stock-derived post-boot enables process reclaim and swappiness 100; Motorola's script differs. | Collect live pressure/major-fault/reclaim deltas. Do not increase ZRAM or change several reclaim policies from an idle snapshot. The vendor's separate 200 MB disk-swap code is conditional on <=1 GiB devices; it does not select GM8's 3 GiB path. Verify actual /proc/swaps when readable. |
| ART | Most tested user apps already have speed-profile. Instagram and a TikTok split show verify/reason=boot. | The separate 0980956 dexopt candidate remains isolated. It is not included in this CPU-placement branch, so the temporary test can change one factor at a time. |
| Graphics | The driver logs a missing EGL 1.5 API, Chrome EGL_BAD_ATTRIBUTE and a long displayed interval. Both references also enable framebuffer UBWC and declare Vulkan 1.1. | Reference declarations do not prove GM8 runtime capabilities. Establish actual renderer, compression state and scheduling/GPU waits before changing blobs or blanket-disabling hardware composition. |
| Thermal | Pinned GM8 thermal-engine.conf contains only placeholder comments. Its stock thermal HAL and kernel thermal/BCL support remain enabled. Xiaomi's actual policy uses other voltage/frequency tables and sensor assumptions. Motorola common selects the HAL and daemon, but its loaded per-device policy was not established here. | This remains an open validation issue. Do not copy Xiaomi thermal thresholds, disable protections or promise battery gains from undervolt. Read sensor identities/units and active limits first. |
| F2FS/storage | GM8 /data is F2FS with discard; system/vendor remain ext4. Motorola adds other options including nobarrier and has a separate ZRAM fstab entry. | Do not copy nobarrier, encryption or partition layout. Read mount options, free space, queue and counters; no write benchmark, forced trim, cache dropping or filesystem conversion is needed for this audit. Actual eMMC health is unknown. |
| Media/camera/IMS/Dolby | GM8 and Motorola declare Qualcomm AVC/HEVC paths. GM8's video XML includes resolve through its vendor copy list. The latest log has working Wi-Fi, no SIM for IMS acceptance, and no Dolby-ready marker. | No evidence that a wholesale HAL replacement fixes general app launch. Codec XML limits alone do not prove runtime hardware decoding, and MOV is a container. Keep call/camera/Dolby testing separate from CPU placement. |

## Prepared CPU-placement candidate

The init.gm.rc change only assigns cpusets on boot. Source and target-files
checks reject all-core or reversed background masks, a restricted top-app,
duplicate overrides and placement outside the boot action. Existing security
policy, clocks, voltage, core_ctl, thermal control and application data are
unchanged. Host checks passed; migration behavior and performance on GM8 are
not yet tested.

To avoid another flash, tools/test-cpusets-17.1.sh provides a temporary test:
it requires adb root on the Q userdebug build, checks GM8/SoC313 and actual CPU
policy membership, saves the three original masks under /dev (tmpfs), and only
then changes those three masks. It refuses unexpected topology or already
customized foreground/top-app masks. Restore uses the saved masks; reboot
also removes this temporary experiment. An application finishing background
work more slowly is a possible tradeoff; compare app switching and foreground
launches under the same conditions rather than using a single idle snapshot.

Windows CMD, after downloading the script from this candidate branch:

```bat
adb root
adb wait-for-device
adb shell sh -s -- apply < gm8-cpuset-test.sh
```

If adb root is unavailable, stop there: the script will refuse writes and no
permission bypass or new root installation is required for the source audit.
To undo while the same boot is running:

```bat
adb shell sh -s -- restore < gm8-cpuset-test.sh
```

Use tools/collect-performance-17.1.sh through stdin to read CPU masks/governors,
GPU policy, memory/reclaim, F2FS/eMMC counters and thermal values. It neither
requests root nor changes settings; protected/missing nodes are reported as
unavailable. Health attributes may not be exposed by this kernel. It avoids
CID, serial, firmware bytes, keys and application content. Do not publish the
user's raw runtime captures.

```bat
adb shell sh -s < gm8-perf-audit.sh > gm8-perf-audit.txt
```

## Primary sources

- [Motorola Q common tree](https://github.com/LineageOS/android_device_motorola_msm8937-common/tree/0f4cb8cfb6826da610ef1ab8b5ea2615e89df942): BoardConfigCommon.mk, msm8937.mk, properties.mk, configs/powerhint.xml, rootdir/etc and rootdir/bin/init.qcom.post_boot.sh.
- [Xiaomi Pie common tree](https://github.com/LineageOS/android_device_xiaomi_msm8937-common/tree/84a0e414d9a4402902de9bef9899ae4223ed0476): rootdir/init.qcom.power.rc, configs/thermal-engine.conf, vendor_prop.mk and board/product configuration.
- [Santoni Pie tree](https://github.com/LineageOS/android_device_xiaomi_santoni/tree/f5aaaa4a43cf1e848ad51593c80a35a90c897fb1): device.mk and BoardConfig.mk.
- [Q initial cpuset setup](https://github.com/LineageOS/android_system_core/blob/lineage-17.1/rootdir/init.rc): all-CPU placeholders and the device-specialization requirement.
