// SPDX-License-Identifier: Apache-2.0
#ifndef ANDROID_LIBPERFMGR_NODEPATHS_H_
#define ANDROID_LIBPERFMGR_NODEPATHS_H_

#include <cerrno>
#include <fcntl.h>
#include <string>
#include <vector>

namespace android {
namespace perfmgr {

// Only an absent hotplug alias permits fallback. Permission and I/O errors
// must stay visible rather than silently writing to another node.
inline int OpenNodePaths(const std::string& primary,
                         const std::vector<std::string>& fallbacks,
                         int flags, std::string* opened_path) {
    auto open_path = [flags](const std::string& path) {
        int fd;
        do {
            fd = open(path.c_str(), flags);
        } while (fd == -1 && errno == EINTR);
        return fd;
    };
    if (opened_path) *opened_path = primary;
    int fd = open_path(primary);
    if (fd >= 0) {
        if (opened_path) *opened_path = primary;
        return fd;
    }
    for (const auto& path : fallbacks) {
        if (errno != ENOENT && errno != ENOTDIR) return -1;
        if (opened_path) *opened_path = path;
        fd = open_path(path);
        if (fd >= 0) {
            if (opened_path) *opened_path = path;
            return fd;
        }
    }
    return -1;
}

}  // namespace perfmgr
}  // namespace android
#endif
