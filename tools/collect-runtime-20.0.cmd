@echo off
setlocal EnableExtensions
where adb >nul 2>&1
if errorlevel 1 (
    echo Run this file from platform-tools, or add adb to PATH.
    exit /b 1
)
set "OUT=gm8-20-runtime-%RANDOM%-%RANDOM%"
if exist "%OUT%" exit /b 1
mkdir "%OUT%"
echo Collecting into %OUT% ...
adb devices > "%OUT%\devices.txt" 2>&1
adb wait-for-device
adb root > "%OUT%\adb-root.txt" 2>&1
adb wait-for-device
adb shell getprop > "%OUT%\properties.txt" 2>&1
adb shell getenforce > "%OUT%\selinux-mode.txt" 2>&1
adb shell cat /proc/cgroups > "%OUT%\controllers.txt" 2>&1
adb shell cat /proc/mounts > "%OUT%\mounts.txt" 2>&1
adb shell cat /vendor/etc/cgroups.json > "%OUT%\cgroups.json" 2>&1
adb shell cat /vendor/etc/task_profiles.json > "%OUT%\task_profiles.json" 2>&1
adb shell dumpsys wifi > "%OUT%\wifi.txt" 2>&1
adb shell dumpsys connectivity > "%OUT%\connectivity.txt" 2>&1
adb shell dumpsys netstats > "%OUT%\netstats.txt" 2>&1
adb shell dumpsys meminfo > "%OUT%\memory.txt" 2>&1
adb shell dumpsys activity processes > "%OUT%\processes.txt" 2>&1
adb shell dumpsys media.audio_flinger > "%OUT%\audio.txt" 2>&1
adb shell dumpsys media.camera > "%OUT%\camera.txt" 2>&1
adb shell dumpsys sensorservice > "%OUT%\sensors.txt" 2>&1
adb shell dumpsys location > "%OUT%\location.txt" 2>&1
adb shell dumpsys gpu > "%OUT%\gpu.txt" 2>&1
adb shell lshal > "%OUT%\hals.txt" 2>&1
adb shell ls -l /system_ext/lib/vendor.qti.hardware.camera.device@1.0.so /system_ext/lib64/vendor.qti.hardware.camera.device@1.0.so > "%OUT%\ims-camera-libraries.txt" 2>&1
adb pull /data/anr "%OUT%\anr" > "%OUT%\anr-copy.txt" 2>&1
adb logcat -b all -d > "%OUT%\logcat.txt" 2>&1
powershell -NoProfile -Command "Compress-Archive -Path '%OUT%\*' -DestinationPath '%OUT%.zip'" > "%OUT%\archive-result.txt" 2>&1
if exist "%OUT%.zip" (
    echo Ready: %OUT%.zip
) else (
    echo Collection folder: %OUT%
)
endlocal
