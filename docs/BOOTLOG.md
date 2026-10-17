# 2026-10-17 device follow-up

`log(10).txt` confirms Dolby `DAP ready: enabled=true profile=2` and rear camera
preview without the previous camera property denials. The owner separately
reports SIM2 mobile data working. These observations do not establish complete
hardware validation.

The follow-up cleanup gives only the three observed Wi-Fi TCP sysctls their own
SELinux label/write rule, uses MDSS's real `idle_notify` input in the power
service, explicitly declares file node types, and removes the unshipped
`gamed` service/start request. Host power tests exercise the real interaction
handler with filesystem and HintManager stubs; Android timing/SELinux still
requires device testing. Policy additions compile against the Android 11
reference policy with neverallows enabled, not a complete device policy build.

`log(20261017-062200).txt` then reports a separate unresolved Wi-Fi failure:
WCNSS and supplicant start, but `WifiThreadRunner.call()` repeatedly times out,
and `com.android.settings/.Settings$WifiSettings2Activity` gets an ANR. The log
does not include the blocked Wi-Fi thread's stack. The later `gm8-wifi.zip`
provides five snapshots proving that Wi-Fi waits in KeyStore HMAC generation
for its randomized MAC. See [WIFI_KEYSTORE.md](WIFI_KEYSTORE.md) for the scoped
per-network-store workaround and required runtime validation.
The TCP policy change is not claimed as a fix for this ANR. Do not format data
or erase Wi-Fi configurations to diagnose this without further evidence.

The WPA3 experiment is kept on `lineage-18.1-wpa3-test` in the matching GM8
repositories while ordinary Wi-Fi is investigated. It is not merged into
`lineage-18.1-rework` and cannot explain the already installed ROM's failure.

Google Play services' repeated `WRITE_DEVICE_CONFIG` permission exceptions
remain separate. No broad settings or `ctl.start` permission is granted.
