# GM8 stock Pie comparison and isolated heap-profile trial

Status: source/configuration validation only. No Android build or phone
performance validation has been performed for this trial.

## Inputs and limits

The supplied stock bugreport identifies Android 9 / SDK 28, build
P.GM8.2102.B-d, a 3.18.120 kernel and Adreno 505 V331 graphics. Its boot uptime
is about 5h52m. This is distinct from the Lineage Android 12.1 / 3.18.124 / V415
captures and is not a synchronized same-app/same-cache performance comparison.
The source post-boot script came from a stock ROM package because the phone
denied adb pull. File contents do not prove every conditional branch executed.

The provided startup script SHA-256 is
b5c1603a880c99c9159232d4382f68b721039ab13e7cb7168b77b47c0ceba777.
Compared with the vendor memory candidate 84fc751, only these hunks differ:

1. Our candidate selects 1.5 GiB zRAM for the 3 GiB non-Go SoC 313, instead of
   the stock script's 1 GiB default.
2. Our candidate disables process_reclaim for SoC 313; stock follows the
   generic PPR enable branch.
3. Our existing vendor startup script omits stock's optional gamed start.

The common msm8937 / SoC 313 HMP scheduler, governor, core-control and memory
functions otherwise match. There is no evidence here of a missing secret
stock CPU tuning profile. Copying the entire stock script would reintroduce
the PPR behavior and remove the candidate zRAM change; it is not a repair.

## Runtime evidence

- Stock reports MemTotal 2,896,788 KiB and MemAvailable 1,533,512 KiB at the
  proc snapshot. It uses about 304 MiB logical swap out of 1 GiB at that point.
  A later dumpsys snapshot reports 297,636 KiB swapped and 130,976 KiB physical
  zRAM use. These are different moments, not one simultaneous memory census.
- Its framework summary is memory status critical, with only 8,205 KiB cached
  process PSS. There are 98 kernel LMK kill messages between 16:17:14 and
  16:29:54 in the captured log, mostly adj >=900, including app restart chains.
  This is substantial eviction activity, not evidence stock retains every app.
  The same capture contains roughly 1.3 GiB framework-counted kernel cache;
  that cache estimate is not all immediately free physical RAM.
- Stock's cached-process maximum is 32, as in the platform-default Lineage
  policy. Stock behavior is not explained by a fixed 16-process maximum.
- Stock /data is ext4 through dm-0. The current Lineage device fstab requires
  F2FS. This is another uncontrolled difference in startup/storage behavior;
  the report does not prove F2FS is defective. Do not format or convert user
  data merely to test a theory.
- Stock uses the same 192 MiB normal heap growth limit and 512 MiB large-heap
  maximum as the prior Lineage profile, but different heap utilization/free
  targets. A maximum heap is not preallocated RAM for every app.
- Kernel/framework memory accounting, app versions, active/cached processes,
  uptime and swap differ. Subtracting stock kernel Used RAM from Android 12's
  number does not establish a leak or a measured reclaimable saving.
- Stock's camera tombstones include CameraHardwareInterface::dump and
  unchecked HIDL FAILED_TRANSACTION aborts, followed by provider DEAD_OBJECT
  failures. This explains the observed diagnostic-call crash path; a full
  original trigger is not established. Avoid repeatedly invoking that camera
  dump while the camera is in use. These crashes do not show EIS was tested.

## One policy under test: match stock ART heap targets

| Property | Previous Lineage 4 GiB profile | Observed stock / this trial |
| --- | --- | --- |
| heapstartsize | 8m | 16m |
| heapgrowthlimit | 192m | 192m |
| heapsize | 512m | 512m |
| heaptargetutilization | 0.6 | 0.75 |
| heapminfree | 8m | 4m |
| heapmaxfree | 16m | 8m |

The inherited 4 GiB ART profile is replaced with configs/heap-gm8-pie.mk, with
these six observed values. This is a heap-policy experiment, not a promise to
recover a particular amount of RAM. A denser heap and smaller free targets can
reduce spare heap space, but can also cause more frequent GC and worsen
startup or frame time. The larger initial heap may affect startup separately.
Normal/large heap limits, JIT/AOT and compilation filters are unchanged.

The trial is based on device 59f8af9, retaining the earlier memory/graphics/power
candidate and existing signing wrapper. It does not include device 3f7c6cc's
bounded ODEX/VDEX prefetch policy: do not combine the trials before measurement.
If build/make still has the prior I/O experiment applied, restore its two
defaults to 104857600 with that branch's --restore helper before switching.
The build/sign helper does not reset these local platform edits automatically.
Preflight refuses a mixed baseline if either prefetch definition is not the
original single 104857600-byte value. This prevents a silent combined trial.

Use the same original release keys. The heap policy itself needs no Format
Data, but this is NOT an instruction to install Lineage over stock Pie while
retaining its data: cross-ROM signature/encryption/data compatibility is a
separate installation decision. Keep the working stock setup until there is
time for a controlled test.

After a full ROM build/install and reboot, check the six dalvik.vm.heap*
properties. Compare the same app versions and switching order, cold/warm
launch time, retained app state, GC pauses and battery/thermal state. Reject
the candidate if GC pauses, relaunches or battery cost worsen. A lower Settings
RAM average is not a sufficient acceptance criterion.

Host validation evaluates the real profile with GNU make and compares all six
values with the supplied stock getprop data; checks patch whitespace and the
single inheritance replacement. It does not execute ART GC on a phone.

Primary build reference: LineageOS/android_frameworks_native lineage-19.1,
build/phone-xhdpi-4096-dalvik-heap.mk. No raw bugreport, tombstone, account or
unique device identifier is published here.
