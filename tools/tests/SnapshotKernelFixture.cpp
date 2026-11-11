// Actual GM8 kernel text writers are inserted; kernel objects/seq_file are fixtures.
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

enum { IFS_RX, IFS_TX };
enum { IFS_TCP, IFS_UDP, IFS_PROTO_OTHER };
using tag_t = unsigned long long;
struct byte_packet { unsigned long long bytes = 0, packets = 0; };
struct data_counters { byte_packet bpc[2][2][3]; };
struct iface_stat { const char* ifname; data_counters totals_via_skb; };
struct tag_stat { struct { tag_t tag; } tn; data_counters counters; };
struct proc_print_info { iface_stat* iface_entry; int item_index = 1; };
struct seq_file { std::string text; proc_print_info* privateData; };
// Kernel's member is named private, a C++ keyword.
#define private privateData
static void seq_puts(seq_file* out, const char* text) { out->text += text; }
static int seq_printf(seq_file* out, const char* format, ...) {
    char buf[4096]; va_list args; va_start(args, format);
    int size = vsnprintf(buf, sizeof(buf), format, args); va_end(args);
    assert(size >= 0 && static_cast<size_t>(size) < sizeof(buf));
    out->text += buf; return size;
}
static unsigned long long dc_sum_bytes(data_counters* c, int set, int dir) {
    return c->bpc[set][dir][0].bytes + c->bpc[set][dir][1].bytes + c->bpc[set][dir][2].bytes;
}
static unsigned long long dc_sum_packets(data_counters* c, int set, int dir) {
    return c->bpc[set][dir][0].packets + c->bpc[set][dir][1].packets + c->bpc[set][dir][2].packets;
}
static unsigned get_uid_from_tag(tag_t tag) { return tag & 0xffffffff; }
static tag_t get_atag_from_tag(tag_t tag) { return tag & 0xffffffff00000000ULL; }
static int init_user_ns;
static unsigned make_kuid(int*, unsigned uid) { return uid; }
static bool can_read_other_uid_stats(unsigned) { return true; }
#define CT_DEBUG(...) do {} while (0)
// ACTUAL_KERNEL_WRITERS
#undef private
static void put(const std::filesystem::path& file, const std::string& data) {
    std::ofstream stream(file); stream << data; assert(stream.good());
}
static std::string detail(bool second) {
    iface_stat wlan{"wlan0", {}}, radio{"rmnet_data0", {}};
    proc_print_info info{&wlan, 1}; seq_file out{"", &info}; pp_stats_header(&out);
    auto row = [&](unsigned uid, unsigned tag, int set, unsigned long long rx, unsigned long long tx) {
        tag_stat entry{{(static_cast<tag_t>(tag) << 32) | uid}, {}};
        entry.counters.bpc[set][IFS_RX][IFS_TCP] = {rx, rx / 10};
        entry.counters.bpc[set][IFS_TX][IFS_UDP] = {tx, tx / 10};
        assert(pp_stats_line(&out, &entry, set) > 0);
    };
    row(10001, 0, 0, second ? 120 : 100, second ? 230 : 200);
    row(10001, 0, 1, second ? 55 : 40, second ? 95 : 80);
    row(10001, 1, 0, second ? 40 : 30, second ? 60 : 50);
    row(20002, 0, 0, second ? 9 : 7, second ? 11 : 9);
    info.iface_entry = &radio;
    row(10001, 0, 0, second ? 80 : 60, second ? 90 : 70);
    return out.text;
}
int main(int argc, char** argv) {
    assert(argc == 2); std::filesystem::path root(argv[1]);
    put(root / "stats-first", detail(false)); put(root / "stats-second", detail(true));
    iface_stat wlan{"wlan0", {}}, radio{"rmnet_data0", {}};
    wlan.totals_via_skb.bpc[0][IFS_RX][IFS_TCP] = {120, 12};
    wlan.totals_via_skb.bpc[0][IFS_TX][IFS_UDP] = {230, 23};
    radio.totals_via_skb.bpc[0][IFS_RX][IFS_TCP] = {80, 8};
    radio.totals_via_skb.bpc[0][IFS_TX][IFS_UDP] = {90, 9};
    seq_file out{"", nullptr}; pp_iface_stat_header(&out);
    pp_iface_stat_line(&out, &wlan); pp_iface_stat_line(&out, &radio);
    put(root / "iface-fmt", out.text);
}
