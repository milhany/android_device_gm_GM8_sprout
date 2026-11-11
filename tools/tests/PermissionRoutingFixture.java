package com.android.server;

import android.net.INetd;
import android.os.RemoteException;
import android.os.ServiceSpecificException;
import android.util.Log;
import android.util.SparseIntArray;
import java.util.ArrayList;
import java.util.Arrays;

/** Actual BpfNetMaps and PermissionMonitor method with Binder/Android fixtures. */
public class PermissionRoutingFixture {
    static final int PERMISSION_NONE = 0, PERMISSION_INTERNET = 4,
            PERMISSION_UPDATE_DEVICE_STATS = 8, PERMISSION_UNINSTALLED = -1;
    static void check(boolean value) { if (!value) throw new AssertionError(); }
    static class Netd extends NetworkPolicyFixture.Netd {
        ArrayList<String> permissions = new ArrayList<>();
        RemoteException remote;
        ServiceSpecificException service;
        @Override public void trafficSetNetPermForUids(int mask, int[] appIds) throws RemoteException {
            permissions.add(mask + ":" + Arrays.toString(appIds));
            if (remote != null) throw remote;
            if (service != null) throw service;
        }
    }
    static class Monitor {
        static final String TAG = "PermissionMonitor";
        final BpfNetMaps mBpfNetMaps;
        Monitor(BpfNetMaps maps) { mBpfNetMaps = maps; }
        static int[] toIntArray(ArrayList<Integer> list) {
            int[] values = new int[list.size()];
            for (int i = 0; i < values.length; i++) values[i] = list.get(i);
            return values;
        }
        // ACTUAL_PERMISSION_MONITOR_METHOD
    }
    public static void main(String[] args) throws Exception {
        String mode = args[0];
        Netd netd = new Netd();
        NetworkPolicyFixture.Dependencies deps = new NetworkPolicyFixture.Dependencies();
        BpfNetMaps maps = new BpfNetMaps(netd, deps);
        if (mode.equals("modern") || mode.equals("default")) {
            check(deps.loaded == 1 && deps.initialized == 1);
            try { maps.setNetPermForUids(8, new int[]{10001}); throw new AssertionError(); }
            catch (UnsatisfiedLinkError expected) { } // JNI is deliberately absent in the fixture.
            check(netd.permissions.isEmpty());
            return;
        }
        check(deps.loaded == (mode.equals("pret") ? 0 : 1) && deps.initialized == 0);
        maps.setNetPermForUids(8, new int[]{10001, 10002});
        check(netd.permissions.toString().equals("[8:[10001, 10002]]"));
        netd.permissions.clear();
        Monitor monitor = new Monitor(maps);
        SparseIntArray batch = new SparseIntArray();
        batch.put(10002, 4); batch.put(10005, -1); batch.put(10001, 12);
        batch.put(10004, 0); batch.put(10003, 8); batch.put(10006, 12);
        monitor.sendAppIdsTrafficPermission(batch);
        check(netd.permissions.toString().equals(
                "[12:[10001, 10006], 4:[10002], 8:[10003], 0:[10004], -1:[10005]]"));
        int count = netd.permissions.size();
        monitor.sendAppIdsTrafficPermission(new SparseIntArray());
        check(netd.permissions.size() == count);
        SparseIntArray bad = new SparseIntArray(); bad.put(10001, 16);
        Log.errors = 0;
        monitor.sendAppIdsTrafficPermission(bad);
        check(netd.permissions.size() == count && Log.errors == 1);

        netd.remote = new RemoteException("actual Binder error identity");
        try { maps.setNetPermForUids(8, new int[]{10001}); throw new AssertionError(); }
        catch (RemoteException error) { check(error == netd.remote); }
        netd.permissions.clear(); Log.errors = 0;
        monitor.sendAppIdsTrafficPermission(batch);
        check(netd.permissions.size() == 1 && Log.errors == 1); // Same caller error path, no hidden success.
        netd.remote = null; netd.service = new ServiceSpecificException(22, "native validation");
        try { maps.setNetPermForUids(8, new int[]{-1}); throw new AssertionError(); }
        catch (ServiceSpecificException error) { check(error == netd.service); }
        netd.permissions.clear(); Log.errors = 0;
        monitor.sendAppIdsTrafficPermission(batch);
        check(netd.permissions.size() == 1 && Log.errors == 1);

        if (mode.equals("legacy")) {
            BpfNetMaps missing = new BpfNetMaps(null, new NetworkPolicyFixture.Dependencies());
            try { missing.setNetPermForUids(8, new int[]{10001}); throw new AssertionError(); }
            catch (ServiceSpecificException error) { check(error.errorCode == 19); }
            try { maps.swapActiveStatsMap(); throw new AssertionError(); }
            catch (ServiceSpecificException error) { check(error.errorCode == 95); }
            try { maps.addUidInterfaceRules("tun0", new int[]{10001}); throw new AssertionError(); }
            catch (ServiceSpecificException error) { check(error.errorCode == 95); }
            check(deps.initialized == 0);
        }
    }
}
