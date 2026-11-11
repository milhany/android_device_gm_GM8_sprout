package android.net;
// Small arithmetic/collection fixture, not Android NetworkStats implementation.
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Map;
public class NetworkStats implements Cloneable {
    public static final String[] INTERFACES_ALL = null;
    public static final int UID_ALL=-1, SET_ALL=-1, TAG_ALL=-1, TAG_NONE=0;
    public static class Entry {
        public String iface; public int uid, set, tag;
        public long rxBytes, rxPackets, txBytes, txPackets;
        public Entry copy(){Entry out=new Entry();out.iface=iface;out.uid=uid;out.set=set;out.tag=tag;
            out.rxBytes=rxBytes;out.rxPackets=rxPackets;out.txBytes=txBytes;out.txPackets=txPackets;return out;}
    }
    public final ArrayList<Entry> rows = new ArrayList<>();
    private long elapsed;
    public NetworkStats(long elapsed,int capacity){this.elapsed=elapsed;}
    public long getElapsedRealtime(){return elapsed;}
    public void setElapsedRealtime(long value){elapsed=value;}
    public int size(){return rows.size();}
    public Entry getValues(int index,Entry unused){return rows.get(index).copy();}
    public void insertEntry(Entry entry){rows.add(entry.copy());}
    private static boolean same(Entry a,Entry b){return a.uid==b.uid&&a.set==b.set&&a.tag==b.tag&&a.iface.equals(b.iface);}
    private Entry find(Entry entry){for(Entry row:rows)if(same(row,entry))return row;return null;}
    public void combineAllValues(NetworkStats other){for(Entry entry:other.rows){Entry row=find(entry);
        if(row==null)insertEntry(entry);else{row.rxBytes+=entry.rxBytes;row.rxPackets+=entry.rxPackets;
        row.txBytes+=entry.txBytes;row.txPackets+=entry.txPackets;}}}
    public NetworkStats subtract(NetworkStats old){NetworkStats out=new NetworkStats(elapsed,-1);
        for(Entry entry:rows){Entry delta=entry.copy();Entry previous=old.find(entry);if(previous!=null){
        delta.rxBytes=Math.max(0,delta.rxBytes-previous.rxBytes);delta.rxPackets=Math.max(0,delta.rxPackets-previous.rxPackets);
        delta.txBytes=Math.max(0,delta.txBytes-previous.txBytes);delta.txPackets=Math.max(0,delta.txPackets-previous.txPackets);}
        out.insertEntry(delta);}return out;}
    @Override public NetworkStats clone(){NetworkStats out=new NetworkStats(elapsed,-1);
        for(Entry entry:rows)out.insertEntry(entry);return out;}
    public void filter(int uid,String[] ifaces,int tag){rows.removeIf(entry->(uid!=-1&&entry.uid!=uid)
        ||(ifaces!=null&&!Arrays.asList(ifaces).contains(entry.iface))||(tag!=-1&&entry.tag!=tag));}
    public void filterDebugEntries(){}
    public void migrateTun(int uid,String iface,String[] underlying){throw new AssertionError("VPN not modeled");}
    public void apply464xlatAdjustments(Map<String,String> ifaces){if(!ifaces.isEmpty())throw new AssertionError("CLAT not modeled");}
    public static void apply464xlatAdjustments(NetworkStats base,NetworkStats stacked,Map<String,String> ifaces){
        if(!ifaces.isEmpty())throw new AssertionError("CLAT not modeled");}
}
