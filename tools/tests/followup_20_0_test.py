#!/usr/bin/env python3
"""Exercise actual mounted-cpuacct and WLAN parser functions with host OS/ABI shims."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
TOP = None


def method(text, signature):
    begin = text.index(signature)
    opening = text.index('{', begin)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[begin:end]


class FollowupTest(unittest.TestCase):
    def cpp(self, content):
        with tempfile.TemporaryDirectory(prefix='gm8-followup-') as tmp:
            p = Path(tmp)
            (p/'test.cpp').write_text(content)
            result = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-Wno-ignored-attributes', '-Wno-sign-compare', str(p/'test.cpp'),
                '-o', str(p/'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(p/'test'), str(p/'acct')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_cpuacct_mount_precedes_owner_change_and_isolated_group_creation(self):
        setup=(TOP/'system/core/libprocessgroup/setup/cgroup_map_write.cpp').read_text()
        process=(TOP/'system/core/libprocessgroup/processgroup.cpp').read_text()
        actual='\n'.join(method(setup, s) for s in ('static bool ChangeDirModeAndOwner(',
            'static bool Mkdir(', 'static bool SetupCgroup('))
        actual+='\n'+ '\n'.join(method(process, s) for s in ('static bool MkdirAndChown(',
            'static int createProcessGroupInternal('))
        fixture=r'''
#include <cassert>
#include <cerrno>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <fstream>
#include <grp.h>
#include <memory>
#include <pwd.h>
#include <string>
#include <sys/mount.h>
#include <sys/stat.h>
#include <unistd.h>
struct Logger {template<class T> Logger& operator<<(const T&){return *this;}};
#define LOG(x) Logger()
#define PLOG(x) Logger()
std::string root;bool mounted=false,legacy=true,mountError=false,ownerError=false;
uid_t caller=0,rootOwner=0;gid_t rootGroup=0;mode_t rootMode=0755;
int beforeMountChanges=0,activations=0;
passwd* user(const char* name){assert(std::string(name)=="system");static passwd p{};p.pw_uid=1000;return &p;}
group* groupName(const char* name){assert(std::string(name)=="system");static group g{};g.gr_gid=1000;return &g;}
bool rootEntry(const char* p){return std::string(p)==root || std::string(p)==root+"/.";}
int makeDir(const char* p,mode_t mode){
 if(caller==1000 && (rootOwner!=1000 || !(rootMode&S_IWUSR))){errno=EACCES;return -1;}
 int ret=::mkdir(p,mode);
 if(ret==0 && mounted)std::ofstream(std::string(p)+"/cgroup.procs");
 return ret;
}
int owner(const char* p,uid_t uid,gid_t gid){
 if(!mounted){++beforeMountChanges;errno=EROFS;return -1;}
 if(ownerError){errno=EACCES;return -1;}
 assert(uid==1000 && gid==1000);
 if(rootEntry(p)){rootOwner=uid;rootGroup=gid;}
 return 0;
}
int permissions(int,const char* p,mode_t mode,int){
 if(!mounted){++beforeMountChanges;errno=EROFS;return -1;}
 if(rootEntry(p))rootMode=mode;
 return ::chmod(p,mode&0777);
}
int metadata(const char* p,struct stat* st){
 int ret=::stat(p,st);if(ret==0&&rootEntry(p)){st->st_uid=rootOwner;st->st_gid=rootGroup;st->st_mode=S_IFDIR|rootMode;}return ret;
}
int attach(const char*,const char* path,const char*,unsigned long flags,const void* data){
 assert(std::string(path)==root && flags==(MS_NODEV|MS_NOEXEC|MS_NOSUID));
 assert(std::string(static_cast<const char*>(data))=="cpuacct");
 if(mountError){errno=EINVAL;return -1;}
 assert(beforeMountChanges==0);mounted=true;
 std::ofstream(root+"/cgroup.procs");std::ofstream(root+"/tasks");return 0;
}
namespace android::base {
bool GetBoolProperty(const char* key,bool fallback){assert(std::string(key)=="ro.vendor.gm8.legacy_cgroups"&&!fallback);return legacy;}
bool WriteStringToFile(const std::string& v,const std::string& p){std::ofstream f(p);f<<v;return f.good();}
}
using android::base::WriteStringToFile;
namespace base=android::base;
namespace format {struct CgroupController {
 int version()const{return 1;}const char* name()const{return "cpuacct";}
 const char* path()const{return root.c_str();}unsigned flags()const{return 0;}
};}
struct CgroupDescriptor {
 format::CgroupController c;const format::CgroupController* controller()const{return &c;}
 mode_t mode()const{return 0;}std::string uid()const{return "";}std::string gid()const{return "";}
};
struct CgroupMap {static CgroupMap GetInstance(){return {};}
 int ActivateControllers(const std::string&){++activations;return 0;}};
constexpr unsigned CGROUPRC_CONTROLLER_FLAG_NEEDS_ACTIVATION=1,CGROUPRC_CONTROLLER_FLAG_OPTIONAL=2;
constexpr char CGROUPV2_CONTROLLER_NAME[]="cgroup2";
constexpr unsigned AID_SYSTEM=1000;
constexpr char PROCESSGROUP_CGROUP_PROCS_FILE[]="/cgroup.procs";
std::string ConvertUidToPath(const char* p,unsigned uid){return std::string(p)+"/uid_"+std::to_string(uid);}
std::string ConvertUidPidToPath(const char* p,unsigned uid,int pid){return ConvertUidToPath(p,uid)+"/pid_"+std::to_string(pid);}
#define getpwnam user
#define getgrnam groupName
#define mkdir makeDir
#define lchown owner
#define fchmodat permissions
#define stat metadata
#define mount attach
ACTUAL
int main(int argc,char** argv){
 assert(argc==2);root=argv[1];assert(::makeDir(root.c_str(),0755)==0);
 CgroupDescriptor d;
 mountError=true;assert(!SetupCgroup(d) && !mounted && !beforeMountChanges);
 mountError=false;legacy=false;assert(SetupCgroup(d) && rootOwner==0);
 caller=1000;assert(createProcessGroupInternal(90000,4321,root,false)==-EACCES);
 caller=0;mounted=false;legacy=true;ownerError=true;
 assert(!SetupCgroup(d) && !beforeMountChanges);ownerError=false;
 assert(SetupCgroup(d) && mounted && rootOwner==1000 && rootGroup==1000 && rootMode==0750);
 assert(!beforeMountChanges);caller=1000;
 assert(createProcessGroupInternal(90000,4321,root,false)==0 && !activations);
 std::ifstream file(root+"/uid_90000/pid_4321/cgroup.procs");std::string pid;file>>pid;assert(pid=="4321");
 struct stat st;assert(::metadata((root+"/uid_90000").c_str(),&st)==0 && (st.st_mode&0777)==0750);
}
'''.replace('ACTUAL',actual)
        # The stat macro also names the C struct, so restore that token only.
        fixture=fixture.replace('struct metadata','struct stat')
        fixture=fixture.replace('#define stat metadata','#define stat(...) metadata(__VA_ARGS__)')
        self.cpp(fixture)

    def test_actual_wlan_parser_keeps_legacy_stats_and_rejects_bad_responses(self):
        src=(TOP/'hardware/qcom/wlan/wcn6740/qcwcn/wifi_hal/llstats.cpp').read_text()
        mk=(TOP/'hardware/qcom/wlan/wcn6740/qcwcn/wifi_hal/Android.mk').read_text()
        modules=[b for b in mk.split('include $(CLEAR_VARS)') if 'LOCAL_MODULE := libwifi-hal-qcom\n' in b]
        self.assertEqual(len(modules),2)
        for module in modules:self.assertRegex(module,r'LOCAL_SHARED_LIBRARIES\s*\+=\s*libcutils\b')
        actual=method(src,'static wifi_error get_wifi_interface_info(')
        attrs=sorted(set(re.findall(r'QCA_WLAN_VENDOR_ATTR_LL_STATS_IFACE_INFO_\w+',actual)))
        fixture=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
using u32=uint32_t;using wifi_error=int;using wifi_interface_mode=int;
using wifi_connection_state=int;using wifi_roam_state=int;
constexpr int WIFI_SUCCESS=0,WIFI_ERROR_INVALID_ARGS=-5;
enum { ATTRIBUTES, ATTRIBUTE_COUNT };
struct nlattr {int length=4;unsigned char bytes[64]{};};
int nla_len(nlattr* p){return p->length;}
void* nla_data(nlattr* p){return p->bytes;}
u32 nla_get_u32(nlattr* p){u32 v;memcpy(&v,p->bytes,4);return v;}
uint8_t nla_get_u8(nlattr* p){assert(p->length==1);return p->bytes[0];}
bool legacy=false;
bool property_get_bool(const char* key,bool fallback){assert(std::string(key)=="ro.vendor.gm8.legacy_wifi_stats"&&!fallback);return legacy;}
#define ALOGE(...) ((void)0)
#define QC_HAL_DEBUG 0
struct wifi_interface_link_layer_info {
 int mode,state,roaming;u32 capabilities;char mac_addr[6],ssid[33],bssid[6],ap_country_str[3],country_str[3];
 uint8_t time_slicing_duty_cycle_percent;
};
ACTUAL
int main(){
 nlattr payload[ATTRIBUTE_COUNT];nlattr* fields[ATTRIBUTE_COUNT];
 for(int i=0;i<ATTRIBUTE_COUNT;i++){fields[i]=&payload[i];payload[i].bytes[0]=7;}
 wifi_interface_link_layer_info stats{};
 auto key=QCA_WLAN_VENDOR_ATTR_LL_STATS_IFACE_INFO_TS_DUTY_CYCLE;
 fields[key]=nullptr;assert(get_wifi_interface_info(&stats,fields)==WIFI_ERROR_INVALID_ARGS);
 legacy=true;assert(get_wifi_interface_info(&stats,fields)==WIFI_SUCCESS);
 assert(stats.time_slicing_duty_cycle_percent==100 && stats.capabilities==7 && stats.mac_addr[0]==7);
 fields[QCA_WLAN_VENDOR_ATTR_LL_STATS_IFACE_INFO_STATE]=nullptr;
 assert(get_wifi_interface_info(&stats,fields)==WIFI_ERROR_INVALID_ARGS);
 fields[QCA_WLAN_VENDOR_ATTR_LL_STATS_IFACE_INFO_STATE]=&payload[QCA_WLAN_VENDOR_ATTR_LL_STATS_IFACE_INFO_STATE];
 fields[key]=&payload[key];legacy=false;payload[key].length=1;
 for(int value:{0,37,100}){payload[key].bytes[0]=value;assert(get_wifi_interface_info(&stats,fields)==WIFI_SUCCESS && stats.time_slicing_duty_cycle_percent==value);}
 for(int value:{101,255}){payload[key].bytes[0]=value;assert(get_wifi_interface_info(&stats,fields)==WIFI_ERROR_INVALID_ARGS);}
 for(int length:{0,2}){payload[key].length=length;assert(get_wifi_interface_info(&stats,fields)==WIFI_ERROR_INVALID_ARGS);}
}
'''.replace('ATTRIBUTES',','.join(attrs)).replace('ACTUAL',actual)
        self.cpp(fixture)

    def test_perf_manifest_and_scoped_wifi_property(self):
        manifest=ET.parse(ROOT/'configs/vintf/manifest.xml').getroot()
        perf=[h for h in manifest.findall('hal') if h.findtext('name')=='vendor.qti.hardware.perf']
        self.assertEqual(len(perf),1)
        h=perf[0];self.assertEqual(h.get('format'),'hidl');self.assertEqual(h.findtext('transport'),'hwbinder')
        self.assertEqual(h.findtext('version'),'1.0')
        self.assertEqual([(i.findtext('name'),i.findtext('instance')) for i in h.findall('interface')],[('IPerf','default')])
        self.assertIn('ro.vendor.gm8.legacy_wifi_stats=true',(ROOT/'vendor.prop').read_text())
        self.assertIn('get_prop(hal_wifi_default, vendor_gm8_wifi_stats_prop)',(ROOT/'sepolicy/vendor/hal_wifi_default.te').read_text())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--top',required=True,type=Path)
    args,rest=p.parse_known_args();TOP=args.top.resolve()
    unittest.main(argv=[__file__,*rest],verbosity=2)
