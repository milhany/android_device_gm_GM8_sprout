#!/usr/bin/env python3
"""Exercise the source editor and actual SDK 32 ART madvise loop on a host.

Inputs are the owner's unmodified Lineage 19.1 runtime_libart.mk/runtime.cc.
The actual madvise system call is substituted; this does not benchmark a phone.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def function(source):
    start = source.index('void Runtime::MadviseFileForRange(')
    brace = source.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-libart', type=Path, required=True)
parser.add_argument('--art-runtime', type=Path, required=True)
args = parser.parse_args()
helper = Path(__file__).resolve().parents[1] / 'apply-art-prefetch-compat.py'
original = args.runtime_libart.read_text()
assert 'dalvik.vm.madvise.odexfile.size=104857600' in original
assert 'dalvik.vm.madvise.vdexfile.size=104857600' in original

with tempfile.TemporaryDirectory(prefix='gm8-art-prefetch-') as td:
    top = Path(td)
    version = top / 'build/core/version_defaults.mk'
    version.parent.mkdir(parents=True)
    version.write_text('PLATFORM_SDK_VERSION := 32\n')
    source = top / 'build/make/target/product/runtime_libart.mk'
    source.parent.mkdir(parents=True)
    original += '\n# Fixture unrelated local edit must be preserved.\n'
    source.write_text(original)

    def run(expected, *extra):
        result = subprocess.run(['python3', str(helper), '--top', str(top), *extra],
                                capture_output=True, text=True)
        assert result.returncode == expected, result.stdout + result.stderr

    run(1, '--check')
    assert source.read_text() == original
    run(0)
    bounded = source.read_text()
    expected = original.replace('dalvik.vm.madvise.odexfile.size=104857600',
                                'dalvik.vm.madvise.odexfile.size=16777216').replace(
                                'dalvik.vm.madvise.vdexfile.size=104857600',
                                'dalvik.vm.madvise.vdexfile.size=16777216')
    assert bounded == expected
    run(0); run(0, '--check')
    assert source.read_text() == bounded
    run(0, '--restore'); run(0, '--restore')
    assert source.read_text() == original
    for bad in (original.replace('vdexfile.size=104857600', 'vdexfile.size=12345'),
                original + '\ndalvik.vm.madvise.odexfile.size=104857600\n'):
        source.write_text(bad)
        run(1)
        assert source.read_text() == bad
    source.write_text(original)
    version.write_text('PLATFORM_SDK_VERSION := 31\n')
    run(1)
    assert source.read_text() == original

    # Compile the actual upstream function, keeping its size cap, chunk loop,
    # end-of-mapping clamp and error path. Replace only OS/Android facilities.
    cpp = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#define LOG(x) std::cerr
constexpr int MADV_WILLNEED = 3;
struct Call { const uint8_t* address; size_t length; };
std::vector<Call> calls;
bool fail = false;
int madvise(void* address, size_t length, int advice) {
    assert(advice == MADV_WILLNEED);
    calls.push_back({static_cast<uint8_t*>(address), length});
    return fail ? -1 : 0;
}
struct ScopedTrace { explicit ScopedTrace(const std::string&) {} };
namespace art {
struct Runtime {
  static void MadviseFileForRange(size_t, size_t, const uint8_t*, const uint8_t*, const std::string&);
};
/* ACTUAL ART FUNCTION */
}
int main() {
    constexpr size_t MiB = 1024 * 1024;
    std::vector<uint8_t> mapping(128 * MiB);
    auto base = mapping.data();
    auto check = [&](size_t limit, size_t length, size_t end, size_t expected) {
        calls.clear();
        art::Runtime::MadviseFileForRange(limit, length, base, base + end, "fixture.odex");
        size_t total = 0;
        for (const auto& c : calls) {
            assert(c.address == base + total);
            assert(c.length > 0 && c.length <= 128 * 1024);
            total += c.length;
        }
        assert(total == expected);
    };
    check(104857600, 128 * MiB, 128 * MiB, 100 * MiB);
    check(16777216, 128 * MiB, 128 * MiB, 16 * MiB);
    check(16777216, MiB, MiB, MiB);
    check(16777216, 128 * MiB, MiB + 123, MiB + 123);
    check(0, 128 * MiB, 128 * MiB, 0);
    calls.clear(); fail = true;
    art::Runtime::MadviseFileForRange(16777216, 128 * MiB, base,
                                    base + mapping.size(), "fixture.odex");
    assert(calls.size() == 1);
}
'''
    cpp = cpp.replace('/* ACTUAL ART FUNCTION */', function(args.art_runtime.read_text()))
    (top / 'actual-art-loop.cc').write_text(cpp)
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-O2',
                    str(top / 'actual-art-loop.cc'), '-o', str(top / 'actual-art-loop')], check=True)
    subprocess.run([str(top / 'actual-art-loop')], check=True, capture_output=True)

print('PASS: real runtime_libart defaults, idempotent apply/check/restore, unrelated edits, '
      'drift/duplicate/SDK refusal without partial writes')
print('PASS: actual ART loop requests 16 instead of 100 MiB, small-file and mapping clamps, '
      '128 KiB chunks, zero limit and madvise failure stop')
