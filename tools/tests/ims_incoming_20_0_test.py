#!/usr/bin/env python3
"""Run real IMS listener dispatch methods on host executor/Binder shims.

The disabled compatibility property reproduces a same-looper wait. The GM8
setting must deliver both call payloads, preserve executor/clean identity, and
allow the main queue to progress. This does not emulate modem or IMS sessions.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_java import find_java

ROOT=Path(__file__).resolve().parents[2]
TOP=None
JAVA=None


def method(text,signature):
    start=text.index(signature);opening=text.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end].replace('@NonNull ','')


class IncomingImsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(TOP/'frameworks/opt/telephony/src/java/com/android/internal/telephony/imsphone/ImsPhoneCallTracker.java').read_text()
        utility=(TOP/'frameworks/base/telephony/common/com/android/internal/telephony/util/TelephonyUtils.java').read_text()
        cls.actual='\n'.join(method(source,s) for s in (
            'public void onIncomingCall(IImsCallSession c, Bundle extras)',
            'private void executeAndWait(Runnable r)'))
        helpers='\n'.join(method(utility,s) for s in (
            'public static void runWithCleanCallingIdentity(\n            @NonNull Runnable action)',
            'public static void runWithCleanCallingIdentity(\n            @NonNull Runnable action, @NonNull Executor executor)'))
        cls.temp=tempfile.TemporaryDirectory(prefix='gm8-ims-incoming-')
        cls.addClassCleanup(cls.temp.cleanup);cls.work=Path(cls.temp.name)
        fixture=r'''
import java.util.*;
import java.util.concurrent.*;
public class IncomingFixture {
 static boolean block=true;
 static class SystemProperties {
  static boolean getBoolean(String key,boolean fallback) {
   if(!key.equals("ro.telephony.block_binder_thread_on_incoming_calls") || !fallback)throw new AssertionError("Unexpected property contract");
   return block;
  }
 }
 static class Binder {
  static ThreadLocal<Long> identity=ThreadLocal.withInitial(()->42L);
  static long clearCallingIdentity(){long old=identity.get();identity.set(0L);return old;}
  static void restoreCallingIdentity(long value){identity.set(value);}
 }
 static class TelephonyUtils { HELPERS }
 static class IImsCallSession { final int id; IImsCallSession(int id){this.id=id;} }
 static class Bundle { final String value; Bundle(String value){this.value=value;} }
 static class Listener {
  final Executor mExecutor;
  final List<String> events=Collections.synchronizedList(new ArrayList<>());
  final CountDownLatch processed=new CountDownLatch(2);
  Thread owner;
  Listener(Executor executor){mExecutor=executor;}
  void logw(String text){throw new AssertionError(text);}
  void processIncomingCall(IImsCallSession call,Bundle extras){
   if(Thread.currentThread()!=owner || Binder.identity.get()!=0L)throw new AssertionError("Wrong executor/identity");
   events.add(call.id+":"+extras.value);processed.countDown();
  }
  ACTUAL
 }
 static ExecutorService queue() {
  return Executors.newSingleThreadExecutor(r->{Thread t=new Thread(r,"phone-main");t.setDaemon(true);return t;});
 }
 static void expect(boolean value,String why){if(!value)throw new AssertionError(why);}
 static void legacy(boolean nonblocking) throws Exception {
  block=!nonblocking;
  ExecutorService main=queue();Listener listener=new Listener(main);
  CountDownLatch entered=new CountDownLatch(1);
  Future<?> callback=main.submit(()->{
   listener.owner=Thread.currentThread();entered.countDown();
   listener.onIncomingCall(new IImsCallSession(1),new Bundle("slot-1"));
   listener.onIncomingCall(new IImsCallSession(2),new Bundle("slot-2"));
  });
  expect(entered.await(2,TimeUnit.SECONDS),"Callback not scheduled");
  if(nonblocking){
   callback.get(2,TimeUnit.SECONDS);
   expect(listener.processed.await(2,TimeUnit.SECONDS),"Incoming payloads not processed");
   expect(listener.events.equals(Arrays.asList("1:slot-1","2:slot-2")),"Payload/order changed");
   expect(main.submit(()->Binder.identity.get()).get(2,TimeUnit.SECONDS)==42L,"Identity not restored");
   main.shutdownNow();
  }else{
   try{callback.get(200,TimeUnit.MILLISECONDS);throw new AssertionError("Expected same-looper deadlock");}
   catch(TimeoutException expected){}
   expect(listener.events.isEmpty(),"Blocked main queue ran callback");
   expect(Arrays.stream(listener.owner.getStackTrace()).anyMatch(f->f.getClassName().equals("java.util.concurrent.CompletableFuture") && f.getMethodName().equals("join")),"Not the original join wait");
   // Deliberately blocked control uses a daemon thread; process exits cleanly.
  }
 }
 static void remote() throws Exception {
  block=true;
  ExecutorService main=queue();Listener listener=new Listener(main);
  listener.owner=main.submit(()->Thread.currentThread()).get(2,TimeUnit.SECONDS);
  Thread binder=new Thread(()->{
   listener.onIncomingCall(new IImsCallSession(1),new Bundle("remote-1"));
   listener.onIncomingCall(new IImsCallSession(2),new Bundle("remote-2"));
  },"binder-caller");
  binder.start();binder.join(2000);
  expect(!binder.isAlive(),"Remote synchronous caller did not return");
  expect(listener.events.equals(Arrays.asList("1:remote-1","2:remote-2")),"Remote completion/order changed");
  main.shutdownNow();
 }
 public static void main(String[] args) throws Exception {
  switch(args[0]){
   case "legacy":legacy(true);break;
   case "control":legacy(false);break;
   case "remote":remote();break;
   default:throw new AssertionError("Unknown case");
  }
 }
}
'''.replace('HELPERS',helpers).replace('ACTUAL',cls.actual)
        (cls.work/'IncomingFixture.java').write_text(fixture)
        result=subprocess.run([JAVA,'-m','jdk.compiler/com.sun.tools.javac.Main',
            str(cls.work/'IncomingFixture.java')],text=True,capture_output=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)

    def run_case(self,name):
        result=subprocess.run([JAVA,'-cp',str(self.work),'IncomingFixture',name],
            text=True,capture_output=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_legacy_same_looper_delivers_both_payloads_without_wait(self):self.run_case('legacy')

    def test_default_blocking_mode_reproduces_same_looper_deadlock(self):self.run_case('control')

    def test_remote_default_dispatch_still_waits_for_processing(self):self.run_case('remote')

    def test_gm8_selects_supported_legacy_mode(self):
        key='ro.telephony.block_binder_thread_on_incoming_calls='
        selected=[line.strip() for line in (ROOT/'system.prop').read_text().splitlines()
                  if line.strip().startswith(key)]
        self.assertEqual(selected,[key+'false'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--top',required=True,type=Path)
    args,rest=p.parse_known_args();TOP=args.top.resolve();JAVA=find_java(TOP)
    unittest.main(argv=[__file__,*rest],verbosity=2)
