#!/usr/bin/env python3
from pathlib import Path
import argparse, re, subprocess, tempfile
parser=argparse.ArgumentParser(description='Host regressions for patched GM8 SDK 32 network sources; requires git and g++.')
parser.add_argument('--top',type=Path,default=Path(__file__).resolve().parents[5])
base=parser.parse_args().top.resolve()
device=Path(__file__).resolve().parents[2]
patches=[('system/bpf',base/'system/bpf',device/'patches/system_bpf/0001-gm8-legacy-bpf-loader.patch'),('system/netd',base/'system/netd',device/'patches/system_netd/0001-gm8-legacy-traffic-accounting.patch'),('packages/modules/NetworkStack',base/'packages/modules/NetworkStack',device/'patches/packages_modules_NetworkStack/0001-gm8-bound-legacy-tcp-info-attributes.patch')]
with tempfile.TemporaryDirectory() as td:
    top=Path(td)
    (top/'build/core').mkdir(parents=True)
    (top/'build/core/version_defaults.mk').write_text('PLATFORM_SDK_VERSION := 32\n')
    for project,repo,patch in patches:
        for name in re.findall(r'^\+\+\+ b/(.*)$',patch.read_text(),re.M):
            out=top/project/name
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(subprocess.check_output(['git','show','HEAD:'+name],cwd=repo))
    helper=['python3',str(device/'tools/apply-legacy-network-compat.py'),'--top',str(top)]
    def run(expected,*flags):
        r=subprocess.run(helper+list(flags),capture_output=True,text=True)
        assert r.returncode==expected,(r.stdout,r.stderr)
    run(1,'--check')
    first=top/'system/bpf/bpfloader/BpfLoader.cpp'
    original=first.read_bytes()
    second=top/'system/netd/server/TrafficController.cpp'
    before=second.read_text()
    second.write_text(before.replace('Status TrafficController::start() {','Status TrafficController::start() { // local drift'))
    run(1)
    assert first.read_bytes()==original,'modified first repo despite divergent second repo'
    second.write_text(before)
    third=top/'packages/modules/NetworkStack/src/com/android/networkstack/netlink/TcpSocketTracker.java'
    before_third=third.read_text()
    third.write_text(before_third.replace('final int remainingDataSize =', 'final long remainingDataSize ='))
    run(1)
    assert first.read_bytes()==original and second.read_text()==before, 'partially applied before final repo drift'
    third.write_text(before_third)
    (top/'system/netd/keep-local.txt').write_text('preserved\n')
    run(0)
    run(0)
    run(0,'--check')
    assert (top/'system/netd/keep-local.txt').read_text()=='preserved\n'
    for project,repo,patch in patches:
        subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=top/project,check=True)
    (top/'build/core/version_defaults.mk').write_text('PLATFORM_SDK_VERSION := 30\n')
    run(1)
print('PASS: three-project apply, check, repeat, drift refusal without partial apply, local work preservation, SDK rejection')

