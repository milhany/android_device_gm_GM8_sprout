#!/usr/bin/env python3
"""Host-test the real kernel external-auth and PMKSA handlers with netlink fixtures."""
import argparse
from pathlib import Path
import subprocess
import tempfile


def extract(source, name):
    start = source.index("static int " + name + "(")
    return source[start:source.index("\n}", start) + 2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    args = parser.parse_args()
    source = (args.kernel / "net/wireless/nl80211.c").read_text()
    header = args.kernel.resolve() / "include/uapi/linux/nl80211.h"
    fixture = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
#define ETH_ALEN 6
#define IEEE80211_MAX_SSID_LEN 32
#define WARN_ON(x) assert(!(x))
_Static_assert(NL80211_CMD_EXTERNAL_AUTH == 127, "command ABI");
_Static_assert(NL80211_ATTR_PMK == 254, "PMK ABI");
_Static_assert(NL80211_ATTR_EXTERNAL_AUTH_ACTION == 260, "action ABI");
_Static_assert(NL80211_ATTR_EXTERNAL_AUTH_SUPPORT == 261, "support ABI");
struct nlattr { size_t len; void *data; };
static void *nla_data(struct nlattr *a){return a->data;}
static size_t nla_len(struct nlattr *a){return a->len;}
static u16 nla_get_u16(struct nlattr *a){return *(u16 *)a->data;}
struct sk_buff {int unused;};
struct cfg80211_external_auth_params { int action; u8 bssid[6];
 struct {u8 ssid[32];size_t ssid_len;} ssid;unsigned int key_mgmt_suite;u16 status;};
struct cfg80211_pmksa {const u8 *bssid,*pmkid,*pmk;size_t pmk_len;};
struct wireless_dev {u32 conn_owner_nlportid;int iftype;};
struct wiphy {int unused;};
struct net_device {struct wireless_dev *ieee80211_ptr;};
struct cfg80211_ops {
 int (*external_auth)(struct wiphy*,struct net_device*,struct cfg80211_external_auth_params*);
 int (*set_pmksa)(struct wiphy*,struct net_device*,struct cfg80211_pmksa*);
 int (*del_pmksa)(struct wiphy*,struct net_device*,struct cfg80211_pmksa*);};
struct cfg80211_registered_device {struct cfg80211_ops *ops;struct wiphy wiphy;};
struct genlmsghdr {int cmd;};
struct genl_info {void *user_ptr[2];struct nlattr *attrs[NL80211_ATTR_MAX+1];
 u32 snd_portid;struct genlmsghdr *genlhdr;};
static int calls;static u16 auth_status;static size_t key_length;
static int auth_cb(struct wiphy*w,struct net_device*d,struct cfg80211_external_auth_params*p){
 ++calls;auth_status=p->status;assert(p->ssid.ssid_len==4);return 7;}
static int pmk_cb(struct wiphy*w,struct net_device*d,struct cfg80211_pmksa*p){
 key_length=p->pmk_len;if(key_length)assert(p->pmk[0]==0x5a);return 9;}
'''
    tests = r'''
int main(void){
 struct cfg80211_ops ops={};struct cfg80211_registered_device r={.ops=&ops};
 struct wireless_dev w={.conn_owner_nlportid=42,.iftype=NL80211_IFTYPE_STATION};
 struct net_device d={.ieee80211_ptr=&w};struct genlmsghdr h={NL80211_CMD_SET_PMKSA};
 struct genl_info i={.user_ptr={&r,&d},.snd_portid=42,.genlhdr=&h};
 u8 ssid[33]="test",bssid[6]={2,3,4,5,6,7},id[16]={},key[64]={0x5a};u16 status=0;
 struct nlattr ss={4,ssid},bs={6,bssid},st={2,&status},pmkid={16,id},pmk={32,key};
 assert(nl80211_external_auth(0,&i)==-EOPNOTSUPP);ops.external_auth=auth_cb;
 assert(nl80211_external_auth(0,&i)==-EINVAL);
 i.attrs[NL80211_ATTR_SSID]=&ss;i.attrs[NL80211_ATTR_BSSID]=&bs;i.attrs[NL80211_ATTR_STATUS_CODE]=&st;
 i.snd_portid=43;assert(nl80211_external_auth(0,&i)==-EPERM);i.snd_portid=42;
 w.conn_owner_nlportid=0;assert(nl80211_external_auth(0,&i)==-EPERM);w.conn_owner_nlportid=42;
 ss.len=33;assert(nl80211_external_auth(0,&i)==-EINVAL);
 ss.len=0;assert(nl80211_external_auth(0,&i)==-EINVAL);ss.len=4;
 bs.len=5;assert(nl80211_external_auth(0,&i)==-EINVAL);bs.len=6;assert(calls==0);
 assert(nl80211_external_auth(0,&i)==7 && calls==1 && auth_status==0);
 status=1;assert(nl80211_external_auth(0,&i)==7 && auth_status==1);
 ops.set_pmksa=pmk_cb;i.attrs[NL80211_ATTR_MAC]=&bs;i.attrs[NL80211_ATTR_PMKID]=&pmkid;
 assert(nl80211_setdel_pmksa(0,&i)==9 && key_length==0);
 i.attrs[NL80211_ATTR_PMK]=&pmk;assert(nl80211_setdel_pmksa(0,&i)==9 && key_length==32);
 pmk.len=48;assert(nl80211_setdel_pmksa(0,&i)==9 && key_length==48);
 pmk.len=0;assert(nl80211_setdel_pmksa(0,&i)==-EINVAL);
 pmk.len=31;assert(nl80211_setdel_pmksa(0,&i)==-EINVAL);
 pmk.len=64;assert(nl80211_setdel_pmksa(0,&i)==-EINVAL);
 return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="gm8-wpa3-") as tmp:
        c = Path(tmp) / "handlers.c"
        c.write_text(f'#include "{header}"\n' + fixture +
                     extract(source, "nl80211_external_auth") + "\n" +
                     extract(source, "nl80211_setdel_pmksa") + "\n" + tests)
        out = Path(tmp) / "handlers"
        subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", str(c), "-o", str(out)], check=True)
        subprocess.run([str(out)], check=True)
    print("External-auth/PMKSA: ownership, callback, bounds, failure status and PMK transfer passed.")


if __name__ == "__main__":
    main()
