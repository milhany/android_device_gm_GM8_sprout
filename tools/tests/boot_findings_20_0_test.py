#!/usr/bin/env python3
"""Exercise the actual SDK33 legacy selection methods and paired device policy.

Syscalls and Android APIs are host fixtures; Android compilation, SELinux and
device behavior remain separate acceptance checks.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
TOP=None


def method(text,signature):
    begin=text.index(signature);opening=text.index('{',begin);depth=1;end=opening+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[begin:end]


class BootFindingsTest(unittest.TestCase):
    def cpp(self,source):
        with tempfile.TemporaryDirectory(prefix='gm8-boot-fixes-') as tmp:
            p=Path(tmp);(p/'test.cpp').write_text(source)
            result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_cgroup_and_profile_selection_legacy_and_default(self):
        core=TOP/'system/core/libprocessgroup'
        read=method((core/'setup/cgroup_map_write.cpp').read_text(),'static bool ReadDescriptors(')
        ctor=method((core/'task_profiles.cpp').read_text(),'TaskProfiles::TaskProfiles()')
        self.cpp('''#include <cassert>
#include <cerrno>
#include <map>
#include <string>
#include <vector>
#include <sstream>
#include <unistd.h>
bool legacy=false,api=false,fail=false;
std::vector<std::string> calls;
namespace android::base {
bool GetBoolProperty(const std::string& key,bool fallback) { assert(key=="ro.vendor.gm8.legacy_cgroups"); assert(!fallback); return legacy; }
std::string StringPrintf(const char*,unsigned) { return "/api"; }
}
template<class T> T GetUintProperty(const char*,T) { return api?28:0; }
int fake_access(const char* p,int) { if(std::string(p)=="/api" && !api){errno=ENOENT;return -1;} return 0; }
#define access fake_access
#define LOG(x) std::ostringstream()
constexpr const char* CGROUPS_DESC_FILE="/system-cgroups";
constexpr const char* CGROUPS_DESC_VENDOR_FILE="/vendor-cgroups";
constexpr const char* TEMPLATE_CGROUPS_DESC_API_FILE="/unused";
constexpr const char* TASK_PROFILE_DB_FILE="/system-profiles";
constexpr const char* TASK_PROFILE_DB_VENDOR_FILE="/vendor-profiles";
constexpr const char* TEMPLATE_TASK_PROFILE_API_FILE="/unused";
struct CgroupDescriptor {};
bool ReadDescriptorsFromFile(const std::string& p,std::map<std::string,CgroupDescriptor>*) { calls.push_back(p);return !fail; }
struct CgroupMap {static CgroupMap GetInstance(){return {};}};
struct TaskProfiles { TaskProfiles(); bool Load(CgroupMap,const std::string& p) {calls.push_back(p);return !fail;} };
'''+read+'\n'+ctor+'''
int main(){
 std::map<std::string,CgroupDescriptor> d;
 assert(ReadDescriptors(&d)); assert((calls==std::vector<std::string>{"/system-cgroups","/vendor-cgroups"}));
 calls.clear(); TaskProfiles a; assert((calls==std::vector<std::string>{"/system-profiles","/vendor-profiles"}));
 calls.clear();api=true; assert(ReadDescriptors(&d));assert((calls==std::vector<std::string>{"/system-cgroups","/api","/vendor-cgroups"}));
 calls.clear();TaskProfiles b;assert((calls==std::vector<std::string>{"/system-profiles","/api","/vendor-profiles"}));
 legacy=true;calls.clear();assert(ReadDescriptors(&d));assert((calls==std::vector<std::string>{"/vendor-cgroups"}));
 calls.clear();TaskProfiles c;assert((calls==std::vector<std::string>{"/vendor-profiles"}));
 calls.clear();fail=true;assert(!ReadDescriptors(&d));assert(calls.size()==1);
 calls.clear();TaskProfiles e;assert(calls.size()==1);
}
''')

    def test_actual_gpu_memory_init_and_destructor_never_wait_on_legacy(self):
        source=(TOP/'frameworks/native/services/gpuservice/gpumem/GpuMem.cpp').read_text()
        init=method(source,'void GpuMem::initialize()');destroy=method(source,'GpuMem::~GpuMem()')
        self.cpp('''#include <atomic>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <unistd.h>
bool legacy=true;int waits=0,lookups=0,attaches=0,detaches=0;
namespace base {bool GetBoolProperty(const char*,bool fallback){assert(fallback);return !legacy;}}
namespace bpf {
void waitForProgsLoaded(){++waits;}
int retrieveProgram(const char*){++lookups;return -1;}
template<class K,class V> struct BpfMap {bool isValid(){return true;}};
template<class K,class V> struct BpfMapRO:BpfMap<K,V> {explicit BpfMapRO(const char*){}};
}
int bpf_attach_tracepoint(int,const char*,const char*){++attaches;return 0;}
int bpf_detach_tracepoint(const char*,const char*){++detaches;return 0;}
#define ALOGI(...) ((void)0)
#define ALOGE(...) ((void)0)
class GpuMem { public: ~GpuMem();void initialize();void setGpuMemTotalMap(bpf::BpfMap<uint64_t,uint64_t>&){}
std::atomic<bool> mInitialized=false;static constexpr const char* kGpuMemTotalProgPath="p";
static constexpr const char* kGpuMemTraceGroup="g";static constexpr const char* kGpuMemTotalTracepoint="t";
static constexpr const char* kGpuMemTotalMapPath="m";static constexpr int kGpuWaitTimeout=30;
};
'''+init+'\n'+destroy+'''
int main(){
 {GpuMem g;g.initialize();assert(!g.mInitialized.load());}
 assert(waits==0 && lookups==0 && attaches==0 && detaches==0);
 legacy=false;{GpuMem g;g.initialize();assert(!g.mInitialized.load());}
 assert(waits==1 && lookups==1 && attaches==0 && detaches==1);
}
''')

    def test_complete_task_policy_has_no_unsupported_controller_references(self):
        c=json.loads((ROOT/'configs/cgroups-gm8.json').read_text())
        self.assertNotIn('Cgroups2',c)
        self.assertEqual({a['Controller']:a['Path'] for a in c['Cgroups']},{'cpu':'/dev/cpuctl','cpuset':'/dev/cpuset','cpuacct':'/acct'})
        p=json.loads((ROOT/'configs/task-profiles-gm8.json').read_text())
        attrs={a['Name'] for a in p['Attributes']};names={a['Name'] for a in p['Profiles']}
        self.assertEqual(len(names),40)
        self.assertEqual(len(p['AggregateProfiles']),15)
        for a in p['Attributes']:self.assertIn(a['Controller'],{'cpu','cpuset','cpuacct'})
        for profile in p['Profiles']:
            for action in profile['Actions']:
                params=action.get('Params',{})
                if action['Name']=='JoinCgroup':self.assertIn(params['Controller'],{'cpu','cpuset','cpuacct'})
                if action['Name']=='SetAttribute':self.assertIn(params['Name'],attrs)
                self.assertNotEqual(action['Name'],'SetClamps')
        for group in p['AggregateProfiles']:
            self.assertTrue(set(group['Profiles'])<=names)
        self.assertEqual(next(x for x in p['Profiles'] if x['Name']=='HighPerformance')['Actions'][0]['Params'],{'Controller':'cpu','Path':''})

    def test_actual_sensor_shell_keeps_qti_and_gates_ssc_by_binary(self):
        text=(TOP/'vendor/gm/GM8_sprout/proprietary/vendor/bin/init.qcom.sensors.sh').read_text()
        with tempfile.TemporaryDirectory(prefix='gm8-sensor-test-') as tmp:
            p=Path(tmp);binary=p/'sscrpcd';trace=p/'trace';persist=p/'persist'
            text=text.replace('/vendor/bin/sscrpcd',str(binary)).replace('/dev/msm_dsps','/dev/null').replace('/dev/sensors','/dev/null').replace('/persist/sensors',str(persist))
            script=p/'script.sh';script.write_text('getprop(){ :; }\nchmod(){ :; }\nchown(){ :; }\nstart(){ echo "$*" >> "'+str(trace)+'"; }\n'+text)
            for present in (False,True):
                if present:binary.write_text('fixture');binary.chmod(0o700)
                if trace.exists():trace.unlink()
                result=subprocess.run(['sh',str(script)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(trace.read_text().splitlines(),['vendor.sensors.qti']+(['vendor.sensors'] if present else []))

    def test_device_init_removes_hidl_duplicate_and_keeps_critical_services(self):
        import re
        texts=[(ROOT/'rootdir/etc'/name).read_text() for name in ('init.qcom.rc','init.target.rc')]
        names=re.findall(r'^service\s+(\S+)', '\n'.join(texts),re.M)
        self.assertEqual(len(names),len(set(names)))
        self.assertNotIn('wpa_supplicant',names)
        for name in ('vendor.rmt_storage','vendor.qseecomd','thermal-engine','vendor.imsqmidaemon','vendor.imsdatadaemon','wcnss-service'):
            self.assertIn(name,names)
        text='\n'.join(texts)
        self.assertNotIn('msm_11ad_proxy',text);self.assertNotIn('audio_machine_sdm450',text)
        self.assertNotIn('mkdir /data/tombstones',text)
        self.assertNotIn('property:sys.powerctl',text)
        self.assertIn('property:sys.powerctl',(ROOT/'rootdir/etc/init.gm8.system.rc').read_text())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--top',required=True,type=Path)
    args,rest=parser.parse_known_args();TOP=args.top.resolve()
    unittest.main(argv=[__file__,*rest],verbosity=2)
