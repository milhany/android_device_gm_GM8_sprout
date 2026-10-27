# GM8 startup I/O experiment

Status: experimental; host validation is not a phone performance result.
Based on device 59f8af9 and companion memory vendor 84fc751. The kernel remains
the working GM8 3.18 tree. This branch changes only the ODEX/VDEX prefetch cap;
the memory/graphics/power settings inherited from the prior candidate remain.

The supplied 32 MiB transition trace retains about 18.19 seconds of events,
less than the requested 25 seconds. It has 43 mismatched scheduler-switch TID
import warnings, so fine-grained scheduler results have that limitation. Some
initial process names are absent. No unobserved parent/worker ownership is
invented. Per-thread blocked time is not equivalent to disk wait without a
blocked-reason stack, and simultaneous waits are not added as wall time.

Observed within that retained interval:

- TikTok bindApplication lasts about 7.018 seconds, followed by activityStart
  about 5.037 seconds. These are framework trace stages, not measured time to
  fully interactive content or a claim that this is entirely ROM overhead.
- Its main thread has about 7.416 seconds in D/DK blocked states across the
  retained trace, about 1.923 seconds running and 0.198 seconds in R/N runnable
  states. Blocking requires further attribution; D/DK is not a unique I/O cause.
- Physical MMC read requests total about 1622 MiB, counted once at issue, not
  by adding issue and completion totals. All 64,727 recorded completions report
  zero errors. This is heavy traffic, not evidence of defective eMMC.
- There are 257 direct reclaim slices, about 823 ms aggregate across threads,
  maximum about 44 ms. They do not alone explain every multi-second wait.
- Background and app worker threads also consume CPU during the transitions.
  Some process associations are missing; thread names do not prove which
  library implements a worker. Trace collection itself adds overhead.

The preceding memory snapshot reports 390,816 KiB logical swap used out of
1,572,860 KiB, with 110,004 KiB physical zRAM use. Its framework Used RAM is
1,491,266 KiB and cached-process PSS 739,574 KiB. This does not establish swap
exhaustion, a sustained system leak, or a reason to shrink the cached-app limit.

## Single policy under test

Lineage 19.1 build/make/target/product/runtime_libart.mk sets both
dalvik.vm.madvise.odexfile.size and dalvik.vm.madvise.vdexfile.size to
104857600 bytes. AndroidRuntime forwards the properties to ART. ART's
Runtime::MadviseFileForRange caps its MADV_WILLNEED calls to that many bytes
per mapping, in 128 KiB chunks. This is a speculative prefetch request, not
heap allocation, a guaranteed disk read or a process memory reservation.

apply-art-prefetch-compat.py reduces those two limits to 16777216 bytes each.
It leaves the ART image limit, heap/GC, JIT/AOT, dexopt filters, zRAM, LMK and
hardware protections unchanged. Actual accesses beyond the cap still use
normal demand paging. Reducing prefetch can also make necessary pages fault
later and worsen startup. 16 MiB is a test value, not an established optimum.

The trace did not enable the dalvik atrace category. Therefore it does not
directly attribute the MMC traffic to ART's madvising calls. This is a
source-supported hypothesis, not a confirmed cause or performance repair.
The trial must be rejected if launch/switch latency or video smoothness worsens.

The build helper applies the two source changes before preflight and records
the build/make local diff with the other project diffs. Preflight checks them.
The helper refuses unfamiliar values or duplicate definitions before writing,
and preserves unrelated local edits. It edits the original definition rather
than adding conflicting property definitions in another partition.

Build/sign using the existing one-command release helper and original keys.
Install the whole signed OTA; boot.img alone cannot install the system props.
No Format Data is requested. Compare the same app versions, battery/thermal
state and usage sequence; keep the graphics settings identical in both runs.

After reboot verify both properties are 16777216. Compare repeated cold/warm
launches and the same transition sequence with the previous signed release.
For another trace include dalvik and sched/sched_blocked_reason in addition
to the prior categories/events, if the kernel supports the latter. More than
one run is needed; cache warm-up can change I/O substantially.

To roll back the source experiment BEFORE switching to the prior device ref:

```sh
python3 device/gm/GM8_sprout/tools/apply-art-prefetch-compat.py --restore
```

Then restore the prior device ref and use the same release build command.
The experimental branch reapplies the trial at every build, so restoring the
properties without changing back to the prior branch is only temporary.

Primary sources: LineageOS/android_build lineage-19.1 runtime_libart.mk;
LineageOS/android_frameworks_base lineage-19.1 core/jni/AndroidRuntime.cpp;
LineageOS/android_art lineage-19.1 runtime/runtime.cc and runtime/oat_file.cc.
No raw trace or private app paths are included here.
