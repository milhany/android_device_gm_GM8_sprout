// SPDX-License-Identifier: Apache-2.0

package org.lineageos.gm8.dolby;

import android.app.Application;
import android.content.Intent;

public final class DolbyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        startService(new Intent(this, DolbyService.class));
    }
}
