# QTI permission XML providers on GM8 / Android 10

LineageOS 17.1 vendor/codeaurora/telephony supplies both the Java libraries
and permission XML modules for qti-telephony-hidl-wrapper and
qti-telephony-utils. The XML modules install under product/etc/permissions;
the library entries reference the corresponding product/framework jars.

The device selects these modules in PRODUCT_PACKAGES. The inherited vendor
makefile also declares raw copies to those same XML destinations, causing
Kati's overriding-commands error. After inheriting vendor, filter just these
two exact PRODUCT_COPY_FILES destinations. Keep both selected XML modules,
both Java libraries and every other vendor permission/copy entry.

Keeping this selection in device.mk avoids hand-editing or regenerating the
proprietary vendor tree and survives vendor makefile regeneration. The source
QTI directories/XML inputs are required by preflight.

Host GNU Make fixtures evaluated the actual before/after device/vendor inputs
and the actual QTI module definitions for both product and system/product
layouts: only two raw copies disappear, both module providers remain, and
other copy entries preserve their order/content. The wrapper XML's parsed
library declaration matches the vendor snapshot. Python syntax passed.
The full Android build and telephony/IMS behavior remain hardware/build gates.
