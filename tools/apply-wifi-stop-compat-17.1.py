#!/usr/bin/env python3
"""Give the observed legacy Wi-Fi teardown time to finish; retain bounded failure."""
import argparse
from pathlib import Path


CHANGES = (
    ('hardware/interfaces/wifi/1.3/default/wifi_legacy_hal.cpp',
     'static constexpr uint32_t kMaxStopCompleteWaitMs = 100;',
     'static constexpr uint32_t kMaxStopCompleteWaitMs = 1000;',
     'std::chrono::milliseconds(kMaxStopCompleteWaitMs)'),
    ('frameworks/opt/net/wifi/service/java/com/android/server/wifi/SupplicantStaIfaceHal.java',
     'public static final long WAIT_FOR_DEATH_TIMEOUT_MS = 50L;',
     'public static final long WAIT_FOR_DEATH_TIMEOUT_MS = 500L;',
     'waitForDeathLatch.await(WAIT_FOR_DEATH_TIMEOUT_MS, TimeUnit.MILLISECONDS)'),
)


def transform(text, old, new, anchor):
    if text.count(anchor) != 1:
        raise ValueError('Unexpected Q Wi-Fi wait implementation; preserve it for inspection')
    if text.count(new) == 1 and old not in text:
        return text
    if text.count(old) != 1 or new in text:
        raise ValueError('Unexpected Q Wi-Fi timeout; preserve it for inspection')
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    try:
        updates = []
        # Validate both sources before writing either one.
        for name, old, new, anchor in CHANGES:
            path = args.top / name
            before = path.read_text()
            after = transform(before, old, new, anchor)
            if after != before:
                updates.append((path, after))
        for path, text in updates:
            path.write_text(text)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Wi-Fi stop compatibility patch failed: {error}\n')
    print('Applied Q Wi-Fi stop compatibility.' if updates else 'Q Wi-Fi stop compatibility already applied.')
    print('Preserve these hardware/interfaces and frameworks/opt/net/wifi edits across syncs.')


if __name__ == '__main__':
    main()
