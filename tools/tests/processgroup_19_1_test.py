#!/usr/bin/env python3
from pathlib import Path
import argparse,subprocess,tempfile,re
parser=argparse.ArgumentParser(description='Host tests for actual GM8 processgroup source; requires Linux, git and g++.')
parser.add_argument('--top',type=Path,default=Path(__file__).resolve().parents[5])
top=parser.parse_args().top.resolve()
root=Path(__file__).resolve().parents[2]
src=(top/'system/core/libprocessgroup/processgroup.cpp').read_text()
helper=src[src.index('static bool GetProcessGroupControllerPath('):src.index('bool CgroupGetAttributePath(')]
kill=src[src.index('static int DoKillProcessGroupOnce('):src.index('static int KillProcessGroup(')]
convert=src[src.index('static std::string ConvertUidPidToPath('):src.index('static int RemoveProcessGroup(')]
program='''#include <string>
#include <set>
#include <memory>
#include <cstdio>
#include <cerrno>
#include <cassert>
#include <vector>
#include <filesystem>
#include <fstream>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/prctl.h>
#include <unistd.h>
#include <signal.h>
struct Logger {template<class T> Logger& operator<<(const T&){return *this;}};
#define LOG(x) Logger()
#define PLOG(x) Logger()
#define PROCESSGROUP_CGROUP_PROCS_FILE "/cgroup.procs"
const char* CGROUPV2_CONTROLLER_NAME="cgroup2";
struct Controller{bool usable;const char*root;bool IsUsable(){return usable;}const char*path(){return root;}};
struct CgroupMap{static bool v2,v1;static CgroupMap& GetInstance(){static CgroupMap x;return x;}Controller FindController(const char* name){bool unified=std::string(name)=="cgroup2";return {unified?v2:v1,unified?"/sys/fs/cgroup":"/acct"};}};
bool CgroupMap::v2=false;bool CgroupMap::v1=false;
template<class...A>std::string StringPrintf(const char*fmt,A...a){int n=snprintf(nullptr,0,fmt,a...);std::vector<char>b(n+1);snprintf(b.data(),b.size(),fmt,a...);return std::string(b.data(),n);}
'''+helper+convert+kill+'''
int child(pid_t group){pid_t pid=fork();assert(pid>=0);if(pid==0){prctl(PR_SET_PDEATHSIG,SIGKILL);setpgid(0,group);while(true)pause();}assert(setpgid(pid,group?group:pid)==0);return pid;}
int main(int argc,char**argv){assert(argc==2);std::string path;
 CgroupMap::v2=true;CgroupMap::v1=true;assert(GetProcessGroupControllerPath(&path)&&path=="/sys/fs/cgroup");
 CgroupMap::v2=false;assert(GetProcessGroupControllerPath(&path)&&path=="/acct");
 CgroupMap::v1=false;errno=0;assert(!GetProcessGroupControllerPath(&path)&&errno==ENODEV);
 CgroupMap::v2=true;assert(GetProcessGroupControllerPath(&path)&&path=="/sys/fs/cgroup");
 pid_t one=child(0),two=child(one);
 // Reproduce the old false success: a nonexistent hierarchy kills neither PID.
 assert(DoKillProcessGroupOnce("/nonexistent-gm8-fixture",1047,one,SIGKILL)==0);
 assert(::kill(one,0)==0&&::kill(two,0)==0);
 auto dir=ConvertUidPidToPath(argv[1],1047,one);std::filesystem::create_directories(dir);
 {std::ofstream out(dir+"/cgroup.procs");out<<one<<"\\n"<<two<<"\\n";}
 assert(DoKillProcessGroupOnce(argv[1],1047,one,SIGKILL)==2);
 int a=0,b=0;assert(waitpid(one,&a,0)==one);assert(waitpid(two,&b,0)==two);
 assert(WIFSIGNALED(a)&&WTERMSIG(a)==SIGKILL);assert(WIFSIGNALED(b)&&WTERMSIG(b)==SIGKILL);
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'check.cpp';p.write_text(program)
 subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-ignored-attributes',str(p),'-o',td+'/check'],check=True)
 subprocess.run([td+'/check',td],check=True,timeout=10)
print('PASS: actual controller selection prefers usable v2, falls back to mounted v1, fails without a hierarchy')
print('PASS: actual process-group killer reproduces missing-directory false success; kills both tracked child PIDs')

with tempfile.TemporaryDirectory() as td:
 top=Path(td);(top/'build/core').mkdir(parents=True);(top/'build/core/version_defaults.mk').write_text('PLATFORM_SDK_VERSION := 32\n')
 dest=top/'system/core/libprocessgroup/processgroup.cpp';dest.parent.mkdir(parents=True)
 dest.write_text(src)
 subprocess.run(['git','apply','--reverse',str(root/'patches/system_core/0001-gm8-cgroup-v1-process-tracking.patch')],cwd=top/'system/core',check=True)
 pristine=dest.read_text()
 (dest.parent/'keep-local.txt').write_text('preserve')
 cmd=['python3',str(root/'tools/apply-processgroup-compat.py'),'--top',str(top)]
 def run(expected,*args):
  r=subprocess.run(cmd+list(args),capture_output=True,text=True);assert r.returncode==expected,(r.stdout,r.stderr)
 run(1,'--check');run(0);run(0);run(0,'--check')
 assert (dest.parent/'keep-local.txt').read_text()=='preserve'
 # Restore just the fixture and introduce drift to confirm refusal before mutation.
 before=pristine.replace('bool CgroupGetAttributePath(const std::string& attr_name, std::string* path) {','bool CgroupGetAttributePath(const std::string& attr_name, std::string* path) { // local drift')
 dest.write_text(before);run(1);assert dest.read_text()==before
 (top/'build/core/version_defaults.mk').write_text('PLATFORM_SDK_VERSION := 30\n');run(1)
print('PASS: real upstream patch apply/check/repeat, local work preservation, drift refusal and SDK guard')
