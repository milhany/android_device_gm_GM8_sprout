// SPDX-License-Identifier: Apache-2.0
// Host regression: pass an Android 11 framework class jar with android/hidl/**
// removed, followed by compiled GM8Dolby classes. Do not put Android jars on
// the test runner's own classpath; each resolution uses an isolated loader.
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Paths;

public final class DolbyClassLoadingTest {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("framework.jar app-classes");
        URL[] inputs = {Paths.get(args[0]).toUri().toURL(), Paths.get(args[1]).toUri().toURL()};
        try (URLClassLoader loader = new URLClassLoader(inputs, null)) {
            try {
                Class.forName("android.hidl.base.V1_0.IBase", false, loader);
                throw new AssertionError("Generated HIDL classes leaked into test framework");
            } catch (ClassNotFoundException expected) {
                // Reproduce the installed framework without generated HIDL server classes.
            }
            Class<?> callback = Class.forName(
                    "org.lineageos.gm8.dolby.StockDmsClient$Callback", false, loader);
            if (!callback.getSuperclass().getName().equals("android.os.HwBinder")) {
                throw new AssertionError("Callback must use the platform HwBinder directly");
            }
            Class.forName("org.lineageos.gm8.dolby.DolbyService", false, loader);
            System.out.println("Dolby callback and service resolve without generated HIDL Java classes");
        }
    }
}
