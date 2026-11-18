# GM8 SDK33 performance work

The target is predictable UI latency and useful process retention within the
device's physical memory budget. Free RAM alone is not a performance score.
Allocation, garbage collection, page-cache reclaim, compressed swap, storage
I/O, thermal throttling and application/service deadlocks must be distinguished.
No zero-jank or unlimited background-process guarantee is implied.

## Initial bounded change

The 3.18 zram implementation defaults to one LZO compression stream. The
single-stream backend serializes compression and cannot be converted into
the multistream backend after device initialization. The factory selects the
multistream backend only when max_comp_streams is greater than one.

Set max_comp_streams to four from the vendor init fs action, before the existing
post-boot script writes disksize and enables swap. This allows bounded parallel
compression on the eight-core SoC; extra stream workspaces are allocated as
needed up to the limit. This removes an avoidable serialization point but is
not evidence of a measured frame-rate or retention improvement on the phone.

The change does not enlarge ZRAM, change its algorithm, bypass low-memory
protection, alter cached-process limits, drop caches, pin all applications,
change CPU/GPU frequencies or modify thermal controls. The existing 1 GiB
ZRAM size and pressure protection remain the baseline for comparison.

After installing a build containing this change, verify:

```sh
adb shell cat /sys/block/zram0/max_comp_streams
```

Expected value: 4. Do not reset or swapoff an active ZRAM device to change it
on an already booted, memory-constrained phone.

## Measurement before further tuning

`tools/collect-performance-20.0.sh` captures a minute of ordinary app switching.
It collects process memory and graphics counters before and after the window,
then samples memory/swap/reclaim counters, CPU accounting, storage statistics,
ZRAM usage, CPU/GPU clocks and temperatures every two seconds. Existing logs
and up to five recent ANRs help separate a service wait from resource pressure.
It makes no performance-setting changes and does not read app databases or
keys. Dumps are bounded with timeout; unsupported optional nodes are skipped.

Compare equivalent workloads after boot/installation activity has settled:

- Application reloads and actual low-memory kill events.
- Added total/janky frame counters for the same applications.
- Swap-in/out, page scanning/refaults and CPU time spent in reclaim.
- ZRAM original/compressed sizes and actual physical memory cost.
- Storage busy time and temperature/frequency changes around a visible stall.

Heap slack, swap size/algorithm and adaptive-LMK thresholds are further tuning
candidates only after the baseline identifies the limiting resource. Protecting
every background process without accounting for swap/reclaim pressure can make
foreground latency worse. The host capture fixture and source ordering review
do not replace physical-device before/after tests.
