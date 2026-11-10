#!/usr/bin/env python3
"""Verify actual legacy Kbuild host link rules with native C/C++ compilers.

Use a private library search path to make HOSTLDFLAGS necessary. This checks
flag propagation, not the Android Clang distribution or a kernel build.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def run(args, **kwargs):
    return subprocess.run(args, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    args = parser.parse_args()
    kernel = args.kernel.resolve()
    rules = (kernel / 'scripts/Makefile.host').read_text()
    fixdep = (kernel / 'scripts/basic/fixdep.c').read_bytes()
    cc = shutil.which(os.environ.get('CC', 'cc'))
    cxx = shutil.which(os.environ.get('CXX', 'c++'))
    ar = shutil.which('ar'); make = shutil.which('make'); nm = shutil.which('nm')
    if not all((cc, cxx, ar, make, nm)):
        raise SystemExit('Host linker regression requires cc, c++, ar, make and nm.')
    with tempfile.TemporaryDirectory(prefix='gm8-host-link-') as temp:
        root = Path(temp)
        src = root / 'src'; src.mkdir()
        lib = root / 'lib'; lib.mkdir()
        (src / 'fixdep.c').write_bytes(fixdep)
        (src / 'main.c').write_text('int helper(void); int main(void) { return helper(); }\n')
        (src / 'helper.c').write_text('int helper(void) { return 0; }\n')
        (src / 'cppmain.cc').write_text('extern "C" int helper(void); int main() { return helper(); }\n')
        result = run([ar, 'rcs', str(lib / 'libgm8_host_flags.a')])
        if result.returncode:
            raise SystemExit(result.stdout)

        def build(label, text, target):
            obj = root / label; obj.mkdir()
            include = root / (label + '.host.mk'); include.write_text(text)
            fixture = root / (label + '.mk')
            fixture.write_text(f'''.DEFAULT_GOAL := all
obj := {obj}
src := {src}
HOSTCC := {cc}
HOSTCXX := {cxx}
HOSTCFLAGS := -O2
HOSTCXXFLAGS := -O2
HOSTLDFLAGS := -L{lib} -Wl,--defsym=gm8_host_flag=1
HOST_LOADLIBES := -lgm8_host_flags
hostprogs-y := fixdep c_multi cpp_multi
c_multi-objs := main.o helper.o
cpp_multi-objs := helper.o
cpp_multi-cxxobjs := cppmain.o
basetarget = $(basename $(notdir $@))
depfile = $(dir $@).$(notdir $@).d
if_changed_dep = $(cmd_$(1))
if_changed = $(cmd_$(1))
include {include}
.PHONY: all FORCE
all: {obj}/fixdep {obj}/c_multi {obj}/cpp_multi
{obj}/c_multi: {obj}/main.o {obj}/helper.o
{obj}/cpp_multi: {obj}/cppmain.o {obj}/helper.o
FORCE:
''')
            command = [make, '-s', '-f', str(fixture)]
            if target:
                command.append(str(obj / target))
            return obj, run(command)

        # Reproduce the old single-C failure with the real rule, without
        # depending on whether GNU ld or Android ld.lld is in this host PATH.
        pattern = r'(cmd_host-csingle\s*=.*)'
        baseline = re.sub(pattern, lambda m: m[0].replace('$(HOSTLDFLAGS) ', ''), rules)
        _, failed = build('baseline', baseline, 'fixdep')
        if failed.returncode == 0 or 'gm8_host_flags' not in failed.stdout:
            raise SystemExit('Baseline did not reproduce missing linker flags:\n' + failed.stdout)
        print('PASS: old single-C rule loses the required library search path')

        obj, result = build('candidate', rules, None)
        if result.returncode:
            raise SystemExit('Kernel host linker rule failed:\n' + result.stdout)
        for name in ('fixdep', 'c_multi', 'cpp_multi'):
            symbols = run([nm, str(obj / name)])
            if symbols.returncode or not re.search(r'\bA gm8_host_flag$', symbols.stdout, re.M):
                raise SystemExit('HOSTLDFLAGS missing from linked host tool: ' + name)
        for name in ('c_multi', 'cpp_multi'):
            if run([str(obj / name)]).returncode:
                raise SystemExit('Linked host fixture failed to execute: ' + name)
        usage = run([str(obj / 'fixdep')])
        if usage.returncode != 1 or 'fixdep' not in usage.stdout.lower():
            raise SystemExit('Real fixdep failed its usage smoke check: ' + usage.stdout)
        print('PASS: real fixdep and C/C++ multi-object links honor HOSTLDFLAGS')
        print('PASS: linked host tools execute; Android Clang/kernel build still needs host validation')


if __name__ == '__main__':
    main()
