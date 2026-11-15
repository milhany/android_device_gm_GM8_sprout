LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)
LOCAL_MODULE := init.recovery.qcom.rc
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := ETC
LOCAL_SRC_FILES := init.recovery.qcom.rc
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)
include $(BUILD_PREBUILT)

# Recovery inherits ro.vendor.gm8.legacy_cgroups=true, but does not mount vendor
# before SetupCgroups(). Install the same authoritative v1 policy in its ramdisk.
include $(CLEAR_VARS)
LOCAL_MODULE := gm8_recovery_cgroups.json
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := ETC
LOCAL_MODULE_STEM := cgroups.json
LOCAL_SRC_FILES := ../configs/cgroups-gm8.json
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/vendor/etc
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := gm8_recovery_task_profiles.json
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := ETC
LOCAL_MODULE_STEM := task_profiles.json
LOCAL_SRC_FILES := ../configs/task-profiles-gm8.json
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/vendor/etc
include $(BUILD_PREBUILT)

