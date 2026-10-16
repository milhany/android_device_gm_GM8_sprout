// SPDX-License-Identifier: Apache-2.0

package org.lineageos.gm8.dolby;

import android.app.Activity;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.UserHandle;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.Switch;
import android.widget.TextView;

public final class DolbyActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            status.setText(UserHandle.myUserId() == UserHandle.USER_SYSTEM
                    ? DolbyService.status : R.string.primary_user_only);
            handler.postDelayed(this, 1000);
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        SharedPreferences prefs = getSharedPreferences(DolbyService.PREFS, MODE_PRIVATE);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);
        TextView description = new TextView(this);
        description.setText(R.string.description);
        layout.addView(description);
        Switch enabled = new Switch(this);
        enabled.setText(R.string.enabled);
        enabled.setPadding(0, padding, 0, padding);
        enabled.setChecked(prefs.getBoolean("enabled", true));
        layout.addView(enabled);
        enabled.setOnCheckedChangeListener((button, checked) ->
                prefs.edit().putBoolean("enabled", checked).apply());
        TextView label = new TextView(this);
        label.setText(R.string.profile);
        layout.addView(label);
        Spinner profiles = new Spinner(this);
        ArrayAdapter<CharSequence> adapter = ArrayAdapter.createFromResource(this,
                R.array.profiles, android.R.layout.simple_spinner_item);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        profiles.setAdapter(adapter);
        profiles.setSelection(Math.max(0, Math.min(5, prefs.getInt("profile", 2) - 1)));
        layout.addView(profiles);
        profiles.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                int profile = position + 1;
                if (prefs.getInt("profile", 2) != profile) {
                    prefs.edit().putInt("profile", profile).apply();
                }
            }
            @Override public void onNothingSelected(AdapterView<?> parent) {}
        });
        status = new TextView(this);
        status.setPadding(0, padding, 0, 0);
        layout.addView(status);
        boolean primary = UserHandle.myUserId() == UserHandle.USER_SYSTEM;
        enabled.setEnabled(primary);
        profiles.setEnabled(primary);
        setContentView(layout);
    }

    @Override public void onResume() {
        super.onResume();
        handler.post(refresh);
    }

    @Override public void onPause() {
        handler.removeCallbacks(refresh);
        super.onPause();
    }
}
