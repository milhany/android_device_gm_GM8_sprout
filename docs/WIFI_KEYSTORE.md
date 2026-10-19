# GM8 Wi-Fi MAC generation / KeyStore hang

The 2026-10-17 `gm8-wifi.zip` contains five ANR snapshots with Wi-Fi blocked at:

```
WifiHandlerThread
  WifiConfigManager.getPersistentMacAddress
  MacAddressUtil.generateAndPersistNewMacRandomizationSecret
  AndroidKeyStoreKeyGeneratorSpi.engineGenerateKey
  KeyStore.generateKeyInternal
  CompletableFuture.get
```

The first two snapshots share the same thread runtime counters minutes apart;
later snapshots show the same wait after a restart. The Keymaster 3.0 service
also waits in `__qseecom_process_incomplete_cmd`. This establishes a stuck
Wi-Fi HMAC key request, not the exact TrustZone/firmware/provisioning defect.
WCNSS and supplicant have started. TCP sysctl permissions do not explain this
particular wait.

## Scoped compatibility path

GM8 sets `wifi.mac_rand_no_keystore=true`. The existing `wifi.` prefix uses the
platform `wifi_prop` context; no broad SELinux grant is needed. Before making
a KeyStore request, the Wi-Fi framework patch:

- Reuses a saved mapping, or the configuration's valid randomized MAC.
- Otherwise calls Android's existing `MacAddressUtils.createRandomUnicastAddress`
  (SecureRandom, locally administered, unicast).
- Persists the address in the existing per-network mapping store for reuse on
  normal network saves/reloads, rather than using a fixed or public SSID hash.
- Returns null for Soft AP hash requests before KeyStore access; its existing
  caller already falls back to a locally generated random MAC.

Other products retain the original branch. This does not disable randomization,
delete credentials, default to the factory MAC, replace global KeyStore, or
repair the underlying Keymaster service. PSK/SAE networks bypass this specific
hang; certificate-backed enterprise networks and unrelated consumers can still
encounter KeyStore faults.

## Build and test

After syncing `lineage-19.1`, run from the Android source root:

```sh
python3 device/gm/GM8_sprout/tools/apply-radio-compat.py
python3 device/gm/GM8_sprout/tools/apply-wifi-keystore-compat.py
python3 device/gm/GM8_sprout/tools/preflight.py
source build/envsetup.sh
lunch lineage_GM8_sprout-userdebug
m service-wifi -j32
m bacon -j32
```

The helper checks before applying, accepts an already applied patch, and refuses
divergent source without resetting changes. Preflight rejects a missing patch.
Install the full matching ROM to apply the framework and property together.
No data wipe, Wi-Fi-store deletion or global permissive policy is required.
Setting this property alone on the old framework cannot fix the active wait.

The original Android 11 Java checks compile the real modified MacAddressUtil and execute the
real getPersistentMacAddress method with framework MAC classes and isolated
KeyStore/property/config fixtures. Checks cover zero KeyStore calls with the
flag, per-network isolation, saved-address reuse, mapping reload, malformed
mapping repair, Soft AP bypass and the unchanged default KeyStore route.
The complete service build and physical phone reconnect remain required.

On the installed ROM, `adb shell getprop wifi.mac_rand_no_keystore` should
return `true`. Connect a WPA2 network, verify IP traffic with mobile data off,
reconnect after reboot, and check the randomized MAC stays stable for that
network. The Wi-Fi settings must stay responsive without the old ANR. WPA3
stays in its separate experiment until this ordinary Wi-Fi check passes.

## Android 12.1 port

This branch patches packages/modules/Wifi (not frameworks/opt/net/wifi),
uses WifiConfiguration.getNetworkKey(), and keeps the same property opt-in.
The patches were rebased on actual 19.1 files. Android 11 runtime success
does not establish 19.1 success; reconnect, persistent MAC and Soft AP need
retesting on the new ROM. See PREBUILD.md for build gates.
