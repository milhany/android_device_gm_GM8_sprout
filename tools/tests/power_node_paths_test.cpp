// SPDX-License-Identifier: Apache-2.0
// Host regression: g++ -std=c++17 -Wall -Wextra -Werror -Ipower-libperfmgr/libperfmgr/include
// tools/tests/power_node_paths_test.cpp -o /tmp/gm8-node-paths && /tmp/gm8-node-paths
#include <perfmgr/NodePaths.h>
#include <cassert>
#include <cstdlib>
#include <sys/stat.h>
#include <unistd.h>

int main() {
    char dir[] = "/tmp/gm8-node-paths-XXXXXX";
    assert(mkdtemp(dir));
    std::string primary = std::string(dir) + "/cpu0";
    std::string sibling1 = std::string(dir) + "/cpu1";
    std::string sibling2 = std::string(dir) + "/cpu2";
    auto create = [](const std::string& path) {
        int fd = open(path.c_str(), O_CREAT | O_WRONLY, 0600);
        assert(fd >= 0);
        assert(close(fd) == 0);
    };
    std::string used;
    create(primary);
    create(sibling1);
    create(sibling2);
    auto open_node = [&]() {
        return android::perfmgr::OpenNodePaths(primary, {sibling1, sibling2},
                                               O_WRONLY | O_CLOEXEC, &used);
    };
    int fd = open_node();
    assert(fd >= 0 && used == primary);
    close(fd);
    assert(unlink(primary.c_str()) == 0);
    fd = open_node();
    assert(fd >= 0 && used == sibling1); // Policy moves off CPU0.
    assert(write(fd, "1209600", 7) == 7);
    close(fd);
    assert(unlink(sibling1.c_str()) == 0);
    fd = open_node();
    assert(fd >= 0 && used == sibling2); // Re-resolve on the next update.
    close(fd);
    assert(mkdir(primary.c_str(), 0700) == 0);
    assert(open_node() == -1 && errno == EISDIR); // Do not hide real I/O errors.
    assert(rmdir(primary.c_str()) == 0);
    assert(unlink(sibling2.c_str()) == 0);
    assert(open_node() == -1 && errno == ENOENT);
    assert(rmdir(dir) == 0);
    return 0;
}
