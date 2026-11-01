# GM8 power HAL on LineageOS 17.1

Use libperfmgr from system/extras/libperfmgr. It is vendor_available and
exports perfmgr/HintManager.h, so the existing proprietary Power HAL and
libdisppower-gm shared_libs dependencies continue to select the vendor
variant by the same module name. The duplicate device library copy is removed,
including its defaults, tests and config verifier definitions.

The consumers call the one-argument GetFromJSON factory, DoHint and EndHint.
These calls match the real 17.1 header; a host C++14 signature check passed
with stubs only for Android thread dependencies. The existing Nodes/Actions
JSON parser implementations match after comments/whitespace normalization,
including Property, HoldFd, ResetOnInit, values and duration handling.

The Q NodeLooperThread starts in onFirstRef. The removed copy used an explicit
Start call through a default factory argument. Consumers use the default
one-argument factory and do not depend on Start or IsHintSupported.

Power-hint settings and HAL consumers are unchanged by this source migration.
This does not validate actual sysfs nodes, boost behavior, battery drain or
a full Android build. Run m nothing and then the normal build gates.
