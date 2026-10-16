// SPDX-License-Identifier: Apache-2.0

package org.lineageos.gm8.dolby;

import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioManager;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.UserHandle;
import android.util.Log;

/** Keeps one global DAP instance alive, including after an audioserver restart. */
public final class DolbyService extends Service {
    static final String PREFS = "dolby";
    static volatile int status = R.string.starting;
    private static final String TAG = "GM8Dolby";
    private HandlerThread thread;
    private Handler worker;
    private StockDolbyEffect effect;
    private SharedPreferences prefs;
    private AudioManager audio;
    private boolean registered;
    private final SharedPreferences.OnSharedPreferenceChangeListener listener =
            (p, key) -> worker.post(this::apply);
    private final AudioManager.AudioServerStateCallback serverCallback =
            new AudioManager.AudioServerStateCallback() {
        @Override public void onAudioServerDown() {
            worker.removeCallbacks(retry);
            releaseEffect();
            status = R.string.starting;
        }
        @Override public void onAudioServerUp() {
            apply();
        }
    };
    private final Runnable retry = this::apply;

    @Override public void onCreate() {
        super.onCreate();
        // This ROM's global output mix is controlled by the primary user.
        if (UserHandle.myUserId() != UserHandle.USER_SYSTEM) {
            stopSelf();
            return;
        }
        thread = new HandlerThread(TAG);
        thread.start();
        worker = new Handler(thread.getLooper());
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        prefs.registerOnSharedPreferenceChangeListener(listener);
        audio = getSystemService(AudioManager.class);
        audio.setAudioServerStateCallback(command -> worker.post(command), serverCallback);
        registered = true;
        worker.post(this::apply);
    }

    private void apply() {
        worker.removeCallbacks(retry);
        try {
            if (effect == null) {
                effect = new StockDolbyEffect();
                // Reactivate the engine after temporary AudioEffect clients release it.
                effect.setControlStatusListener((e, control) -> {
                    if (control) worker.post(this::apply);
                    else status = R.string.unavailable;
                });
            }
            boolean enabled = prefs.getBoolean("enabled", true);
            int profile = prefs.getInt("profile", 2);
            effect.apply(enabled, profile);
            if (effect.isDapEnabled() != enabled || effect.profile() != profile) {
                throw new IllegalStateException("Dolby did not accept the requested settings");
            }
            status = enabled ? R.string.active : R.string.inactive;
            Log.i(TAG, "DAP ready: enabled=" + enabled + " profile=" + profile);
        } catch (RuntimeException e) {
            status = R.string.unavailable;
            Log.w(TAG, "Cannot attach GM8 stock DAP; retrying in 10s", e);
            releaseEffect();
            worker.postDelayed(retry, 10000);
        }
    }

    private void releaseEffect() {
        if (effect != null) {
            try {
                effect.setControlStatusListener(null);
                effect.release();
            } catch (RuntimeException e) {
                Log.w(TAG, "Audio server already released Dolby", e);
            } finally {
                effect = null;
            }
        }
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        return worker == null ? START_NOT_STICKY : START_STICKY;
    }

    @Override public void onDestroy() {
        if (worker != null) {
            prefs.unregisterOnSharedPreferenceChangeListener(listener);
            if (registered) audio.clearAudioServerStateCallback();
            worker.removeCallbacksAndMessages(null);
            worker.post(() -> {
                releaseEffect();
                thread.quitSafely();
            });
        }
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) {
        return null;
    }
}
