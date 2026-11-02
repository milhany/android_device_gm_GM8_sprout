#!/usr/bin/env python3
"""Preserve errno in Q libperfmgr's existing node-open/write failure log."""
import argparse
from pathlib import Path


OLD = '                LOG(WARNING) << "Failed to write to node: " << node_path_'
NEW = '                PLOG(WARNING) << "Failed to write to node: " << node_path_'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    path = args.top / 'system/extras/libperfmgr/FileNode.cc'
    try:
        text = path.read_text()
        if text.count(NEW) == 1 and OLD not in text:
            print('Q libperfmgr errno diagnostics already applied.')
            return
        if text.count(OLD) != 1 or NEW in text:
            raise ValueError('Unexpected Q FileNode.cc; preserving it for inspection')
        path.write_text(text.replace(OLD, NEW))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Power diagnostics patch failed: {error}\n')
    print('Applied Q libperfmgr errno diagnostics; preserve this local change across syncs.')


if __name__ == '__main__':
    main()
