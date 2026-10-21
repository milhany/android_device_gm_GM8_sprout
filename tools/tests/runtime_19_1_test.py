#!/usr/bin/env python3
"""Test actual patched Java methods and three-project patch application.

Requires a JDK and --top pointing to a prepared Android 12.1 source tree.
Extracted real methods use isolated Android/HAL fixtures, not a full platform
build. Pristine methods must reproduce all three reported null-pointer crashes.
"""

import argparse
from pathlib import Path
import subprocess
import tempfile


DEVICE = Path(__file__).resolve().parents[2]
SOURCES = [
    ("frameworks/base", "packages/SystemUI/src/com/android/systemui/statusbar/phone/fragment/"
     "CollapsedStatusBarFragment.java", "frameworks_base/0001-gm8-statusbar-tuner-view-lifecycle.patch"),
    ("lineage-sdk", "lineage/lib/main/java/org/lineageos/platform/internal/health/"
     "ChargingControlController.java", "lineage_sdk/0001-gm8-optional-charging-control-hal.patch"),
    ("packages/apps/Trebuchet", "quickstep/src/com/android/quickstep/SystemUiProxy.java",
     "packages_apps_Trebuchet/0001-gm8-handle-unavailable-recent-tasks.patch"),
]


def method(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


UI_FIXTURE = r'''
import java.util.*;
class Context { Object getResources() { return new Object(); } }
class Fragment {
    Context context = new Context(); Object view = new Object();
    Context getContext() { return context; }
    Object getView() { return view; }
    public void onDestroyView() { view = null; }
}
public class RuntimeUiTest extends Fragment {
    static final TunerService tuner = new TunerService();
    static class Dependency { static <T> T get(Class<T> type) { return type.cast(tuner); } }
    static class TunerService {
        final Set<RuntimeUiTest> clients = new HashSet<>();
        void addTunable(RuntimeUiTest f) { clients.add(f); }
        void removeTunable(RuntimeUiTest f) { clients.remove(f); }
        void dispatch(String value) {
            for (RuntimeUiTest f : new ArrayList<>(clients)) f.onTuningChanged("icon_blacklist", value);
        }
    }
    static class StatusBarIconController {
        static Set<String> getIconHideList(Context context, String value) {
            context.getResources();
            return value == null || value.isEmpty() ? Collections.emptySet() :
                    new HashSet<>(Arrays.asList(value.split(",")));
        }
    }
    static class Callbacks {
        void removeIconGroup(Object manager) {}
        void removeCallback(Object listener) {}
        boolean hasEmergencyCryptKeeperText() { return true; }
    }
    final Callbacks mStatusBarIconController = new Callbacks();
    final Callbacks mAnimationScheduler = new Callbacks();
    final Callbacks mNetworkController = new Callbacks();
    final Object mDarkIconManager = new Object(), mSignalCallback = new Object();
    boolean mIsClockBlacklisted; int clockShown;
    void showClock(boolean animate) { clockShown++; }
    /* DESTROY */
    /* TUNING */
    static void check(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }
    public static void main(String[] args) {
        RuntimeUiTest f = new RuntimeUiTest();
        tuner.addTunable(f);
        tuner.dispatch("clock"); check(f.mIsClockBlacklisted, "active hide");
        tuner.dispatch(""); check(!f.mIsClockBlacklisted && f.clockShown == 1, "active show");
        f.onDestroyView();
        // Simulate a callback already queued before the view was destroyed.
        f.context = null;
        f.onTuningChanged("icon_blacklist", "clock");
        check(!f.mIsClockBlacklisted, "ignore callback after detach");
        check(!tuner.clients.contains(f), "unregister on view destruction");
        f.context = new Context();
        f.onTuningChanged("icon_blacklist", "clock");
        check(!f.mIsClockBlacklisted, "ignore destroyed view while attached");
        f.view = new Object(); tuner.addTunable(f);
        tuner.dispatch("clock"); check(f.mIsClockBlacklisted, "recreated view receives updates");
        tuner.dispatch(null); check(!f.mIsClockBlacklisted && f.clockShown == 2, "default list");
        f.onDestroyView(); tuner.dispatch("clock");
        check(tuner.clients.isEmpty(), "no listeners leak across repeated view lifecycles");
    }
}
'''

HEALTH_FIXTURE = r'''
public class RuntimeHealthTest {
    static class RemoteException extends Exception {}
    interface IChargingControl { int getSupportedMode() throws RemoteException; }
    final IChargingControl mChargingControl;
    RuntimeHealthTest(IChargingControl hal) { mChargingControl = hal; }
    /* MODE */
    /* SUPPORTED */
    static void check(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }
    public static void main(String[] args) {
        RuntimeHealthTest absent = new RuntimeHealthTest(null);
        // These probes run inside the real constructor before isSupported().
        for (int mode : new int[]{1, 2, 4}) {
            check(!absent.isChargingModeSupported(mode), "absent optional HAL");
        }
        check(!absent.isSupported(), "do not advertise nonexistent HAL");
        final int[] calls = {0};
        RuntimeHealthTest present = new RuntimeHealthTest(() -> { calls[0]++; return 5; });
        check(present.isSupported(), "available HAL remains supported");
        check(present.isChargingModeSupported(1), "toggle capability");
        check(!present.isChargingModeSupported(2), "missing bypass capability");
        check(present.isChargingModeSupported(4), "deadline capability");
        check(calls[0] == 3, "query real capabilities without inventing support");
        RuntimeHealthTest broken = new RuntimeHealthTest(() -> { throw new RemoteException(); });
        try { broken.isChargingModeSupported(1); throw new AssertionError("lost existing exception"); }
        catch (RuntimeException expected) {
            check(expected.getCause() instanceof RemoteException, "preserve HAL failure semantics");
        }
    }
}
'''


RECENTS_FIXTURE = r'''
import java.util.*;
public class RuntimeRecentsTest {
    static final int RECENT_IGNORE_UNAVAILABLE = 2;
    static final String TAG = "fixture";
    static class RemoteException extends Exception {}
    static class Log { static void w(String tag, String msg, Exception e) {} }
    static class GroupedRecentTaskInfo { final int id; GroupedRecentTaskInfo(int value) { id = value; } }
    interface RecentTasks {
        GroupedRecentTaskInfo[] getRecentTasks(int max, int flags, int user) throws RemoteException;
    }
    RecentTasks mRecentTasks;
    /* TASKS */
    static void check(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }
    public static void main(String[] args) {
        RuntimeRecentsTest p = new RuntimeRecentsTest();
        check(p.getRecentTasks(10, 0).isEmpty(), "disconnected service");
        p.mRecentTasks = (max, flags, user) -> null;
        ArrayList<GroupedRecentTaskInfo> absent = p.getRecentTasks(10, 0);
        check(absent != null && absent.isEmpty(), "null remote array during reconnect");
        // The caller receives a fresh mutable list, including failure cases.
        absent.add(new GroupedRecentTaskInfo(99));
        check(p.getRecentTasks(10, 0).isEmpty(), "no shared fallback list");
        p.mRecentTasks = (max, flags, user) -> new GroupedRecentTaskInfo[0];
        check(p.getRecentTasks(10, 0).isEmpty(), "empty remote list");
        p.mRecentTasks = (max, flags, user) -> { throw new RemoteException(); };
        check(p.getRecentTasks(10, 0).isEmpty(), "retain binder-failure fallback");
        GroupedRecentTaskInfo first = new GroupedRecentTaskInfo(7), second = new GroupedRecentTaskInfo(3);
        p.mRecentTasks = (max, flags, user) -> {
            check(max == 42 && flags == RECENT_IGNORE_UNAVAILABLE && user == 11, "IPC arguments");
            return new GroupedRecentTaskInfo[]{first, second};
        };
        ArrayList<GroupedRecentTaskInfo> tasks = p.getRecentTasks(42, 11);
        check(tasks.size() == 2 && tasks.get(0) == first && tasks.get(1) == second, "order and identity");
        tasks.remove(0); check(tasks.size() == 1, "retain mutable result");
    }
}
'''


def run_java(directory, name, program, fixed):
    source = directory / (name + ".java")
    source.write_text(program)
    subprocess.run(["java", "com.sun.tools.javac.Main", "-d", str(directory), str(source)],
                   check=True, timeout=30)
    result = subprocess.run(["java", "-ea", "-cp", str(directory), name],
                            capture_output=True, text=True, timeout=15)
    if fixed:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0 and "NullPointerException" in result.stderr, result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, required=True)
    args = parser.parse_args()
    pristine, patched = [], []
    with tempfile.TemporaryDirectory(prefix="gm8-runtime-") as directory:
        top = Path(directory)
        (top / "build/core").mkdir(parents=True)
        version = top / "build/core/version_defaults.mk"
        version.write_text("PLATFORM_SDK_VERSION := 32\n")
        for project, path, patch in SOURCES:
            data = ((args.top / project / path).read_text()
                    + "\n// Fixture local change outside patched methods.\n")
            patched.append(data)
            dest = top / project / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(data)
            subprocess.run(["git", "apply", "--reverse", str(DEVICE / "patches" / patch)],
                           cwd=top / project, check=True)
            pristine.append(dest.read_text())
            (top / project / "unrelated-local.txt").write_text("keep local work\n")
        cmd = ["python3", str(DEVICE / "tools/apply-runtime-compat.py"), "--top", str(top)]

        def run(expected, *extra):
            result = subprocess.run(cmd + list(extra), capture_output=True, text=True)
            assert result.returncode == expected, (result.stdout, result.stderr)

        run(1, "--check")
        # Drift in the last project must not leave either earlier project patched.
        last = top / SOURCES[2][0] / SOURCES[2][1]
        last.write_text(pristine[2].replace("    public ArrayList<GroupedRecentTaskInfo> getRecentTasks(",
                                          "    public ArrayList<GroupedRecentTaskInfo> localTasks("))
        before = last.read_text()
        run(1)
        for index in (0, 1):
            assert (top / SOURCES[index][0] / SOURCES[index][1]).read_text() == pristine[index]
        assert last.read_text() == before
        last.write_text(pristine[2])
        run(0); run(0); run(0, "--check")
        for index, (project, path, patch) in enumerate(SOURCES):
            assert (top / project / path).read_text() == patched[index]
            assert (top / project / "unrelated-local.txt").read_text() == "keep local work\n"
        # A sync may reset only one project; preserve the already-applied one.
        last.write_text(pristine[2])
        run(1, "--check"); run(0); run(0, "--check")
        assert last.read_text() == patched[2]
        assert (top / SOURCES[0][0] / SOURCES[0][1]).read_text() == patched[0]
        version.write_text("PLATFORM_SDK_VERSION := 30\n")
        run(1)

        for fixed, texts in ((False, pristine), (True, patched)):
            ui = UI_FIXTURE.replace("/* DESTROY */", method(texts[0], "public void onDestroyView()"))
            ui = ui.replace("/* TUNING */", method(texts[0],
                            "public void onTuningChanged(String key, String newValue)"))
            health = HEALTH_FIXTURE.replace("/* MODE */", method(texts[1],
                            "public boolean isChargingModeSupported(int mode)"))
            health = health.replace("/* SUPPORTED */", method(texts[1], "public boolean isSupported()"))
            run_java(top, "RuntimeUiTest", ui, fixed)
            run_java(top, "RuntimeHealthTest", health, fixed)
            recents = RECENTS_FIXTURE.replace("/* TASKS */", method(texts[2],
                            "public ArrayList<GroupedRecentTaskInfo> getRecentTasks(int numTasks, int userId)"))
            run_java(top, "RuntimeRecentsTest", recents, fixed)
    print("PASS: real Java methods reproduce all three original crashes and pass after repair.")
    print("PASS: active/recreated status bar, stale callbacks, absent/present HAL capabilities.")
    print("PASS: null/empty/available recent tasks, binder failures, result mutability and IPC arguments.")
    print("PASS: three-project check/apply/repeat, local work preservation, drift refusal, SDK guard.")


if __name__ == "__main__":
    main()
