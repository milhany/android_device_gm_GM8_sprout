#!/usr/bin/env python3
"""Run the real build entry point with local command fixtures, not Android."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = (ROOT / 'tools/build-20.0.sh').read_text()

for case in ('audit', 'configure', 'compile', 'compile-failure',
             'preflight-failure', 'port-failure', 'stats-port-failure', 'network-stats',
             'network-stats-failure', 'firewall-port-failure', 'network-firewall',
             'network-firewall-failure', 'policy-port-failure', 'network-policy',
             'network-policy-failure', 'socket-port-failure', 'network-sockets',
             'network-sockets-failure', 'wrong-sdk', 'invalid-stage'):
    with tempfile.TemporaryDirectory(prefix='gm8-build20-') as tmp:
        parent = Path(tmp)
        top = parent / 'lineage-20.0'
        tools = top / 'device/gm/GM8_sprout/tools'
        (tools / 'tests').mkdir(parents=True)
        entry = tools / 'build-20.0.sh'; entry.write_text(BUILD)
        version = top / 'build/core/version_defaults.mk'
        version.parent.mkdir(parents=True)
        version.write_text('PLATFORM_SDK_VERSION := ' + ('32' if case == 'wrong-sdk' else '33') + '\n')
        trace = parent / 'trace'
        env = {**os.environ, 'GM8_TEST_TRACE': str(trace),
               'GM8_TEST_SOCKET_PORT_FAIL': '1' if case == 'socket-port-failure' else '0',
               'GM8_TEST_POLICY_PORT_FAIL': '1' if case == 'policy-port-failure' else '0',
               'GM8_TEST_FIREWALL_PORT_FAIL': '1' if case == 'firewall-port-failure' else '0',
               'GM8_TEST_STATS_PORT_FAIL': '1' if case == 'stats-port-failure' else '0',
               'GM8_TEST_PORT_FAIL': '1' if case == 'port-failure' else '0',
               'GM8_TEST_PREFLIGHT_FAIL': '1' if case == 'preflight-failure' else '0',
               'GM8_TEST_M_EXIT': '17' if case in ('compile-failure', 'network-stats-failure', 'network-firewall-failure', 'network-policy-failure', 'network-sockets-failure') else '0'}
        bin_dir = parent / 'bin'; bin_dir.mkdir()
        repo = bin_dir / 'repo'
        repo.write_text('#!/bin/sh\nset -eu\nprintf "repo %s\\n" "$*" >> "$GM8_TEST_TRACE"\n'
                        'test "$1" = manifest\ntest "$2" = -r\ntest "$3" = -o\n'
                        'printf "<manifest/>\\n" > "$4"\n')
        repo.chmod(0o755)
        env['PATH'] = str(bin_dir) + os.pathsep + env['PATH']
        leaf = '''import os, sys
from pathlib import Path
name = Path(__file__).name
with Path(os.environ['GM8_TEST_TRACE']).open('a') as f: f.write(name + '\\n')
if name == 'apply-processgroup-20.0.py' and os.environ['GM8_TEST_PORT_FAIL'] == '1':
    raise SystemExit(23)
if name == 'apply-network-stats-20.0.py' and os.environ['GM8_TEST_STATS_PORT_FAIL'] == '1':
    raise SystemExit(24)
if name == 'apply-firewall-20.0.py' and os.environ['GM8_TEST_FIREWALL_PORT_FAIL'] == '1':
    raise SystemExit(25)
if name == 'apply-network-policy-20.0.py' and os.environ['GM8_TEST_POLICY_PORT_FAIL'] == '1':
    raise SystemExit(26)
if name == 'apply-socket-20.0.py' and os.environ['GM8_TEST_SOCKET_PORT_FAIL'] == '1':
    raise SystemExit(27)
if name == 'preflight-20.0.py' and os.environ['GM8_TEST_PREFLIGHT_FAIL'] == '1':
    raise SystemExit(9)
'''
        for name in ('preflight-20.0.py', 'fixup-legacy-protobuf.py', 'apply-processgroup-20.0.py',
                     'tests/processgroup_20_0_test.py', 'apply-network-stats-20.0.py',
                     'tests/network_stats_20_0_test.py', 'apply-firewall-20.0.py',
                     'tests/firewall_20_0_test.py', 'apply-network-policy-20.0.py',
                     'tests/network_policy_20_0_test.py', 'apply-socket-20.0.py', 'tests/socket_20_0_test.py',
                     'tests/kernel_host_link_test.py',
                     'tests/ft8006_gesture_test.py', 'tests/qsee_wait_test.py',
                     'tests/power_policy_test.py'):
            (tools / name).write_text(leaf)
        (top / 'build/envsetup.sh').write_text('''
lunch() { printf "lunch %s\\n" "$*" >> "$GM8_TEST_TRACE"; }
m() {
    printf "m %s\\n" "$*" >> "$GM8_TEST_TRACE"
    echo 'fixture native build output'
    return "$GM8_TEST_M_EXIT"
}
''')
        stage = case if case in ('audit', 'configure', 'compile', 'network-stats', 'network-firewall', 'network-policy', 'network-sockets') else (
            'invalid' if case == 'invalid-stage' else 'network-sockets' if case == 'network-sockets-failure' else 'network-stats' if case == 'network-stats-failure' else 'network-firewall' if case == 'network-firewall-failure' else 'network-policy' if case == 'network-policy-failure' else 'compile')
        result = subprocess.run(['bash', str(entry), stage], env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        calls = trace.read_text().splitlines() if trace.exists() else []
        make_calls = [x for x in calls if x.startswith('m ')]
        expected = 17 if case in ('compile-failure', 'network-stats-failure', 'network-firewall-failure', 'network-policy-failure', 'network-sockets-failure') else 27 if case == 'socket-port-failure' else 26 if case == 'policy-port-failure' else 25 if case == 'firewall-port-failure' else 24 if case == 'stats-port-failure' else 9 if case == 'preflight-failure' else 23 if case == 'port-failure' else (
            1 if case == 'wrong-sdk' else 2 if case == 'invalid-stage' else 0)
        assert result.returncode == expected, (case, result.returncode, result.stdout)
        if case == 'configure':
            assert make_calls == ['m nothing -j32']
        elif case in ('compile', 'compile-failure'):
            assert make_calls == ['m target-files-package -j32']
        elif case in ('network-stats', 'network-stats-failure'):
            assert make_calls == ['m libservice-connectivity -j32']
        elif case in ('network-sockets', 'network-sockets-failure'):
            assert make_calls == ['m netd -j32']
        elif case in ('network-firewall', 'network-firewall-failure'):
            assert make_calls == ['m netd -j32']
        elif case in ('network-policy', 'network-policy-failure'):
            assert make_calls == ['m netd service-connectivity -j32']
        else:
            assert not make_calls
        if case == 'audit':
            assert 'apply-processgroup-20.0.py' not in calls
            assert 'processgroup_20_0_test.py' not in calls
            assert 'apply-network-stats-20.0.py' not in calls
            assert 'network_stats_20_0_test.py' not in calls
            assert 'apply-firewall-20.0.py' not in calls
            assert 'firewall_20_0_test.py' not in calls
            assert 'apply-network-policy-20.0.py' not in calls
            assert 'apply-socket-20.0.py' not in calls
            assert 'network_policy_20_0_test.py' not in calls
        if case == 'port-failure':
            assert calls[-1] == 'apply-processgroup-20.0.py'
            assert 'preflight-20.0.py' not in calls
        if case == 'stats-port-failure':
            assert calls[-1] == 'apply-network-stats-20.0.py'
            assert 'preflight-20.0.py' not in calls
        if case == 'firewall-port-failure':
            assert calls[-1] == 'apply-firewall-20.0.py'
            assert 'preflight-20.0.py' not in calls
        if case == 'policy-port-failure':
            assert calls[-1] == 'apply-network-policy-20.0.py'
            assert 'preflight-20.0.py' not in calls
        if case == 'socket-port-failure':
            assert calls[-1] == 'apply-socket-20.0.py'
            assert 'preflight-20.0.py' not in calls
        if case == 'preflight-failure':
            assert not any('fixup' in x or x.startswith('lunch ') or 'test.py' in x for x in calls)
        if case in ('wrong-sdk', 'invalid-stage'):
            assert not calls
            assert not (parent / 'gm8-20.0-records').exists()
        if case in ('configure', 'compile', 'compile-failure', 'network-stats', 'network-stats-failure', 'network-firewall', 'network-firewall-failure', 'network-policy', 'network-policy-failure', 'network-sockets', 'network-sockets-failure'):
            assert 'lunch lineage_GM8_sprout-userdebug' in calls
            assert 'fixup-legacy-protobuf.py' in calls
            assert calls.index('apply-processgroup-20.0.py') < calls.index('preflight-20.0.py')
            assert 'processgroup_20_0_test.py' in calls
            assert 'network_stats_20_0_test.py' in calls
            assert 'firewall_20_0_test.py' in calls
            assert 'network_policy_20_0_test.py' in calls
            assert 'socket_20_0_test.py' in calls
            assert calls.index('apply-socket-20.0.py') < calls.index('preflight-20.0.py')
            assert calls.index('apply-network-policy-20.0.py') < calls.index('preflight-20.0.py')
            assert calls.index('apply-firewall-20.0.py') < calls.index('preflight-20.0.py')
            assert calls.index('apply-network-stats-20.0.py') < calls.index('preflight-20.0.py')
        if case in ('compile', 'compile-failure'):
            logs = list((parent / 'gm8-20.0-records').glob('*/compile.log'))
            assert len(logs) == 1 and 'fixture native build output' in logs[0].read_text()
            assert ('Build outputs were generated' in result.stdout) == (case == 'compile')
            assert 'No Android boot image' not in result.stdout
        if case in ('network-stats', 'network-stats-failure'):
            logs = list((parent / 'gm8-20.0-records').glob('*/network-stats.log'))
            assert len(logs) == 1 and 'fixture native build output' in logs[0].read_text()
            assert ('Native TrafficStats component compiled' in result.stdout) == (case == 'network-stats')
            assert 'm target-files-package' not in calls
            assert 'Build outputs were generated' not in result.stdout
        if case in ('network-firewall', 'network-firewall-failure'):
            logs = list((parent / 'gm8-20.0-records').glob('*/network-firewall.log'))
            assert len(logs) == 1 and 'fixture native build output' in logs[0].read_text()
            assert ('Native netd UID-firewall backend compiled' in result.stdout) == (case == 'network-firewall')
            assert 'm target-files-package' not in calls
            assert 'Build outputs were generated' not in result.stdout
        if case in ('network-policy', 'network-policy-failure'):
            logs = list((parent / 'gm8-20.0-records').glob('*/network-policy.log'))
            assert len(logs) == 1 and 'fixture native build output' in logs[0].read_text()
            assert ('Native bandwidth policy and Java netd routing compiled' in result.stdout) == (case == 'network-policy')
            assert 'm target-files-package' not in calls
            assert 'Build outputs were generated' not in result.stdout
        if case in ('network-sockets', 'network-sockets-failure'):
            logs = list((parent / 'gm8-20.0-records').glob('*/network-sockets.log'))
            assert len(logs) == 1 and 'fixture native build output' in logs[0].read_text()
            assert ('Native legacy socket backend compiled' in result.stdout) == (case == 'network-sockets')
            assert 'm target-files-package' not in calls
            assert 'Build outputs were generated' not in result.stdout
        if case == 'compile':
            assert 'not an installation OTA' in result.stdout
            assert 'runtime compatibility ports remain open' in result.stdout
        print('PASS:', case, '— real entry-point flow and exit status')
