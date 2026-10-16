// SPDX-License-Identifier: Apache-2.0

package org.lineageos.gm8.dolby;

import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioManager;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.IHwBinder;
import android.os.RemoteException;
import android.os.UserHandle;
import android.util.Log;

/** Owns the global DAP effect and stops automatically after an unsafe attach. */
public final class DolbyService extends Service {
    static final String PREFS = "dolby";
    static volatile int status = R.string.starting;
    private static final String TAG = "GM8Dolby";
    private static final long STABLE_MS = 5000;
    private HandlerThread thread;
    private Handler worker;
    private StockDolbyEffect effect;
    private StockDmsClient dms;
    private long dmsGeneration;
    private SharedPreferences prefs;
    private AudioManager audio;
    private boolean registered;
    private boolean attaching;
    private final Runnable attach = this::apply;
    private final Runnable verify = this::verify;
    private final IHwBinder.DeathRecipient dmsDeath = cookie -> worker.post(() -> {
        if (cookie == dmsGeneration && dms != null) {
            dms = null;
            pause("Stock Dolby DMS died; waiting for an explicit retry", null);
        }
    });
    private final SharedPreferences.OnSharedPreferenceChangeListener listener = (p, key) -> {
        // Internal checkpoints must never schedule another native transaction.
        if ("enabled".equals(key) || "profile".equals(key) || "retry".equals(key)) {
            worker.post(() -> {
                if ("retry".equals(key) || ("enabled".equals(key)
                        && p.getBoolean("enabled", true))) {
                    prefs.edit().putBoolean("paused", false).commit();
                }
                schedule();
            });
        }
    };
    private final AudioManager.AudioServerStateCallback serverCallback =
            new AudioManager.AudioServerStateCallback() {
        @Override public void onAudioServerDown() {
            worker.removeCallbacks(attach);
            worker.removeCallbacks(verify);
            if (attaching) {
                pause("Audio server died during Dolby attachment", null);
            } else {
                releaseEffect();
                status = prefs.getBoolean("paused", false) ? R.string.paused
                        : prefs.getBoolean("enabled", true) ? R.string.starting : R.string.inactive;
            }
        }
        @Override public void onAudioServerUp() {
            if (effect == null && !prefs.getBoolean("paused", false)) schedule();
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        if (UserHandle.myUserId() != UserHandle.USER_SYSTEM) {
            stopSelf();
            return;
        }
        thread = new HandlerThread(TAG);
        thread.start();
        worker = new Handler(thread.getLooper());
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        // Survives a native crash or process death before Java can catch an error.
        if (prefs.getBoolean("attaching", false)) {
            prefs.edit().putBoolean("paused", true).putBoolean("attaching", false).commit();
        }
        prefs.registerOnSharedPreferenceChangeListener(listener);
        audio = getSystemService(AudioManager.class);
        audio.setAudioServerStateCallback(command -> worker.post(command), serverCallback);
        registered = true;
        worker.post(this::schedule);
    }

    private void schedule() {
        worker.removeCallbacks(attach);
        worker.removeCallbacks(verify);
        worker.postDelayed(attach, 1000);
    }

    private void apply() {
        worker.removeCallbacks(verify);
        if (!prefs.getBoolean("enabled", true)) {
            releaseEffect();
            releaseDms();
            attaching = false;
            prefs.edit().putBoolean("attaching", false).commit();
            status = R.string.inactive;
            return;
        }
        if (prefs.getBoolean("paused", false)) {
            status = R.string.paused;
            return;
        }
        // Commit before touching native audio so a process restart cannot loop.
        if (!prefs.edit().putBoolean("attaching", true).commit()) {
            status = R.string.paused;
            return;
        }
        attaching = true;
        status = R.string.starting;
        try {
            if (dms == null) dms = new StockDmsClient(dmsDeath, ++dmsGeneration);
            if (effect == null) {
                effect = new StockDolbyEffect();
                effect.setControlStatusListener((e, control) -> {
                    if (e != effect) return;
                    if (control && !prefs.getBoolean("paused", false)) schedule();
                    else if (!control) status = R.string.unavailable;
                });
            }
            effect.apply(true, prefs.getInt("profile", 2));
            worker.postDelayed(verify, STABLE_MS);
        } catch (RemoteException | RuntimeException e) {
            pause("Dolby attachment failed; waiting for an explicit retry", e);
        }
    }

    private void verify() {
        try {
            if (effect == null || !effect.isDapEnabled()
                    || effect.profile() != prefs.getInt("profile", 2)) {
                throw new IllegalStateException("Dolby did not accept the requested settings");
            }
            if (!prefs.edit().putBoolean("attaching", false).commit()) {
                throw new IllegalStateException("Cannot save Dolby attachment checkpoint");
            }
            attaching = false;
            status = R.string.active;
            Log.i(TAG, "DAP ready: enabled=true profile=" + prefs.getInt("profile", 2));
        } catch (RuntimeException e) {
            pause("Dolby verification failed; waiting for an explicit retry", e);
        }
    }

    private void pause(String reason, Throwable error) {
        worker.removeCallbacks(attach);
        worker.removeCallbacks(verify);
        prefs.edit().putBoolean("paused", true).putBoolean("attaching", false).commit();
        attaching = false;
        status = R.string.paused;
        Log.w(TAG, reason, error);
        releaseEffect();
        releaseDms();
    }

    private void releaseDms() {
        if (dms != null) {
            StockDmsClient previous = dms;
            dms = null;
            ++dmsGeneration;
            previous.close();
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
                releaseDms();
                prefs.edit().putBoolean("attaching", false).commit();
                thread.quitSafely();
            });
        }
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) {
        return null;
    }
}
