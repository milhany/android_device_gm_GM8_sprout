#!/usr/bin/env python3
"""Check actual compiled Q policy for Dolby application startup and DMS access."""
import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    top = args.top.resolve()
    policy = top / 'out/target/product/GM8_sprout/obj/ETC/sepolicy_intermediates/sepolicy'
    host = top / 'out/host/linux-x86'
    search = host / 'bin/searchpolicy'
    library = host / 'lib64/libsepolwrap.so'
    analyzer = host / 'bin/sepolicy-analyze'
    try:
        for path in (policy, search, library, analyzer):
            if not path.is_file():
                raise ValueError(f'Missing compiled policy tool/input: {path}')
        result = subprocess.run([str(analyzer), str(policy), 'attribute', 'appdomain'],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        if 'gm8_dolby_app' not in result.stdout.split():
            raise ValueError('gm8_dolby_app is missing from the compiled appdomain attribute')
        targets = [(name, 'service_manager') for name in (
            'activity_service', 'package_service', 'audio_service',
            'notification_service', 'power_service',
            'audioserver_service', 'gpu_service')]
        requests = [(target, target_class, 'find') for target, target_class in targets]
        requests.extend((('hal_gm8_dolby_hwservice', 'hwservice_manager', 'find'),
                         ('gpuservice', 'binder', 'call')))
        for target, target_class, permission in requests:
            result = subprocess.run([
                str(search), str(policy), '--libpath', str(library), '--allow',
                '-s', 'gm8_dolby_app', '-t', target, '-c', target_class, '-p', permission],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if not any(line.startswith('allow ') for line in result.stdout.splitlines()):
                raise ValueError(f'Compiled Dolby policy lacks {permission} on {target}:{target_class}')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        detail = getattr(error, 'stderr', '') or ''
        parser.exit(1, f'Dolby policy check failed: {error}\n{detail}')
    print('PASS: compiled Dolby app policy permits Android startup/UI/audio APIs and DMS discovery')
    print('This check does not prove service availability, audio processing or route behavior.')


if __name__ == '__main__':
    main()
