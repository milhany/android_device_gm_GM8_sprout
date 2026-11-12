#!/usr/bin/env python3
"""Host checks of the complete source stack and actual changed method bodies.

Android classes/syscalls are explicit fixtures. This is not an Android build,
SELinux validation, a real network/VPN test or a hardware acceptance claim.
"""
import argparse
import ast
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOP = None
CONFIG = json.loads((ROOT / 'tools/runtime-stack-20.0.json').read_text())
spec = importlib.util.spec_from_file_location('stack', ROOT / 'tools/apply-runtime-stack-20.0.py')
STACK = importlib.util.module_from_spec(spec)
spec.loader.exec_module(STACK)
TESTS = Path(__file__).parent


def run(argv, **kwargs):
    return subprocess.run([str(x) for x in argv], text=True, capture_output=True, **kwargs)


def body(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def clean_java(source):
    import re
    return re.sub(r'@(?:NonNull|Nullable|VisibleForTesting)\s*', '', source)


class RuntimeStackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gm8-runtime-host-')
        self.addCleanup(self.temp.cleanup)
        self.host = Path(self.temp.name)

    def cpp(self, text, sources=(), flags=()):
        source = self.host / 'fixture.cpp'
        source.write_text(text)
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler)
        result = run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                      '-I', self.host, source, *sources, *flags, '-o', self.host/'fixture'])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run([self.host/'fixture', self.host])
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def java(self, sources, main, flags=(), args=()):
        for name, content in sources.items():
            p = self.host / 'src' / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        java = TOP/'prebuilts/jdk/jdk11/linux-x86/bin/java'
        if not java.is_file(): java = Path(shutil.which('java') or '/nonexistent')
        result = run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-source', '8',
                      '-target', '8', '-d', self.host/'classes', *sorted((self.host/'src').rglob('*.java'))])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run([java, '-ea', *flags, '-cp', self.host/'classes', main, *args])
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_real_socket_backend_old_bridges_and_new_lifecycle(self):
        server = TOP/'system/netd/server'
        for name in ('LegacySocketTagger.cpp', 'LegacySocketTagger.h'):
            shutil.copyfile(server/name, self.host/name)
        (self.host/'netdutils').mkdir();(self.host/'private').mkdir()
        (self.host/'netdutils/UidConstants.h').write_text('constexpr unsigned PER_USER_RANGE=100000;\n')
        (self.host/'private/android_filesystem_config.h').write_text('#define AID_ROOT 0\n#define AID_SYSTEM 1000\n#define AID_DNS 1051\n#define AID_CLAT 1029\n')
        fixture = (TESTS/'socket_20_0_fixture.cpp').read_text()
        rpc = body((server/'NetdNativeService.cpp').read_text(), 'binder::Status NetdNativeService::trafficSetNetPermForUids(')
        fwmark = (server/'FwmarkServer.cpp').read_text()
        fixture = fixture.replace('// BINDER_BODY', rpc)
        for kind in ('TAG', 'UNTAG'):
            method = body(fwmark, 'case FwmarkCommand::'+kind+'_SOCKET:')
            fixture = fixture.replace('// FWMARK_'+kind+'_BODY', method[method.index('{')+1:-1])
        fixture = fixture.replace('static bool unsupportedFamily', 'static bool clatSocket = false;\nstatic bool unsupportedFamily')
        fixture = fixture.replace('    if ((unsupportedFamily', '''    if (clatSocket && (option == SO_DOMAIN || option == SO_PROTOCOL)) {
        *static_cast<int*>(value) = option == SO_DOMAIN ? AF_INET6 : IPPROTO_RAW;
        return 0;
    }
    if ((unsupportedFamily''')
        fixture = fixture.replace('        Controllers controllers{tagger};', '''        assert(tagger.checkReady() == -ENOENT); // Missing real stats inputs is an error.
        assert(tagger.setCounterSet(10001, 1) == 0 && commands.back() == "s 1 10001");
        assert(tagger.setCounterSet(10001, 0) == 0 && commands.back() == "s 0 10001");
        assert(tagger.setCounterSet(10001, 2) == -EINVAL);
        assert(tagger.setCounterSet(UINT32_MAX, 0) == -EINVAL);
        assert(tagger.deleteTagData(10001) == 0 && commands.back() == "d 0 10001");
        assert(tagger.deleteTagData(UINT32_MAX) == -EINVAL);
        assert(tagger.tagClatSocket(tcp) == -EAFNOSUPPORT);
        clatSocket = true;
        assert(tagger.tagClatSocket(udp6) == 0);
        assert(commands.back() == "t " + std::to_string(udp6) + " 0 1029");
        assert(tagger.tagSocket(udp6, 0, 1029, 0) == -EPERM);
        assert(tagger.untagClatSocket(udp6) == 0);
        writeMode = 1; assert(tagger.setCounterSet(10001, 1) == -EPERM);
        writeMode = 2; assert(tagger.deleteTagData(10001) == -EIO);
        writeMode = 0; clatSocket = false;
        Controllers controllers{tagger};''')
        self.cpp(fixture, [self.host/'LegacySocketTagger.cpp'],
                 ['-Wl,--wrap='+name for name in ('getsockopt','open','close','write')])

    def test_ingress_ifindex_wildcard_lockdown_and_rollback(self):
        shutil.copyfile(TOP/'system/netd/server/LegacyIngressRules.h',self.host/'LegacyIngressRules.h')
        self.cpp(r'''
#include "LegacyIngressRules.h"
#include <cassert>
#include <sstream>
using android::net::LegacyIngressRules;
int main(int,char**) {
 std::vector<std::pair<bool,std::string>> writes; int calls=0,fail=0,fail2=0;unsigned index=7;
 LegacyIngressRules rules([&](bool v6,const std::string& text){writes.push_back({v6,text});++calls;return calls==fail||calls==fail2?-1:0;},
  [&](const std::string& name){return name=="tun0"?index:0;});
 assert(rules.setLockdown(10001,2)==-ENODEV);assert(rules.initialize()==0);
 assert(writes[0].second.find("-m bpf --bytecode")!=std::string::npos);
 assert(rules.setLockdown(10001,2)==0);assert(writes.back().second.find("--uid-owner 10001 -j DROP")!=std::string::npos);
 assert(rules.addInterfaces("tun0",{10001})==0);
 auto prior=writes.back().second;assert(prior.find(LegacyIngressRules::wrongInterface(7))!=std::string::npos);
 assert(prior.find("--uid-owner 10001 -j DROP")==std::string::npos);
 // A reused interface name resolves to a new index; old rules never grant it.
 index=8;assert(prior.find(LegacyIngressRules::wrongInterface(8))==std::string::npos);
 auto count=writes.size();assert(rules.addInterfaces("missing",{10001})==-ENODEV&&writes.size()==count);
 assert(rules.addInterfaces("tun0",{10001,-1})==-EINVAL&&writes.size()==count);
 assert(rules.addInterfaces("",{10001})==0);assert(writes.back().second.find("--uid-owner 10001")==std::string::npos);
 assert(rules.removeInterfaces({10001})==0);assert(writes.back().second.find("--uid-owner 10001 -j DROP")!=std::string::npos);
 prior=writes.back().second;fail=calls+2;assert(rules.setLockdown(10001,1)==-EREMOTEIO);
 assert(writes.back().first&&writes.back().second==prior); // IPv4 and IPv6 rollback
 fail=0;assert(rules.setLockdown(10001,1)==0);
 fail=calls+2;fail2=calls+3;assert(rules.setLockdown(10002,2)==-EREMOTEIO);
 assert(rules.setLockdown(10002,2)==-ENODEV);
 // Execute the actual generated classic bytecode with IFINDEX metadata.
 std::string program=LegacyIngressRules::wrongInterface(7);std::stringstream fields(program);std::string part;
 std::getline(fields,part,',');assert(part=="4");unsigned pc=0,acc=0;struct Ins{unsigned code,jt,jf,k;};std::vector<Ins> ins;
 while(std::getline(fields,part,',')){std::stringstream row(part);Ins i{};row>>i.code>>i.jt>>i.jf>>i.k;assert(row);ins.push_back(i);}
 for(unsigned iface:{1U,7U,8U,999U}){pc=0;acc=0;unsigned value=0;while(pc<ins.size()){auto i=ins[pc];if(i.code==32){assert(i.k==4294963208U);acc=iface;++pc;}else if(i.code==21)pc+=1+(acc==i.k?i.jt:i.jf);else{assert(i.code==6);value=i.k;break;}}assert((value!=0)==(iface!=7));}
}
''')

    def test_private_ipc_ack_errors_and_fd_transfer(self):
        shutil.copyfile(TOP/'system/netd/include/FwmarkCommand.h',self.host/'FwmarkCommand.h')
        shutil.copyfile(TOP/'packages/modules/Connectivity/service-t/jni/LegacyAccountingClient.h',self.host/'LegacyAccountingClient.h')
        self.cpp(r'''
#include "LegacyAccountingClient.h"
#include <cassert>
#include <fcntl.h>
#include <vector>
static int mode=0,closed=0,ack=0,sends=0,receives=0;static bool expectFd=false;
extern "C" int __wrap_socket(int domain,int type,int){assert(domain==AF_UNIX&&(type&SOCK_CLOEXEC));if(mode==1){errno=EMFILE;return-1;}return 70;}
extern "C" int __wrap_setsockopt(int,int,int,const void*,socklen_t){if(mode==2){errno=EINVAL;return-1;}return 0;}
extern "C" int __wrap_connect(int,const sockaddr* addr,socklen_t){assert(!strcmp(reinterpret_cast<const sockaddr_un*>(addr)->sun_path,"/dev/socket/fwmarkd"));if(mode==3){errno=ENOENT;return-1;}return 0;}
extern "C" ssize_t __wrap_sendmsg(int,const msghdr* msg,int flags){++sends;assert(flags==MSG_NOSIGNAL);auto c=static_cast<FwmarkCommand*>(msg->msg_iov[0].iov_base);assert(c->uid==10001&&c->netId==0);assert(c->trafficCtrlInfo==1&&c->cmdId==9);if(expectFd){auto h=CMSG_FIRSTHDR(msg);assert(h&&h->cmsg_type==SCM_RIGHTS&&*reinterpret_cast<int*>(CMSG_DATA(h))==23);}else assert(msg->msg_control==nullptr);if(mode==4)return 1;if(mode==5&&sends==1){errno=EINTR;return-1;}return sizeof(FwmarkCommand);}
extern "C" ssize_t __wrap_recv(int,void* data,size_t,int flags){++receives;assert(flags==MSG_WAITALL);if(mode==6)return 0;if(mode==7)return 1;if(mode==8){errno=EAGAIN;return-1;}if(mode==9&&receives==1){errno=EINTR;return-1;}*static_cast<int*>(data)=ack;return sizeof(int);}
extern "C" int __wrap_close(int fd){assert(fd==70);++closed;return 0;}
int main(int,char**){using android::gm8legacy::request;auto cmd=FwmarkCommand::_UNUSED_SET_COUNTERSET;
 std::vector<int> expected={0,-EMFILE,-EINVAL,-ENOENT,-EIO,0,-ECONNRESET,-EPROTO,-EAGAIN,0};
 for(mode=0;mode<10;++mode){closed=0;sends=receives=0;ack=0;assert(request(cmd,10001,1)==expected[mode]);assert(closed==(mode==1?0:1));}
 mode=0;ack=EACCES;assert(request(cmd,10001,1)==-EPROTO);ack=-EACCES;assert(request(cmd,10001,1)==-EACCES);
 ack=0;expectFd=true;assert(request(cmd,10001,1,23)==0);
}
''', flags=['-Wl,--wrap='+name for name in ('socket','setsockopt','connect','sendmsg','recv','close')])

    def test_stack_pristine_prefix_repeat_and_conflict_preserve_edits(self):
        # All source changes are prepared before any project is changed.
        target = self.host/'top'; target.mkdir()
        for item in CONFIG['projects']:
            project=target/item['path'];project.mkdir(parents=True)
            paths=set().union(*(STACK.patch_paths(ROOT/p) for p in item['patches']))
            for name in paths:
                source=TOP/item['path']/name
                if source.exists():
                    destination=project/name;destination.parent.mkdir(parents=True,exist_ok=True)
                    destination.write_bytes(source.read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            changes,_=STACK.prepare(target,Path(temp),CONFIG)
            self.assertEqual(changes,[]) # final candidate is idempotent
        # Reverse the full stack to form pristine inputs, then reapply a prefix.
        for item in CONFIG['projects']:
            project=target/item['path'];run(['git','init','-q',project])
            for patch in reversed(item['patches']):
                result=run(['git','-C',project,'apply','--reverse',ROOT/patch])
                self.assertEqual(result.returncode,0,result.stderr)
        marker=target/'system/netd/server/main.cpp'
        marker.write_text(marker.read_text()+'\n// unrelated local change\n')
        pristine=marker.read_bytes()
        for item in CONFIG['projects']:
            # Exercise a real prefix in each project.
            result=run(['git','-C',target/item['path'],'apply',ROOT/item['patches'][0]])
            self.assertEqual(result.returncode,0,result.stderr)
        with tempfile.TemporaryDirectory() as temp:
            changes,_=STACK.prepare(target,Path(temp),CONFIG);STACK.apply_changes(changes)
        self.assertTrue(marker.read_text().endswith('// unrelated local change\n'))
        with tempfile.TemporaryDirectory() as temp:
            changes,_=STACK.prepare(target,Path(temp),CONFIG);self.assertEqual(changes,[])
        # A conflict in the last project cannot mutate an earlier project.
        item=CONFIG['projects'][-1];project=target/item['path'];patch=ROOT/item['patches'][-1]
        result=run(['git','-C',project,'apply','--reverse',patch]);self.assertEqual(result.returncode,0,result.stderr)
        name=sorted(STACK.patch_paths(patch))[0];bad=project/name
        bad.write_text('unrelated incompatible source\n')
        snapshot={str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file() and '.git' not in p.parts}
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):STACK.prepare(target,Path(temp),CONFIG)
        self.assertEqual(snapshot,{str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file() and '.git' not in p.parts})
        # Inject a disk-write failure: previous files roll back byte-for-byte.
        first=self.host/'first';second=self.host/'second';first.write_bytes(b'old');second.write_bytes(b'old2')
        original_replace=STACK.replace;count=0
        def failing(path,data,mode):
            nonlocal count
            count+=1
            if count==2:raise OSError('injected disk error')
            original_replace(path,data,mode)
        STACK.replace=failing
        try:
            with self.assertRaises(OSError):STACK.apply_changes([(first,b'old',b'new',0o644),(second,b'old2',b'new2',0o644)])
        finally:STACK.replace=original_replace
        self.assertEqual(first.read_bytes(),b'old');self.assertEqual(second.read_bytes(),b'old2')

    def test_real_java_bpf_routing_legacy_and_default(self):
        # Reuse the explicit Android API fixtures, but compile the full FINAL class.
        tree=ast.parse((TESTS/'network_policy_20_0_test.py').read_text())
        stubs=next(ast.literal_eval(node.value) for node in ast.walk(tree)
                   if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='stubs' for t in node.targets))
        code=(TESTS/'NetworkPolicyFixture.java').read_text()
        code=code.replace('call("iif+");','call("iif+" + iface);')
        start=code.index('        int calls = netd.calls.size();')
        end=code.index('        BpfNetMaps missing',start)
        code=code[:start]+'''        netd.dead = false;
        maps.addUidInterfaceRules("tun0", new int[]{10001});
        check(netd.calls.get(netd.calls.size()-1).equals("iif+tun0"));
        maps.addUidInterfaceRules(null, new int[]{10001});
        check(netd.calls.get(netd.calls.size()-1).equals("iif+"));
        maps.removeUidInterfaceRules(new int[]{10001});
        check(netd.calls.get(netd.calls.size()-1).equals("iif-"));
        netd.failure = 22; error(22, () -> maps.removeUidInterfaceRules(new int[]{-1}));
        netd.failure = 0; netd.dead = true;
        try { maps.addUidInterfaceRules("tun0",new int[]{10001}); throw new AssertionError(); }
        catch (RemoteException expected) { }
        error(95, () -> maps.swapActiveStatsMap());
        error(95, () -> maps.dump(null, false));
''' + code[end:]
        stubs['com/android/server/NetworkPolicyFixture.java']=code
        stubs['com/android/server/BpfNetMaps.java']=(TOP/'packages/modules/Connectivity/service/src/com/android/server/BpfNetMaps.java').read_text()
        self.java(stubs,'com.android.server.NetworkPolicyFixture',['-Dro.kernel.ebpf.supported=false'], ['legacy'])
        java=TOP/'prebuilts/jdk/jdk11/linux-x86/bin/java'
        if not java.is_file():java=Path(shutil.which('java'))
        for mode in ('modern','default','pret','load-failure'):
            flags=[] if mode=='default' else ['-Dro.kernel.ebpf.supported=true']
            if mode=='pret':flags.append('-Dgm8.sdk.t=false')
            result=run([java,'-ea',*flags,'-cp',self.host/'classes','com.android.server.NetworkPolicyFixture',mode])
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_uid_counter_retry_and_purge_cache(self):
        text=(TOP/'packages/modules/Connectivity/service-t/src/com/android/server/net/NetworkStatsService.java').read_text()
        methods=clean_java(body(text,'public void noteUidForeground(')+'\n'+body(text,'private void deleteKernelTagData('))
        # The BPF-only tail is compiled against typed map fixtures as well.
        source=r'''
import java.util.*;
public class CounterFixture {
 static final int SET_DEFAULT=0,SET_FOREGROUND=1;static final String TAG="fixture";
 final Object mStatsLock=new Object(),mContext=new Object();boolean mUseBpfStats;
 static class ErrnoException extends Exception {}
 static class MapFixture {java.util.Map<Integer,Integer> map=new HashMap<>();int get(int k,int d){return map.getOrDefault(k,d);}void put(int k,int v){map.put(k,v);}void delete(int k){map.remove(k);}}
 final MapFixture mActiveUidCounterSet=new MapFixture();
 static class Dependency {int writes,purges;boolean fail;void setLegacyCounterSet(int uid,int set)throws ErrnoException{++writes;if(fail)throw new ErrnoException();}void deleteLegacyTagData(int uid)throws ErrnoException{++purges;if(fail)throw new ErrnoException();}}
 final Dependency mDeps=new Dependency();
 static class Factory {int removed;void removeLegacyUids(int[] uids){removed=uids[0];}}
 final Factory mStatsFactory=new Factory();int modern;
 void setKernelCounterSet(int uid,int set){++modern;}
 static class Log {static void e(String t,String s,Exception e){}}
 static class PermissionUtils {static boolean allowed=true;static void enforceNetworkStackPermission(Object c){if(!allowed)throw new SecurityException();}}
 static class Key {int uid;}static class Value {int uid;}
 interface Visitor {void visit(Key k,Value v);}
 static class BpfMap {void forEach(Visitor v)throws ErrnoException{}void deleteEntry(Object key)throws ErrnoException{}}
 static class U32 {U32(int v){}}static class UidStatsMapKey {UidStatsMapKey(int v){}}
 final BpfMap mCookieTagMap=new BpfMap(),mStatsMapA=new BpfMap(),mStatsMapB=new BpfMap(),mUidCounterSetMap=new BpfMap(),mAppUidStatsMap=new BpfMap();
 void deleteStatsMapTagData(BpfMap m,int uid){}void logErrorIfNotErrNoent(ErrnoException e,String msg){}
 METHODS
 public static void main(String[] args){CounterFixture f=new CounterFixture();
 f.mDeps.fail=true;f.noteUidForeground(10001,true);if(f.mActiveUidCounterSet.get(10001,0)!=0||f.mDeps.writes!=1)throw new AssertionError();
 f.mDeps.fail=false;f.noteUidForeground(10001,true);f.noteUidForeground(10001,true);if(f.mDeps.writes!=2||f.mActiveUidCounterSet.get(10001,0)!=1)throw new AssertionError();
 f.mDeps.fail=true;f.deleteKernelTagData(10001);if(f.mStatsFactory.removed!=0||f.mActiveUidCounterSet.get(10001,0)!=1)throw new AssertionError();
 f.mDeps.fail=false;f.deleteKernelTagData(10001);if(f.mStatsFactory.removed!=10001||f.mActiveUidCounterSet.get(10001,0)!=0)throw new AssertionError();
 f.mUseBpfStats=true;f.noteUidForeground(10001,true);if(f.modern!=1||f.mDeps.writes!=2)throw new AssertionError();
 PermissionUtils.allowed=false;try{f.noteUidForeground(10002,true);throw new AssertionError();}catch(SecurityException expected){}
 }
}
'''.replace('METHODS',methods)
        self.java({'CounterFixture.java':source},'CounterFixture')

    def test_actual_wifi_mac_persistence_and_default_keystore_path(self):
        text=(TOP/'packages/modules/Wifi/service/java/com/android/server/wifi/WifiConfigManager.java').read_text()
        method=body(text,'public MacAddress getPersistentMacAddress(')
        source=r'''
import java.util.*;
public class WifiFixture {
 static final String TAG="test";static boolean legacy;static int generated;
 static class SystemProperties {static boolean getBoolean(String key,boolean fallback){return legacy;}}
 static class MacAddress {final String value;MacAddress(String v){value=v;}static MacAddress fromString(String v){if(!v.matches("([0-9a-f]{2}:){5}[0-9a-f]{2}"))throw new IllegalArgumentException();return new MacAddress(v);}public String toString(){return value;}public boolean equals(Object o){return o instanceof MacAddress&&value.equals(o.toString());}}
 static final MacAddress DEFAULT_MAC_ADDRESS=new MacAddress("02:00:00:00:00:00");
 static class WifiConfiguration {String key;MacAddress mac=DEFAULT_MAC_ADDRESS;WifiConfiguration(String k){key=k;}String getNetworkKey(){return key;}MacAddress getRandomizedMacAddress(){return mac;}static boolean isValidMacAddressForRandomization(MacAddress m){return m!=null&&!m.equals(DEFAULT_MAC_ADDRESS)&&((Integer.parseInt(m.value.substring(0,2),16)&3)==2);}}
 static class MacAddressUtils {static MacAddress createRandomUnicastAddress(){return new MacAddress(String.format("02:00:00:00:01:%02x",++generated));}}
 static class Process {static int WIFI_UID=1010;}
 static class Log {static void e(String t,String m){}static void wtf(String t,String m){}}
 static class Util {int keystore;Object obtainMacRandHashFunction(int uid){++keystore;return this;}MacAddress calculatePersistentMac(String key,Object hash){return new MacAddress("02:00:00:00:02:01");}}
 final Util mMacAddressUtil=new Util();final Map<String,String> mRandomizedMacAddressMapping=new HashMap<>();
 METHOD
 public static void main(String[] args){legacy=true;WifiFixture f=new WifiFixture();WifiConfiguration a=new WifiConfiguration("a");MacAddress first=f.getPersistentMacAddress(a);
 if(!f.getPersistentMacAddress(a).equals(first)||f.mMacAddressUtil.keystore!=0)throw new AssertionError();
 WifiFixture reloaded=new WifiFixture();reloaded.mRandomizedMacAddressMapping.putAll(f.mRandomizedMacAddressMapping);if(!reloaded.getPersistentMacAddress(a).equals(first))throw new AssertionError();
 if(f.getPersistentMacAddress(new WifiConfiguration("b")).equals(first))throw new AssertionError();
 f.mRandomizedMacAddressMapping.put("c","00:11:22:33:44:55");if(!WifiConfiguration.isValidMacAddressForRandomization(f.getPersistentMacAddress(new WifiConfiguration("c"))))throw new AssertionError();
 f.mRandomizedMacAddressMapping.put("d","invalid");f.getPersistentMacAddress(new WifiConfiguration("d"));
 WifiConfiguration e=new WifiConfiguration("e");e.mac=new MacAddress("02:11:22:33:44:55");if(!f.getPersistentMacAddress(e).equals(e.mac))throw new AssertionError();
 legacy=false;f.getPersistentMacAddress(new WifiConfiguration("default"));if(f.mMacAddressUtil.keystore!=1)throw new AssertionError();
 }
}
'''.replace('METHOD',method)
        self.java({'WifiFixture.java':source},'WifiFixture')

    def test_actual_radio_hal_selection_and_single_dsds_commands(self):
        radio=(TOP/'frameworks/opt/telephony/src/java/com/android/internal/telephony/RadioConfig.java').read_text()
        switch=(TOP/'frameworks/opt/telephony/src/java/com/android/internal/telephony/data/PhoneSwitcher.java').read_text()
        selection=body(radio,'public boolean isSetPreferredDataCommandSupported(')
        methods=body(switch,'private void updateHalCommandToUse(')+'\n'+body(switch,'protected void sendRilCommands(')
        source=r'''
public class RadioFixture {
 static boolean legacy,empty;static int version=11,calls,preferred;static final int RADIO_CONFIG_HAL_VERSION_1_1=11;
 static class SystemProperties {static boolean getBoolean(String key,boolean fallback){return legacy;}}
 static class Version {boolean greaterOrEqual(int v){return version>=v;}}
 static class RadioConfigProxy {boolean isEmpty(){return empty;}Version getVersion(){return new Version();}}
 RadioConfigProxy getRadioConfigProxy(Object unused){return new RadioConfigProxy();}
 SELECTION
 static final int HAL_COMMAND_UNKNOWN=0,HAL_COMMAND_ALLOW_DATA=1,HAL_COMMAND_PREFERRED_DATA=2,EVENT_MODEM_COMMAND_DONE=7;
 int mHalCommandToUse,mActiveModemCount=1,mPreferredDataPhoneId=1;RadioFixture mRadioConfig=this;
 static class SubscriptionManager {static boolean isValidPhoneId(int id){return id>=0&&id<2;}}
 static class Message {static Message obtain(Object owner,int what,int id){return new Message();}}
 static class Ci {void setDataAllowed(boolean allowed,Message m){++calls;}}
 static class Phone {Ci mCi=new Ci();}static class PhoneFactory {static Phone getPhone(int id){return new Phone();}}
 boolean isPhoneActive(int id){return id==1;}void log(String text){}void setPreferredDataModem(int id,Message message){++preferred;}
 METHODS
 public static void main(String[] args){RadioFixture f=new RadioFixture();legacy=true;f.updateHalCommandToUse();if(f.mHalCommandToUse!=1)throw new AssertionError();
 f.sendRilCommands(0);if(calls!=0)throw new AssertionError();f.mActiveModemCount=2;f.sendRilCommands(0);f.sendRilCommands(1);if(calls!=2||preferred!=0)throw new AssertionError();
 f.sendRilCommands(-1);if(calls!=2)throw new AssertionError();legacy=false;f.updateHalCommandToUse();f.sendRilCommands(0);f.sendRilCommands(1);if(preferred!=1||calls!=2)throw new AssertionError();
 empty=true;f.updateHalCommandToUse();if(f.mHalCommandToUse!=1)throw new AssertionError();empty=false;version=10;if(f.isSetPreferredDataCommandSupported())throw new AssertionError();
 }
}
'''.replace('SELECTION',selection).replace('METHODS',methods)
        self.java({'RadioFixture.java':source},'RadioFixture')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top',type=Path,required=True)
    TOP=parser.parse_args().top.resolve(strict=True)
    unittest.main(argv=[sys.argv[0]],verbosity=2)