# Compile the actual patched command generator and its upstream expected output.
netd=base/'system/netd'
s=(netd/'server/BandwidthController.cpp').read_text()
t=(netd/'server/BandwidthControllerTest.cpp').read_text()
func=s[s.index('std::vector<std::string> getBasicAccountingCommands('):s.index('std::vector<std::string> toStrVec(')]
constants='\n'.join(re.search(r'const std::string '+n+r'\s*=.*?;',s,re.S)[0] for n in ['COMMIT_AND_CLOSE','HAPPY_BOX_MATCH_ALLOWLIST_COMMAND','BPF_HAPPY_BOX_MATCH_ALLOWLIST_COMMAND','BPF_PENALTY_BOX_MATCH_DENYLIST_COMMAND'])
expect='\n'.join(re.search(r'const std::string '+n+r'\s*=.*?;',t,re.S)[0] for n in ['ACCOUNT_RULES_WITHOUT_BPF','ACCOUNT_RULES_WITH_BPF'])
headers=(netd/'libnetdbpf/include/netdbpf/bpf_shared.h').read_text()+(netd/'server/NetdConstants.h').read_text()
macros='\n'.join(x for x in headers.splitlines() if re.match(r'#define (BPF_PATH|XT_BPF_(INGRESS|EGRESS|ALLOWLIST|DENYLIST)_PROG_PATH|IPSEC_IFACE_PREFIX)\b',x))
program='''#include <string>
#include <vector>
#include <cassert>
#include <cstdio>
#include <cstdint>
template<class... A> std::string StringPrintf(const char* fmt,A...args){
 int n=snprintf(nullptr,0,fmt,args...);std::vector<char>b(n+1);snprintf(b.data(),b.size(),fmt,args...);return std::string(b.data(),n);
}
constexpr unsigned MAX_SYSTEM_UID=9999;
constexpr uint32_t uidBillingMask=0x100000;
'''+macros+'\n'+constants+'\n'+func+'\n'+expect+'''
std::string join(const std::vector<std::string>&v){std::string s;for(auto&x:v){if(!s.empty())s+='\\n';s+=x;}return s;}
int main(){
 auto legacy=join(getBasicAccountingCommands(false));
 auto bpf=join(getBasicAccountingCommands(true));
 assert(legacy==ACCOUNT_RULES_WITHOUT_BPF);
 assert(bpf==ACCOUNT_RULES_WITH_BPF);
 assert(legacy.find("-m bpf")==std::string::npos);
 assert(legacy.find("-m owner --socket-exists")!=std::string::npos);
 assert(legacy.find("bw_data_saver")!=std::string::npos);
}
'''
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/'test.cpp';p.write_text(program)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(p),'-o',td+'/test'],check=True)
    subprocess.run([td+'/test'],check=True)
print('PASS: actual C++ accounting generator equals restored upstream expectations in both modes')

# Compile the actual loader main, replacing only platform I/O/ELF boundaries.
s=(base/'system/bpf/bpfloader/BpfLoader.cpp').read_text()
main=s[s.index('int main() {'):].replace('int main() {','int loader_main() {',1)
program='''#include <string>
#include <cassert>
#include <cstdio>
#include <cstdarg>
int setting=-1,dirs=0,loads=0,sets=0,delay=0,loadResult=0;bool propertyOk=true;
void logLine(const char* fmt,...){ (void)fmt; }
#define ALOGE(...) logLine(__VA_ARGS__)
namespace android { namespace base {
bool GetBoolProperty(const char* key,bool def){assert(std::string(key)=="ro.kernel.ebpf.supported");return setting<0?def:setting;}
bool SetProperty(const char* key,const char*value){assert(std::string(key)=="bpf.progs_loaded");assert(std::string(value)=="1");++sets;return propertyOk;}
}}
struct Loc{const char*dir;const char*prefix;};Loc locations[]={{"one","a"},{"two","b"}};
void createSysFsBpfSubDir(const char*){++dirs;}
int loadAllElfObjects(const char*,const char*){++loads;return loadResult;}
unsigned sleep(unsigned n){delay+=n;return 0;}
void reset(){dirs=loads=sets=delay=loadResult=0;propertyOk=true;}
'''+main+'''
int main(){
 reset();setting=0;loadResult=-38;assert(loader_main()==0);assert(dirs==0&&loads==0&&sets==1&&delay==0);
 reset();setting=1;assert(loader_main()==0);assert(dirs==2&&loads==2&&sets==1);
 reset();setting=-1;loadResult=-38;assert(loader_main()==2);assert(loads==1&&sets==0&&delay==20);
 reset();setting=1;loadResult=-38;assert(loader_main()==2);assert(loads==1&&sets==0&&delay==20);
 reset();setting=0;propertyOk=false;assert(loader_main()==1);assert(loads==0&&sets==1);
}
'''
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/'test.cpp';p.write_text(program)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(p),'-o',td+'/test'],check=True)
    subprocess.run([td+'/test'],check=True)
print('PASS: actual loader main skips unsupported BPF, signals readiness, retains fatal behavior by default/on enabled kernels and checks property failure')
