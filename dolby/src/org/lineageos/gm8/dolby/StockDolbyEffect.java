// SPDX-License-Identifier: Apache-2.0

package org.lineageos.gm8.dolby;

import android.media.audiofx.AudioEffect;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.UUID;

/** The DS1.10 protocol in GM8 build 411, not the Lenovo DAX1 protocol. */
final class StockDolbyEffect extends AudioEffect {
    private static final UUID DAP = UUID.fromString("9d4921da-8225-4f29-aefa-39537a04bcaa");
    private static final int CPDP_VALUES = 11;
    private static final int ENABLE = 0x01000000;
    private static final int PROFILE = 0x06000000;

    StockDolbyEffect() {
        super(EFFECT_TYPE_NULL, DAP, 0, 0);
    }

    void apply(boolean enabled, int profile) {
        if (profile < 1 || profile > 6) {
            throw new IllegalArgumentException("Invalid GM8 profile " + profile);
        }
        if (!hasControl()) {
            throw new IllegalStateException("Another client controls Dolby");
        }
        write(PROFILE, profile);
        write(ENABLE, enabled ? 1 : 0);
        checkStatus(setEnabled(enabled));
    }

    boolean isDapEnabled() {
        return read(ENABLE) != 0;
    }

    int profile() {
        return read(PROFILE);
    }

    private void write(int parameter, int value) {
        byte[] payload = ByteBuffer.allocate(12).order(ByteOrder.nativeOrder())
                .putInt(parameter).putInt(1).putInt(value).array();
        checkStatus(setParameter(CPDP_VALUES, payload));
    }

    private int read(int parameter) {
        byte[] payload = ByteBuffer.allocate(12).order(ByteOrder.nativeOrder())
                .putInt(parameter).array();
        int result = getParameter(CPDP_VALUES + parameter, payload);
        checkStatus(result);
        if (result < 4) {
            throw new IllegalStateException("Short Dolby response: " + result);
        }
        return ByteBuffer.wrap(payload).order(ByteOrder.nativeOrder()).getInt();
    }
}
