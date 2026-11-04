#!/usr/bin/env python3
"""Check compiled Q vendor-app access and the legacy app-zygote cleanup path."""
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
        app_domains = set(result.stdout.split())
        for domain in ('gm8_dolby_app', 'gm8_time_app'):
            if domain not in app_domains:
                raise ValueError(f'{domain} is missing from the compiled appdomain attribute')
        result = subprocess.run([str(analyzer), str(policy), 'attribute', 'coredomain'],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        if {'gm8_dolby_app', 'gm8_time_app'} & set(result.stdout.split()):
            raise ValueError('GM8 vendor app clients must not acquire coredomain')
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
        result = subprocess.run([
            str(search), str(policy), '--libpath', str(library), '--allow',
            '-s', 'gm8_time_app', '-t', 'time_daemon', '-c', 'unix_stream_socket', '-p', 'connectto'],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if not any(line.startswith('allow ') for line in result.stdout.splitlines()):
            raise ValueError('Compiled TimeService policy lacks its time_daemon socket connection')
        result = subprocess.run([
            str(search), str(policy), '--libpath', str(library), '--allow',
            '-s', 'system_server', '-t', 'app_zygote', '-c', 'process', '-p', 'getpgid'],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if not any(line.startswith('allow ') for line in result.stdout.splitlines()):
            raise ValueError('Compiled policy lacks system_server app_zygote process-group lookup')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        detail = getattr(error, 'stderr', '') or ''
        parser.exit(1, f'GM8 app policy check failed: {error}\n{detail}')
    print('PASS: compiled vendor app domains, Dolby/TimeService access and app-zygote group lookup')
    print('This check does not prove service availability, audio processing or route behavior.')


if __name__ == '__main__':
    main()
