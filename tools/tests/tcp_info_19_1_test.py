#!/usr/bin/env python3
"""Compile actual Android 12 TCP parsers against legacy and malformed attributes."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def block(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def clean(source):
    source = re.sub(r'^import (?:android\.|androidx\.|com.android.internal\.).*;\n',
                    '', source, flags=re.M)
    return re.sub(r'@(?:NonNull|Nullable|VisibleForTesting)\s*', '', source)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--top', type=Path, default=Path(__file__).resolve().parents[5])
parser.add_argument('--source', type=Path)
parser.add_argument('--java', default=shutil.which('java') or
                    '/usr/lib/jvm/java-17-openjdk-amd64/bin/java')
args = parser.parse_args()
repo = args.source or args.top / 'packages/modules/NetworkStack'
relative = 'src/com/android/networkstack/netlink/'
current = (repo / relative / 'TcpSocketTracker.java').read_text()
original = subprocess.check_output(['git', 'show', 'HEAD:' + relative + 'TcpSocketTracker.java'],
                                   cwd=repo, text=True)
info = (repo / relative / 'TcpInfo.java').read_text()
common = block(current, 'class RoutingAttribute {') + '\n' + block(current, 'class SocketInfo {')
methods = (block(original, 'SocketInfo parseSockInfo(').replace('parseSockInfo(', 'oldParse(', 1)
           + '\n' + block(original, 'private void skipRemainingAttributesBytesAligned(')
           + '\n' + block(current, 'SocketInfo parseSockInfo('))
source = r'''
package com.android.networkstack.netlink;
import java.nio.*;
public class ParserRegression {
 static final int AF_INET=2,AF_INET6=10,SOCKDIAG_MSG_HEADER_SIZE=88;
 void log(String message) {}
 METHODS
 COMMON
 static ByteBuffer message(int infoLength,boolean extra) {
  ByteBuffer b=ByteBuffer.allocate(50000).order(ByteOrder.nativeOrder());b.position(88);
  b.putShort((short)5).putShort((short)8).putInt(0);
  b.putShort((short)8).putShort((short)15).putInt(0x12345678);
  b.putShort((short)(infoLength+4)).putShort((short)2);
  int start=b.position();b.put((byte)1);b.position(start+infoLength);
  if(extra)b.putShort((short)7).putShort((short)99).putInt(0);
  b.limit(b.position());b.position(88);return b;
 }
 interface Check {void run();}
 static void rejected(Check c) {
  try {c.run();throw new AssertionError("malformed attribute accepted");}
  catch(IllegalArgumentException expected) {}
 }
 public static void main(String[] ignored) {
  ParserRegression p=new ParserRegression();ByteBuffer old=message(120,false);
  rejected(()->p.oldParse(old,AF_INET6,old.limit(),1));
  if(Log.errors==0)throw new AssertionError("old short-info failure missing");Log.errors=0;
  ByteBuffer legacy=message(120,false);
  SocketInfo result=p.parseSockInfo(legacy,AF_INET6,legacy.limit(),1);
  if(result.tcpInfo!=null||result.fwmark!=0x12345678||legacy.position()!=legacy.limit()
     ||Log.errors!=0)throw new AssertionError("legacy parse");
  for(boolean extra:new boolean[]{false,true}) {
   ByteBuffer modern=message(160,extra);result=p.parseSockInfo(modern,AF_INET,modern.limit(),2);
   if(result.tcpInfo==null||result.fwmark!=0x12345678||modern.position()!=modern.limit())
    throw new AssertionError("modern parse");
  }
  ByteBuffer bounded=message(120,false);int end=bounded.limit();bounded.limit(end+8);
  p.parseSockInfo(bounded,AF_INET,end,3);
  if(bounded.position()!=end)throw new AssertionError("message boundary");
  for(int len:new int[]{0,1,3,65535}) {
   ByteBuffer bad=message(120,false);bad.putShort(88,(short)len);
   rejected(()->p.parseSockInfo(bad,AF_INET,bad.limit(),0));
  }
  ByteBuffer shortHeader=message(120,false);shortHeader.limit(91);
  rejected(()->p.parseSockInfo(shortHeader,AF_INET,91,0));
  ByteBuffer badMark=message(120,false);badMark.putShort(96,(short)7);
  rejected(()->p.parseSockInfo(badMark,AF_INET,badMark.limit(),0));
  ByteBuffer shortMessage=message(120,false);
  rejected(()->p.parseSockInfo(shortMessage,AF_INET,shortMessage.limit()+4,0));
  ByteBuffer unsigned=ByteBuffer.allocate(40100).order(ByteOrder.nativeOrder());
  unsigned.position(88);unsigned.putShort((short)40004).putShort((short)99);
  unsigned.limit(40092);unsigned.position(88);p.parseSockInfo(unsigned,AF_INET,unsigned.limit(),0);
  if(unsigned.position()!=unsigned.limit())throw new AssertionError("unsigned length");
  System.out.println("PASS: old failure reproduced; legacy and modern INFO, marks, padding, boundaries, malformed and unsigned lengths checked");
 }
}
class NetlinkConstants {
 static int alignedLengthOf(int n){return(n+3)&~3;}
 static int alignedLengthOf(short n){return alignedLengthOf(Short.toUnsignedInt(n));}
}
class Log {
 static int errors;
 static int e(String tag,String message,Throwable cause){++errors;return 0;}
}
'''.replace('METHODS', methods).replace('COMMON', common)
with tempfile.TemporaryDirectory(prefix='gm8-tcp-info-') as temporary:
    root = Path(temporary)
    folder = root / 'src/com/android/networkstack/netlink'
    folder.mkdir(parents=True)
    (folder / 'ParserRegression.java').write_text(clean(source))
    (folder / 'TcpInfo.java').write_text(clean(info))
    subprocess.run([args.java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-d',
                    str(root / 'classes'), str(folder / 'ParserRegression.java'),
                    str(folder / 'TcpInfo.java')], check=True)
    subprocess.run([args.java, '-ea', '-cp', str(root / 'classes'),
                    'com.android.networkstack.netlink.ParserRegression'], check=True, timeout=10)
