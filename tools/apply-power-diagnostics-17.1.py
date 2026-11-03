#!/usr/bin/env python3
"""Apply bounded Q libperfmgr errno and GM8 CPU hotplug compatibility fixes."""
import argparse
from pathlib import Path


OLD = '                LOG(WARNING) << "Failed to write to node: " << node_path_'
NEW = '                PLOG(WARNING) << "Failed to write to node: " << node_path_'

OPEN_OLD = '''        fd_.reset(TEMP_FAILURE_RETRY(
            open(node_path_.c_str(), O_WRONLY | O_CLOEXEC | O_TRUNC)));'''
OPEN_NEW = '        fd_.reset(OpenGm8CpuFreqNode(node_path_));'
NAMESPACE = 'namespace perfmgr {\n'
INCLUDES = '#include <cerrno>\n#include <sstream>\n\n'
HELPER = r'''
namespace {

// GM8's 3.18 cpufreq kobject moves when the policy CPU goes offline.
// Resolve only the four configured frequency endpoints, only on ENOENT,
// and only to a CPU proven to share that original four-CPU policy.
int OpenGm8CpuFreqNode(const std::string& path) {
    const int flags = O_WRONLY | O_CLOEXEC | O_TRUNC;
    int fd = TEMP_FAILURE_RETRY(open(path.c_str(), flags));
    if (fd >= 0 || errno != ENOENT) return fd;

    const std::string prefix = "/sys/devices/system/cpu/cpu";
    int first_cpu = -1;
    std::string attribute;
    for (int cpu : {0, 4}) {
        for (const char* name : {"scaling_min_freq", "scaling_max_freq"}) {
            if (path == prefix + std::to_string(cpu) + "/cpufreq/" + name) {
                first_cpu = cpu;
                attribute = name;
            }
        }
    }
    if (first_cpu < 0) { errno = ENOENT; return -1; }

    for (int cpu = first_cpu + 1; cpu < first_cpu + 4; ++cpu) {
        const std::string directory = prefix + std::to_string(cpu) + "/cpufreq/";
        std::string related;
        if (!android::base::ReadFileToString(directory + "related_cpus", &related)) continue;
        std::istringstream members(related);
        std::string token;
        bool has_original = false, has_candidate = false, valid = true;
        while (members >> token) {
            if (token.size() != 1 || token[0] < '0' || token[0] > '7') {
                valid = false;
                break;
            }
            const int member = token[0] - '0';
            if (member < first_cpu || member >= first_cpu + 4) valid = false;
            has_original = has_original || member == first_cpu;
            has_candidate = has_candidate || member == cpu;
        }
        if (!members.eof() || !valid || !has_original || !has_candidate) continue;

        fd = TEMP_FAILURE_RETRY(open((directory + attribute).c_str(), flags));
        if (fd >= 0 || errno != ENOENT) return fd;
        // A second CPU can go offline during discovery. Try the next sibling.
    }
    errno = ENOENT;
    return -1;
}

}  // namespace
'''


def transform(text):
    # Validate both hunks before changing anything on disk. Accept vanilla Q
    # or our previous errno-only patch; reject drift rather than guessing.
    if text.count(NEW) == 1 and OLD not in text:
        pass
    elif text.count(OLD) == 1 and NEW not in text:
        text = text.replace(OLD, NEW)
    else:
        raise ValueError('Unexpected Q FileNode.cc diagnostics; preserving it for inspection')
    if HELPER in text and OPEN_NEW in text:
        if (text.count(HELPER) != 1 or text.count(OPEN_NEW) != 1 or
                OPEN_OLD in text or INCLUDES not in text):
            raise ValueError('Partial GM8 cpufreq patch; preserving it for inspection')
        return text
    if ('OpenGm8CpuFreqNode' in text or text.count(OPEN_OLD) != 1 or
            text.count(NAMESPACE) != 1 or text.count('#include "perfmgr/FileNode.h"') != 1):
        raise ValueError('Unexpected Q FileNode.cc CPU path; preserving it for inspection')
    text = text.replace('#include "perfmgr/FileNode.h"', INCLUDES + '#include "perfmgr/FileNode.h"')
    return text.replace(NAMESPACE, NAMESPACE + HELPER).replace(OPEN_OLD, OPEN_NEW)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    path = args.top / 'system/extras/libperfmgr/FileNode.cc'
    try:
        text = path.read_text()
        patched = transform(text)
        if patched == text:
            print('Q libperfmgr errno/hotplug compatibility already applied.')
            return
        path.write_text(patched)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Power diagnostics patch failed: {error}\n')
    print('Applied Q libperfmgr errno/hotplug compatibility; preserve this local change across syncs.')


if __name__ == '__main__':
    main()
