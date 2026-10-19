#!/usr/bin/env python3
"""Host-test actual patched 19.1 methods with isolated property/MAC/HAL fixtures.

Pass --top to a prepared Android 12.1 tree. This compiles extracted real methods,
not the whole Android services; run their Android builds and device tests too.
Requires a JDK (java with jdk.compiler); does not change the source tree.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


def method(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


FIXTURE = r'''
import java.util.*;
import java.security.*;
import javax.crypto.*;
public class CompatTest {
 static class SystemProperties {
  static final Map<String,Boolean> values=new HashMap<>();
  static boolean getBoolean(String key,boolean fallback){return values.getOrDefault(key,fallback);}
 }
 static class Process {static final int WIFI_UID=1010;}
 static class Log {static void e(String t,String m){} static void e(String t,String m,Exception e){}
  static void wtf(String t,String m){} }
 static class MacAddress {
  final String value; private MacAddress(String s){value=s.toLowerCase(Locale.ROOT);}
  static MacAddress fromString(String s){
   if(!s.matches("[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}"))throw new IllegalArgumentException();
   return new MacAddress(s);
  }
  public String toString(){return value;}
  public boolean equals(Object o){return o instanceof MacAddress && value.equals(((MacAddress)o).value);}
  public int hashCode(){return value.hashCode();}
 }
 static class MacAddressUtils {
  static int sequence=1;
  static MacAddress createRandomUnicastAddress(){return MacAddress.fromString(String.format("02:11:22:33:44:%02x",sequence++));}
 }
 static final MacAddress DEFAULT_MAC_ADDRESS=MacAddress.fromString("02:00:00:00:00:00");
 static class WifiConfiguration {
  final String key; MacAddress mac=DEFAULT_MAC_ADDRESS;
  WifiConfiguration(String k){key=k;}
  String getNetworkKey(){return key;} MacAddress getRandomizedMacAddress(){return mac;}
  static boolean isValidMacAddressForRandomization(MacAddress m){
   return m!=null && (Integer.parseInt(m.value.substring(0,2),16)&3)==2 && !DEFAULT_MAC_ADDRESS.equals(m);
  }
 }
 static class AndroidKeyStoreProvider {
  static int calls;
  static KeyStore getKeyStoreForUid(int uid) throws KeyStoreException,NoSuchProviderException {
   ++calls;
   try {KeyStore k=KeyStore.getInstance(KeyStore.getDefaultType());k.load(null,null);return k;}
   catch(Exception e){throw new KeyStoreException(e);}
  }
 }
 static class MacAddressUtil {
  static final String TAG="mac"; int generated;
  Key generateAndPersistNewMacRandomizationSecret(int uid,String alias){++generated;return null;}
  Mac obtainMacRandHashFunction(int uid){return obtainMacRandHashFunctionInternal(uid,"client");}
  Mac obtainMacRandHashFunctionForSap(int uid){return obtainMacRandHashFunctionInternal(uid,"sap");}
  MacAddress calculatePersistentMac(String key,Mac hash){return null;}
  /* REAL_MAC_METHOD */
 }
 static class WifiConfigManager {
  static final String TAG="wifi";
  Map<String,String> mRandomizedMacAddressMapping=new HashMap<>();
  MacAddressUtil mMacAddressUtil=new MacAddressUtil();
  /* REAL_WIFI_METHOD */
 }
 interface IRadioConfig {}
 static class Version {int value=11;boolean greaterOrEqual(Version other){return value>=other.value;}}
 static class RadioConfig {
  static final Version RADIO_CONFIG_HAL_VERSION_1_1=new Version();
  Version mRadioConfigVersion=new Version(); int calls; boolean present=true;
  IRadioConfig getRadioConfigProxy(Object result){++calls;return present?new IRadioConfig(){}:null;}
  /* REAL_RADIO_METHOD */
 }
 static void check(boolean value,String reason){if(!value)throw new AssertionError(reason);}
 public static void main(String[] args){
  final String wifiFlag="wifi.mac_rand_no_keystore", radioFlag="ro.ril.use_legacy_data_switch";
  SystemProperties.values.put(wifiFlag,true);
  WifiConfigManager w=new WifiConfigManager();
  WifiConfiguration a=new WifiConfiguration("network-a");
  MacAddress first=w.getPersistentMacAddress(a);
  check(WifiConfiguration.isValidMacAddressForRandomization(first),"generated MAC validity");
  check(first.equals(w.getPersistentMacAddress(a)),"stable per-network mapping");
  check(AndroidKeyStoreProvider.calls==0,"opt-in must not touch KeyStore");
  WifiConfiguration b=new WifiConfiguration("network-b");
  check(!first.equals(w.getPersistentMacAddress(b)),"different networks must have different mappings");
  WifiConfiguration c=new WifiConfiguration("network-c");c.mac=MacAddress.fromString("02:ab:cd:12:34:56");
  check(c.mac.equals(w.getPersistentMacAddress(c)),"reuse valid configuration MAC");
  WifiConfiguration bad=new WifiConfiguration("bad");
  w.mRandomizedMacAddressMapping.put(bad.key,"malformed");
  check(WifiConfiguration.isValidMacAddressForRandomization(w.getPersistentMacAddress(bad)),"repair malformed mapping");
  WifiConfiguration invalid=new WifiConfiguration("multicast");invalid.mac=MacAddress.fromString("03:ab:cd:12:34:56");
  check(WifiConfiguration.isValidMacAddressForRandomization(w.getPersistentMacAddress(invalid)),"reject invalid config MAC");
  WifiConfigManager reload=new WifiConfigManager();reload.mRandomizedMacAddressMapping.putAll(w.mRandomizedMacAddressMapping);
  check(first.equals(reload.getPersistentMacAddress(new WifiConfiguration(a.key))),"mapping survives reload");
  check(w.mMacAddressUtil.obtainMacRandHashFunctionForSap(Process.WIFI_UID)==null,"Soft AP fallback signal");
  check(AndroidKeyStoreProvider.calls==0,"Soft AP must not touch KeyStore");
  SystemProperties.values.remove(wifiFlag);
  w.getPersistentMacAddress(new WifiConfiguration("normal-default"));
  check(AndroidKeyStoreProvider.calls==2,"default route must retain both original KeyStore attempts");
  w.mMacAddressUtil.obtainMacRandHashFunctionForSap(Process.WIFI_UID);
  check(AndroidKeyStoreProvider.calls==3,"default Soft AP route must retain KeyStore");
  RadioConfig radio=new RadioConfig();
  check(radio.isSetPreferredDataCommandSupported(),"default 1.1 HAL supported");
  radio.mRadioConfigVersion.value=10;check(!radio.isSetPreferredDataCommandSupported(),"default 1.0 HAL unsupported");
  radio.present=false;check(!radio.isSetPreferredDataCommandSupported(),"absent HAL unsupported");
  SystemProperties.values.put(radioFlag,true);radio.calls=0;radio.present=true;radio.mRadioConfigVersion.value=11;
  check(!radio.isSetPreferredDataCommandSupported() && radio.calls==0,"legacy opt-in bypasses preferred-data capability");
  System.out.println("Actual 19.1 methods: stable/isolated MACs, reload/repair, zero KeyStore calls, default/Soft AP routes and legacy radio opt-in passed.");
 }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, required=True)
    args = parser.parse_args()
    top = args.top.resolve()
    wifi = top / "packages/modules/Wifi/service/java/com/android/server/wifi"
    radio = top / "frameworks/opt/telephony/src/java/com/android/internal/telephony/RadioConfig.java"
    program = FIXTURE.replace("/* REAL_WIFI_METHOD */", method(
        (wifi / "WifiConfigManager.java").read_text(),
        "public MacAddress getPersistentMacAddress(WifiConfiguration config)"))
    program = program.replace("/* REAL_MAC_METHOD */", method(
        (wifi / "MacAddressUtil.java").read_text(),
        "private Mac obtainMacRandHashFunctionInternal(int uid, String alias)"))
    program = program.replace("/* REAL_RADIO_METHOD */", method(
        radio.read_text(), "public boolean isSetPreferredDataCommandSupported()"))
    with tempfile.TemporaryDirectory(prefix="gm8-19-compat-") as directory:
        source = Path(directory) / "CompatTest.java"
        source.write_text(program)
        subprocess.run(["java", "com.sun.tools.javac.Main", "-d", directory, str(source)],
                       check=True, timeout=30)
        subprocess.run(["java", "-ea", "-cp", directory, "CompatTest"], check=True, timeout=15)


if __name__ == "__main__":
    main()
