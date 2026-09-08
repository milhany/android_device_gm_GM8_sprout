package com.gm.settingsbridge;

import android.app.Service;
import android.content.ContentResolver;
import android.content.Intent;
import android.database.ContentObserver;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.UserHandle;
import android.provider.Settings;
import android.util.Log;

public final class SettingsBridgeService extends Service {
    private static final String TAG = "GM8SettingsBridge";
    private static final Uri LINEAGE_SYSTEM_URI =
            Uri.parse("content://lineagesettings/system");
    private static final String LINEAGE_BATTERY_PERCENT =
            "status_bar_show_battery_percent";

    private final Handler mHandler = new Handler(Looper.getMainLooper());
    private ContentObserver mBatteryObserver;

    @Override
    public void onCreate() {
        super.onCreate();
        mBatteryObserver = new ContentObserver(mHandler) {
            @Override
            public void onChange(boolean selfChange) {
                syncBatteryPercentage();
            }
        };
        getContentResolver().registerContentObserver(
                Settings.System.getUriFor(Settings.System.SHOW_BATTERY_PERCENT),
                false, mBatteryObserver);
        syncBatteryPercentage();
    }

    private void syncBatteryPercentage() {
        final ContentResolver resolver = getContentResolver();
        final int aospValue = Settings.System.getInt(
                resolver, Settings.System.SHOW_BATTERY_PERCENT, 0);

        // LineageOS 18.1 SystemUI reads its own LineageSettings key while
        // AOSP Settings writes Settings.System.SHOW_BATTERY_PERCENT.
        // Mirror the switch so the stock Battery screen actually controls
        // the visible SystemUI percentage.
        final Bundle extras = new Bundle();
        extras.putString(Settings.NameValueTable.VALUE, aospValue != 0 ? "1" : "0");
        extras.putInt("_user", UserHandle.myUserId());

        try {
            resolver.call(LINEAGE_SYSTEM_URI, "PUT_system",
                    LINEAGE_BATTERY_PERCENT, extras);
        } catch (RuntimeException e) {
            Log.w(TAG, "Unable to sync battery percentage", e);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        syncBatteryPercentage();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (mBatteryObserver != null) {
            getContentResolver().unregisterContentObserver(mBatteryObserver);
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
