#!/vendor/bin/sh
# Match the HAL to the driver that actually initialized. A DT node or a
# compiled-in module alone does not establish a successful driver probe.
# Do not force GPIO IDs, create device nodes, or start competing HALs.

fpc_present=0
sunwave_present=0
for irq in /sys/bus/platform/drivers/fpc1020/*/irq; do
    if [ -f "$irq" ]; then
        fpc_present=1
        break
    fi
done
if [ -c /dev/sunwave_fp ]; then
    sunwave_present=1
fi

case "$fpc_present:$sunwave_present" in
    1:0) sensor=fpc ;;
    0:1) sensor=sunwave ;;
    0:0) sensor=unknown ;;
    1:1) sensor=ambiguous ;;
esac

setprop vendor.gm8.fingerprint.sensor "$sensor" || exit 1
log -p i -t GM8Fingerprint "kernel driver selection: $sensor (fpc=$fpc_present sunwave=$sunwave_present)"
case "$sensor" in
    unknown|ambiguous)
        log -p e -t GM8Fingerprint "No unambiguous initialized fingerprint driver; keeping fingerprint HALs disabled"
        exit 1
        ;;
esac
