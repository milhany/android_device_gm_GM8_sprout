// SPDX-License-Identifier: Apache-2.0
package org.lineageos.gm8.dolby;

/** Pure policy; values are Android's MODE_NORMAL and DEVICE_OUT_EARPIECE. */
final class DolbyRoutePolicy {
    static boolean allowsDap(int mode, int musicDevices) {
        // No processing in a call/VoIP session or while routing is unknown.
        // Check the bit, not equality: mirrored earpiece+speaker is unsafe too.
        return mode == 0 && musicDevices != 0 && (musicDevices & 1) == 0;
    }

    private DolbyRoutePolicy() {}
}
