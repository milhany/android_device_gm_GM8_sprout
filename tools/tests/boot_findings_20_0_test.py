#!/usr/bin/env python3
"""Exercise the actual SDK33 legacy selection methods and paired device policy.

Syscalls and Android APIs are host fixtures; Android compilation, SELinux and
device behavior remain separate acceptance checks.
"""
import argparse
import ctypes
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from host_java import find_java

ROOT=Path(__file__).resolve().parents[2]
TOP=None


def method(text,signature):
    begin=text.index(signature);opening=text.index('{',begin);depth=1;end=opening+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[begin:end]


class BootFindingsTest(unittest.TestCase):
    def test_real_selinux_lookup_covers_every_built_root_alias(self):
        import re
        # This performs real libselinux file-context lookups, including inode
        # kinds. It does not claim to validate a compiled Android policy/image.
        lib=ctypes.CDLL('libselinux.so.1',use_errno=True)
        class Option(ctypes.Structure):
            _fields_=[('type',ctypes.c_int),('value',ctypes.c_char_p)]
        lib.selabel_open.argtypes=[ctypes.c_uint,ctypes.POINTER(Option),ctypes.c_uint]
        lib.selabel_open.restype=ctypes.c_void_p
        lib.selabel_lookup_raw.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p),ctypes.c_char_p,ctypes.c_int]
        lib.selabel_lookup_raw.restype=ctypes.c_int
        lib.freecon.argtypes=[ctypes.c_void_p]
        lib.selabel_close.argtypes=[ctypes.c_void_p]
        path=ROOT/'sepolicy/vendor/file_contexts'
        options=(Option*1)(Option(3,str(path).encode())) # SELABEL_OPT_PATH
        handle=lib.selabel_open(0,options,1) # SELABEL_CTX_FILE
        self.assertTrue(handle,'libselinux rejected device file_contexts')
        expected={'/bt_firmware':'bt_firmware_file','/firmware':'firmware_file',
                  '/dsp':'adsprpcd_file','/tombstones':'vendor_tombstone_data_file',
                  '/persist':'mnt_vendor_file'}
        board=re.sub(r'\\\n\s*',' ',(ROOT/'BoardConfig.mk').read_text())
        aliases=[]
        for value in re.findall(r'^BOARD_ROOT_EXTRA_SYMLINKS\s*[+:?]?=\s*(.*)$',board,re.M):
            aliases.extend('/'+entry.split(':',1)[1].lstrip('/') for entry in value.split())
        self.assertEqual(set(aliases),set(expected)-{'/persist'})
        self.assertRegex(board,r'BOARD_ROOT_EXTRA_FOLDERS\s*\+=\s*persist')
        try:
            for name in [*aliases,'/persist']:
                with self.subTest(path=name):
                    mode=stat.S_IFDIR if name=='/persist' else stat.S_IFLNK
                    result=ctypes.c_void_p()
                    status=lib.selabel_lookup_raw(handle,ctypes.byref(result),name.encode(),mode)
                    self.assertEqual(status,0,'No SELinux label for built root entry '+name)
                    try:self.assertEqual(ctypes.string_at(result).decode(),'u:object_r:'+expected[name]+':s0')
                    finally:lib.freecon(result)
                    result=ctypes.c_void_p()
                    status=lib.selabel_lookup_raw(handle,ctypes.byref(result),name.encode(),stat.S_IFREG)
                    if status==0:lib.freecon(result)
                    self.assertEqual(status,-1,'Root compatibility rule unexpectedly labels regular files')
        finally:lib.selabel_close(handle)

    def cpp(self,source,flags=()):
        with tempfile.TemporaryDirectory(prefix='gm8-boot-fixes-') as tmp:
            p=Path(tmp);(p/'test.cpp').write_text(source)
            result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',*flags,str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_libmeminfo_gpu_readers_never_construct_bpf_on_legacy(self):
        source=(TOP/'system/memory/libmeminfo/sysmeminfo.cpp').read_text()
        actual='\n'.join(method(source,sig) for sig in (
            'bool ReadPerProcessGpuMem(', 'bool ReadProcessGpuUsageKb(',
            'bool ReadGpuTotalUsageKb('))
        fixture=r'''
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <map>
#include <sstream>
#include <string>
#include <unordered_map>
bool legacy=true,valid=true,readError=false;
int constructed=0,propertyReads=0;
std::map<uint64_t,uint64_t> values;
namespace android::base {
bool GetBoolProperty(const char* key,bool fallback){
 assert(std::string(key)=="ro.kernel.ebpf.supported" && fallback);
 ++propertyReads;return !legacy;
}}
template<class T> struct Result {
 T data{};int code=0;
 bool ok() const{return code==0;}
 T value() const{assert(ok());return data;}
 struct Error {int number;int code() const{return number;}};
 Error error() const{return {code};}
};
namespace bpf {
template<class K,class V> struct BpfMapRO {
 explicit BpfMapRO(const char*) {assert(!legacy);++constructed;}
 bool isValid() const{return valid;}
 Result<K> getFirstKey() const {
  if(values.empty())return {{},ENOENT};
  return {values.begin()->first,0};
 }
 Result<K> getNextKey(K key) const {
  auto i=values.upper_bound(key);if(i==values.end())return {{},ENOENT};return {i->first,0};
 }
 Result<V> readValue(K key) const {
  if(readError)return {{},EIO};
  auto i=values.find(key);
  if(i==values.end())return {{},ENOENT};
  return {i->second,0};
 }
};}
#define LOG(x) std::ostringstream()
ACTUAL
int main(){
 uint64_t size=991;std::unordered_map<uint32_t,uint64_t> out{{77,13}};
#if defined(__ANDROID__) && !defined(__ANDROID_APEX__) && !defined(__ANDROID_VNDK__)
 constexpr bool platform=true;
#else
 constexpr bool platform=false;
#endif
 assert(!ReadGpuTotalUsageKb(&size));assert(size==(platform?991:0));
 assert(!ReadProcessGpuUsageKb(12,0,nullptr));
 assert(!ReadPerProcessGpuMem(&out));assert(out.at(77)==13);
 assert(!ReadPerProcessGpuMem(nullptr));assert(constructed==0);
#if defined(__ANDROID__) && !defined(__ANDROID_APEX__) && !defined(__ANDROID_VNDK__)
 assert(propertyReads==4);legacy=false;
 values={{0,8192},{12,2048},{(uint64_t{1}<<32)|12,4096}};
 assert(ReadGpuTotalUsageKb(&size) && size==8);
 assert(ReadProcessGpuUsageKb(12,1,&size) && size==4);
 assert(ReadProcessGpuUsageKb(12,1,nullptr));
 assert(ReadPerProcessGpuMem(&out) && out.size()==2 && out.at(12)==6 && out.at(0)==8);
 assert(!ReadPerProcessGpuMem(nullptr));
 assert(ReadProcessGpuUsageKb(99,0,&size) && size==0);
 valid=false;size=992;
 assert(!ReadGpuTotalUsageKb(&size) && size==992);assert(!ReadPerProcessGpuMem(&out));
 valid=true;readError=true;
 assert(!ReadProcessGpuUsageKb(12,0,&size));assert(!ReadPerProcessGpuMem(&out));
 readError=false;values.clear();out[77]=13;
 assert(ReadPerProcessGpuMem(&out) && out.empty());
#else
 assert(size==0 && propertyReads==0); // Existing non-platform API behavior.
#endif
}
'''.replace('ACTUAL',actual)
        for flags in (('-D__ANDROID__',),(),('-D__ANDROID__','-D__ANDROID_VNDK__'),
                      ('-D__ANDROID__','-D__ANDROID_APEX__')):
            with self.subTest(flags=flags):self.cpp(fixture,flags)

    def test_actual_bluetooth_music_headset_and_remote_profiles(self):
        import re
        mk=(ROOT/'device.mk').read_text().replace('\\\n',' ')
        product='\n'.join(re.findall(r'^PRODUCT_PRODUCT_PROPERTIES\s*\+=\s*(.*)$',mk,re.M))
        props=dict(re.findall(r'(bluetooth\.profile\.[\w.]+)=(\w+)',product))
        definitions=(TOP/'system/libsysprop/srcs/android/sysprop/BluetoothProperties.sysprop').read_text()
        api={}
        for block in re.findall(r'prop\s*\{(.*?)\}',definitions,re.S):
            name=re.search(r'api_name:\s*"([^"]+)"',block)
            key=re.search(r'prop_name:\s*"([^"]+)"',block)
            if name and key and re.search(r'type:\s*Boolean',block):
                api[name[1]]=key[1]
        self.assertTrue(props,'SDK33 classic profiles missing from product properties')
        self.assertTrue(set(props)<=set(api.values()),'Unknown Bluetooth sysprop')
        self.assertTrue(all(value=='true' for value in props.values()))
        self.assertFalse(any('.bap.' in key for key in props),'GM8 does not advertise LE Audio')
        services={'A2dpService':'a2dp','HeadsetService':'hfp','AvrcpTargetService':'avrcp'}
        classes=[];accessors=[]
        for name,folder in services.items():
            source=(TOP/'packages/modules/Bluetooth/android/app/src/com/android/bluetooth'/folder/(name+'.java')).read_text()
            actual=method(source,'public static boolean isEnabled()')
            accessor=re.search(r'BluetoothProperties\.(\w+)\(',actual)[1]
            self.assertEqual(props.get(api[accessor]),'true',name+' is disabled')
            accessors.append('static Optional<Boolean> '+accessor+'(){return Optional.ofNullable(props.get('+json.dumps(api[accessor])+')).map(Boolean::parseBoolean);}')
            classes.append('class '+name+'{'+actual+'}')
        fixture='import java.util.*;\nclass BluetoothProperties{static Map<String,String> props=new HashMap<>();'+''.join(accessors)+'}\n'+''.join(classes)+'''
public class ProfileSelectionTest {
 public static void main(String[] args) {
  assert !A2dpService.isEnabled() && !HeadsetService.isEnabled() && !AvrcpTargetService.isEnabled();
  INSERT_PROPERTIES
  assert A2dpService.isEnabled() && HeadsetService.isEnabled() && AvrcpTargetService.isEnabled();
  BluetoothProperties.props.put("bluetooth.profile.a2dp.source.enabled","false");
  assert !A2dpService.isEnabled() && HeadsetService.isEnabled();
 }
}'''.replace('INSERT_PROPERTIES','\n'.join('BluetoothProperties.props.put('+json.dumps(k)+','+json.dumps(v)+');' for k,v in props.items()))
        java=find_java(TOP)
        with tempfile.TemporaryDirectory(prefix='gm8-bt-profiles-') as tmp:
            p=Path(tmp);source=p/'ProfileSelectionTest.java';source.write_text(fixture)
            result=subprocess.run([java,'-m','jdk.compiler/com.sun.tools.javac.Main','-d',str(p),str(source)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([java,'-ea','-cp',str(p),'ProfileSelectionTest'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

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
