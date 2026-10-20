#!/usr/bin/env python3
"""Exercise Android's actual setup functions against read-only SAR ownership failure."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--top', type=Path, default=Path(__file__).resolve().parents[5])
parser.add_argument('--source', type=Path)
args = parser.parse_args()
device = Path(__file__).resolve().parents[2]
account = next(c for c in json.loads((device / 'configs/cgroups-gm8.json').read_text())['Cgroups']
               if c['Controller'] == 'cpuacct')
assert account['Path'] == '/acct'
source = (args.source or args.top / 'system/core/libprocessgroup/setup/cgroup_map_write.cpp').read_text()
methods = source[source.index('static bool ChangeDirModeAndOwner('):
                 source.index('static void MergeCgroupToDescriptors(')]
program = r'''
#include <cassert>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <grp.h>
#include <memory>
#include <pwd.h>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
struct Logger {template<class T> Logger& operator<<(const T&){return *this;}};
#define PLOG(level) Logger()
bool readOnlyRoot = true;
int ownershipCalls = 0;
passwd* test_getpwnam(const char*) {static passwd p{};p.pw_uid=1000;return &p;}
group* test_getgrnam(const char*) {static group g{};g.gr_gid=1000;return &g;}
int test_lchown(const char*,uid_t,gid_t) {
 ++ownershipCalls;if(readOnlyRoot){errno=EROFS;return -1;}return 0;
}
int test_fchmodat(int,const char*,mode_t,int) {
 if(readOnlyRoot){errno=EROFS;return -1;}return 0;
}
#define getpwnam test_getpwnam
#define getgrnam test_getgrnam
#define lchown test_lchown
#define fchmodat test_fchmodat
METHODS
int main(int argc,char**argv) {
 assert(argc==2);
 assert(!Mkdir(argv[1],0755,"system","system"));
 assert(ownershipCalls==1);ownershipCalls=0;
 assert(Mkdir(argv[1],MODE,UID,GID));assert(ownershipCalls==0);
 readOnlyRoot=false;
 assert(Mkdir(argv[1],0755,"system","system"));assert(ownershipCalls>0);
}
'''.replace('METHODS', methods).replace('MODE', str(int(account['Mode'], 8)))
program = program.replace('UID', json.dumps(account['UID'])).replace('GID', json.dumps(account['GID']))
with tempfile.TemporaryDirectory(prefix='gm8-cgroup-setup-') as temporary:
    path = Path(temporary)
    (path / 'acct').mkdir()
    (path / 'check.cpp').write_text(program)
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-Wno-ignored-attributes', '-Wno-sign-compare', str(path / 'check.cpp'),
                    '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check'), str(path / 'acct')], check=True)
print('PASS: actual setup reproduces read-only ownership failure; fixed descriptor preserves mount point; writable setup works')
