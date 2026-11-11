package com.android.server;

import android.net.INetd;
import android.os.RemoteException;
import android.os.ServiceSpecificException;
import java.util.ArrayList;
import java.util.List;

public class NetworkPolicyFixture {
    static void check(boolean value) { if (!value) throw new AssertionError(); }
    interface Operation { void run() throws Exception; }
    static void error(int expected, Operation action) throws Exception {
        try { action.run(); } catch (ServiceSpecificException e) { check(e.errorCode == expected); return; }
        throw new AssertionError("No expected error " + expected);
    }
    static class Dependencies extends BpfNetMaps.Dependencies {
        int loaded, initialized;
        boolean failLoad;
        @Override public void loadNativeLibrary() { loaded++; if (failLoad) throw new UnsatisfiedLinkError("fixture"); }
        @Override public void initializeNativeMaps() { initialized++; }
    }
    static class Netd implements INetd {
        List<String> calls = new ArrayList<>();
        int failure;
        boolean dead, replaceOk = true;
        void call(String name) throws RemoteException {
            calls.add(name);
            if (dead) throw new RemoteException("fixture");
            if (failure != 0) throw new ServiceSpecificException(failure, "fixture");
        }
        public void bandwidthAddNaughtyApp(int uid) throws RemoteException { call("bad+" + uid); }
        public void bandwidthRemoveNaughtyApp(int uid) throws RemoteException { call("bad-" + uid); }
        public void bandwidthAddNiceApp(int uid) throws RemoteException { call("good+" + uid); }
        public void bandwidthRemoveNiceApp(int uid) throws RemoteException { call("good-" + uid); }
        public void firewallEnableChildChain(int chain, boolean enable) throws RemoteException { call("chain" + chain + enable); }
        public void firewallSetUidRule(int chain, int uid, int rule) throws RemoteException { call("rule" + chain + ":" + uid + ":" + rule); }
        public boolean firewallReplaceUidChain(String name, boolean allow, int[] uids) throws RemoteException { call("replace" + name); return replaceOk; }
        public void firewallAddUidInterfaceRules(String iface, int[] uids) throws RemoteException { call("iif+"); }
        public void firewallRemoveUidInterfaceRules(int[] uids) throws RemoteException { call("iif-"); }
        public void trafficSetNetPermForUids(int permissions, int[] uids) throws RemoteException { call("permissions"); }
    }
    public static void main(String[] args) throws Exception {
        String mode = args[0];
        Dependencies deps = new Dependencies();
        if (mode.equals("load-failure")) {
            deps.failLoad = true;
            try { new BpfNetMaps(new Netd(), deps); throw new AssertionError(); }
            catch (UnsatisfiedLinkError expected) { check(deps.loaded == 1); }
            deps = new Dependencies();
        }
        Netd netd = new Netd();
        BpfNetMaps maps = new BpfNetMaps(netd, deps);
        if (mode.equals("pret")) {
            check(deps.loaded == 0 && deps.initialized == 0);
            maps.addUidInterfaceRules("tun0", new int[]{10001});
            maps.removeUidInterfaceRules(new int[]{10001});
            maps.setNetPermForUids(1, new int[]{10001});
            check(netd.calls.size() == 3);
            try { new BpfNetMaps(); throw new AssertionError(); } catch (IllegalArgumentException expected) { }
            return;
        }
        check(deps.loaded == 1);
        if (!mode.equals("legacy")) { check(deps.initialized == 1 && netd.calls.isEmpty()); return; }
        check(deps.initialized == 0);
        Dependencies second = new Dependencies();
        new BpfNetMaps(netd, second);
        check(second.loaded == 0 && second.initialized == 0);
        maps.addNaughtyApp(10001); maps.removeNaughtyApp(10001);
        maps.addNiceApp(10002); maps.removeNiceApp(10002);
        maps.setChildChain(1, true); maps.setUidRule(1, 10001, 1);
        check(maps.replaceUidChain("fw_dozable", true, new int[]{10001}) == 0);
        check(netd.calls.toString().equals("[bad+10001, bad-10001, good+10002, good-10002, chain1true, rule1:10001:1, replacefw_dozable]"));
        netd.failure = 22;
        error(22, () -> maps.addNiceApp(-1));
        check(maps.replaceUidChain("bad", true, new int[]{}) == 22);
        netd.failure = 0; netd.replaceOk = false;
        check(maps.replaceUidChain("fw_dozable", true, new int[]{}) == 5);
        netd.dead = true;
        error(5, () -> maps.setChildChain(1, false));
        check(maps.replaceUidChain("fw_dozable", true, new int[]{}) == 5);
        int calls = netd.calls.size();
        error(95, () -> maps.addUidInterfaceRules("tun0", new int[]{10001}));
        error(95, () -> maps.removeUidInterfaceRules(new int[]{10001}));
        error(95, () -> maps.swapActiveStatsMap());
        error(95, () -> maps.setNetPermForUids(1, new int[]{10001}));
        error(95, () -> maps.dump(null, false));
        check(netd.calls.size() == calls);
        BpfNetMaps missing = new BpfNetMaps(null, new Dependencies());
        error(19, () -> missing.setUidRule(1, 10001, 1));
        check(missing.replaceUidChain("fw_dozable", true, new int[]{}) == 19);
        new BpfNetMaps(); // On T legacy mode a null-netd query object is allowed.
    }
}
