// SPDX-License-Identifier: Apache-2.0

package org.lineageos.gm8.dolby;

import android.hidl.base.V1_0.IBase;
import android.os.HwBinder;
import android.os.HwBlob;
import android.os.HwParcel;
import android.os.IHwBinder;
import android.os.IHwInterface;
import android.os.Process;
import android.os.RemoteException;
import java.util.ArrayList;
import java.util.Arrays;

/** Minimal transport for stock GM8 DMS's first two, synchronous HIDL methods. */
final class StockDmsClient {
    private static final String DMS = "vendor.dolby.hardware.dms@1.0::IDms";
    private static final String CALLBACK = "vendor.dolby.hardware.dms@1.0::IDmsCallbacks";
    private static final int NATIVE_SERVICE = 3;
    private final IHwBinder binder;
    private final Callback callback = new Callback();
    private final IHwBinder.DeathRecipient death;

    StockDmsClient(IHwBinder.DeathRecipient death, long cookie) throws RemoteException {
        this.death = death;
        binder = HwBinder.getService(DMS, "default", false);
        if (binder == null || !binder.linkToDeath(death, cookie)) {
            throw new IllegalStateException("Stock Dolby DMS is not available");
        }
        try {
            // Stock DMS calls DsManager::init only for this native-service client.
            // This must finish before AudioEffect creation enters the audio HAL.
            transactClient(1);
        } catch (RemoteException | RuntimeException e) {
            binder.unlinkToDeath(death);
            throw e;
        }
    }

    private void transactClient(int transaction) throws RemoteException {
        HwParcel request = new HwParcel();
        HwParcel reply = new HwParcel();
        try {
            request.writeInterfaceToken(DMS);
            request.writeStrongBinder(callback.asBinder());
            request.writeInt32(NATIVE_SERVICE);
            request.writeInt32(Process.myPid());
            binder.transact(transaction, request, reply, 0);
            reply.verifySuccess();
        } finally {
            request.releaseTemporaryStorage();
            reply.release();
        }
    }

    void close() {
        try {
            transactClient(2);
        } catch (RemoteException | RuntimeException ignored) {
            // DMS may already have died; do not reconnect during cleanup.
        } finally {
            binder.unlinkToDeath(death);
        }
    }

    private static byte[] hash(String hex) {
        byte[] result = new byte[32];
        for (int i = 0; i < result.length; i++) {
            result[i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
        }
        return result;
    }

    /** IBase supplies standard debug/ping/death handling; identify the callback on the wire. */
    private static final class Callback extends IBase.Stub {
        @Override public IHwInterface queryLocalInterface(String descriptor) {
            return CALLBACK.equals(descriptor) ? this : super.queryLocalInterface(descriptor);
        }

        @Override public void onTransact(int code, HwParcel request, HwParcel reply, int flags)
                throws RemoteException {
            if (code == 1) {
                request.enforceInterface(CALLBACK);
                request.readInt8Vector(); // Native DAP clients pull the updated parameter cache.
                if ((flags & 1) == 0) {
                    reply.writeStatus(0);
                    reply.send();
                }
                return;
            }
            if (code != 256067662 && code != 256136003 && code != 256398152) {
                super.onTransact(code, request, reply, flags);
                return;
            }
            if ((flags & 1) != 0) {
                reply.writeStatus(Integer.MIN_VALUE);
                reply.send();
                return;
            }
            request.enforceInterface(IBase.kInterfaceName);
            reply.writeStatus(0);
            if (code == 256067662) {
                reply.writeStringVector(new ArrayList<>(Arrays.asList(CALLBACK, IBase.kInterfaceName)));
            } else if (code == 256136003) {
                reply.writeString(CALLBACK);
            } else {
                // Exact callback/base hashes exported by the stock GM8 interface library.
                HwBlob header = new HwBlob(16);
                header.putInt32(8, 2);
                header.putBool(12, false);
                HwBlob hashes = new HwBlob(64);
                hashes.putInt8Array(0, hash("ac03bccdd6e6212209fe6e51cf8aff786b228568324d4abf20d6e2c624c04aa5"));
                hashes.putInt8Array(32, hash("bddab6184d7a346da6a07dc0828cf19a696f4caa3611c51f2e14565a14b40fd9"));
                header.putBlob(0, hashes);
                reply.writeBuffer(header);
            }
            reply.send();
        }
    }
}
