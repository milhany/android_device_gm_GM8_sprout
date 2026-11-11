package com.android.server.net;
import android.content.Context;
import android.net.NetworkStats;
import android.os.StrictMode;
import com.android.server.BpfNetMaps;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CumulativeSnapshotFixture {
    static void check(boolean value){if(!value)throw new AssertionError();}
    interface Operation {void run() throws Exception;}
    static void ioError(Operation action)throws Exception{try{action.run();}catch(IOException expected){return;}throw new AssertionError("Expected IO failure");}
    static void put(Path file,String value)throws Exception{Files.write(file,value.getBytes(StandardCharsets.UTF_8));}
    static String read(Path file)throws Exception{return new String(Files.readAllBytes(file),StandardCharsets.UTF_8);}
    static long bytes(NetworkStats stats){long total=0;for(NetworkStats.Entry row:stats.rows)total+=row.rxBytes;return total;}
    public static void main(String[] args)throws Exception{
        String mode=args[0];Path root=Path.of(args[1]);Context context=new Context();
        new NetworkStatsFactory(context); // Exercise the real default backend selector.
        if(!mode.equals("legacy")){
            check(BpfNetMaps.created==1);
            NetworkStatsFactory modern=new NetworkStatsFactory(context,root.toFile(),true);
            ioError(()->modern.readNetworkStatsSummaryDev());
            ioError(()->modern.readNetworkStatsSummaryXt());
            ioError(()->modern.readNetworkStatsDetail());
            check(BpfNetMaps.swaps==1); // Native fixture fails; no fallback into valid proc data.
            return;
        }
        check(BpfNetMaps.created==0);
        NetworkStatsFactory factory=new NetworkStatsFactory(context,root.toFile(),false);
        check(BpfNetMaps.created==0);
        Path stats=root.resolve("net/xt_qtaguid/stats"),fmt=root.resolve("net/xt_qtaguid/iface_stat_fmt");
        StrictMode.ThreadPolicy policy=StrictMode.current;
        String first=read(root.resolve("stats-first")),second=read(root.resolve("stats-second"));
        put(stats,first);
        NetworkStats initial=factory.readNetworkStatsDetail(10001,null,0);
        check(bytes(initial)==200 && initial.size()==3);
        check(bytes(factory.readNetworkStatsDetail(10001,null,0))==200); // Cumulative, not incremental.
        put(stats,second);
        check(bytes(factory.readNetworkStatsDetail(10001,null,0))==255);
        check(bytes(factory.readNetworkStatsDetail(10001,new String[]{"wlan0"},0))==175);
        check(bytes(factory.readNetworkStatsDetail(10001,null,1))==40);
        check(bytes(factory.readNetworkStatsDetail(20002,null,0))==9);
        check(bytes(factory.readNetworkStatsDetail(99999,null,0))==0);
        NetworkStats copy=factory.readNetworkStatsDetail(10001,null,0);copy.rows.get(0).rxBytes=999999;
        check(bytes(factory.readNetworkStatsDetail(10001,null,0))==255);
        check(bytes(factory.readNetworkStatsSummaryDev())==170);
        check(bytes(factory.readNetworkStatsSummaryXt())==200);
        check(NetworkStatsFactory.kernelToTag("0xfffffffe00000000")==-2);
        check(NetworkStatsFactory.kernelToTag("0x0")==0);
        for(String bad:new String[]{second.replace("2 wlan0","4 wlan0"),
                second.replace(" 120 12 "," -1 12 "),
                second.replace(" 120 12 "," 9223372036854775808 12 "),
                "idx iface acct_tag_hex uid_tag_int cnt_set rx_bytes\n2 wlan0 0x0 10001 0 1\n"}){
            put(stats,bad);ioError(()->factory.readNetworkStatsDetail());
            check(StrictMode.current==policy);
            put(stats,second);check(bytes(factory.readNetworkStatsDetail(10001,null,0))==255);
        }
        Files.delete(stats);ioError(()->factory.readNetworkStatsDetail());check(StrictMode.current==policy);
        put(stats,second);check(bytes(factory.readNetworkStatsDetail(10001,null,0))==255);
        String oldFmt=read(fmt);Files.delete(fmt);ioError(()->factory.readNetworkStatsSummaryXt());
        check(StrictMode.current==policy);put(fmt,oldFmt);
        Files.delete(root.resolve("net/xt_qtaguid/iface_stat_all"));
        ioError(()->factory.readNetworkStatsSummaryDev());check(StrictMode.current==policy);
        check(BpfNetMaps.created==0&&BpfNetMaps.swaps==0);
    }
}
