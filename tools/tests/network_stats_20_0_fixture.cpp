// Real GM8 kernel text writers and the patched JNI entry-point bodies are inserted by the runner.
// Kernel data structures, Android property/JNI access and BPF operations are fixtures.
#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;
static fs::path fixtureIface, fixtureUid;
static int legacyOpens = 0;
static FILE* fixtureFopen(const char* path, const char* mode) {
    assert(std::string(mode) == "re");
    if (std::string(path) == "/proc/net/xt_qtaguid/iface_stat_fmt") {
        ++legacyOpens;
        return std::fopen(fixtureIface.c_str(), mode);
    }
    if (std::string(path) == "/proc/net/xt_qtaguid/stats") {
        ++legacyOpens;
        return std::fopen(fixtureUid.c_str(), mode);
    }
    return std::fopen(path, mode);
}
#define fopen fixtureFopen
#include "LegacyTrafficStats.h"
#undef fopen

struct Stats {
    uint64_t rxBytes, rxPackets, txBytes, txPackets, tcpRxPackets, tcpTxPackets;
};
struct JNIEnv {};
using jclass = void*;
using jint = int32_t;
using jlong = int64_t;
using jstring = const char*;
struct ScopedUtfChars {
    const char* text;
    ScopedUtfChars(JNIEnv*, jstring value) : text(value) {}
    const char* c_str() const { return text; }
};
static std::string propertyMode;
static int propertyReads = 0, bpfReads = 0, bpfResult = 0;
namespace android {
namespace base {
static bool GetBoolProperty(const std::string& name, bool fallback) {
    assert(name == "ro.kernel.ebpf.supported" && fallback);
    ++propertyReads;
    return propertyMode == "default" ? fallback : propertyMode == "enabled";
}
}
static int bpfGetIfaceStats(const char*, Stats* stats) {
    ++bpfReads;
    *stats = {900, 90, 800, 80, 70, 60};
    return bpfResult;
}
static int bpfGetUidStats(uint32_t, Stats* stats) {
    return bpfGetIfaceStats(nullptr, stats);
}
// JNI_FUNCTIONS
}  // namespace android

namespace kernel_fixture {
enum { IFS_RX, IFS_TX };
enum { IFS_TCP, IFS_UDP, IFS_PROTO_OTHER };
struct byte_packet { unsigned long long bytes, packets; };
struct data_counters { byte_packet bpc[1][2][3]; };
struct iface_stat { const char* ifname; data_counters totals_via_skb; };
struct seq_file { std::string text; };
static void seq_puts(seq_file* file, const char* text) { file->text += text; }
static void seq_printf(seq_file* file, const char* format, ...) {
    char buffer[4096];
    va_list args;
    va_start(args, format);
    const int count = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    assert(count >= 0 && static_cast<size_t>(count) < sizeof(buffer));
    file->text += buffer;
}
static unsigned long long dc_sum_bytes(data_counters* counts, int set, int dir) {
    return counts->bpc[set][dir][0].bytes + counts->bpc[set][dir][1].bytes +
            counts->bpc[set][dir][2].bytes;
}
static unsigned long long dc_sum_packets(data_counters* counts, int set, int dir) {
    return counts->bpc[set][dir][0].packets + counts->bpc[set][dir][1].packets +
            counts->bpc[set][dir][2].packets;
}
// KERNEL_FUNCTIONS
static std::string sample() {
    iface_stat wlan = {"wlan0", {}}, radio = {"rmnet_data0", {}};
    wlan.totals_via_skb.bpc[0][IFS_RX][IFS_TCP] = {100, 10};
    wlan.totals_via_skb.bpc[0][IFS_RX][IFS_UDP] = {200, 20};
    wlan.totals_via_skb.bpc[0][IFS_RX][IFS_PROTO_OTHER] = {300, 30};
    wlan.totals_via_skb.bpc[0][IFS_TX][IFS_TCP] = {400, 40};
    wlan.totals_via_skb.bpc[0][IFS_TX][IFS_UDP] = {500, 50};
    wlan.totals_via_skb.bpc[0][IFS_TX][IFS_PROTO_OTHER] = {600, 60};
    radio.totals_via_skb.bpc[0][IFS_RX][IFS_TCP] = {10, 1};
    radio.totals_via_skb.bpc[0][IFS_RX][IFS_UDP] = {20, 2};
    radio.totals_via_skb.bpc[0][IFS_RX][IFS_PROTO_OTHER] = {30, 3};
    radio.totals_via_skb.bpc[0][IFS_TX][IFS_TCP] = {40, 4};
    radio.totals_via_skb.bpc[0][IFS_TX][IFS_UDP] = {50, 5};
    radio.totals_via_skb.bpc[0][IFS_TX][IFS_PROTO_OTHER] = {60, 6};
    seq_file output;
    pp_iface_stat_header(&output);
    pp_iface_stat_line(&output, &wlan);
    pp_iface_stat_line(&output, &radio);
    return output.text;
}
}  // namespace kernel_fixture

static void write(const fs::path& path, const std::string& text) {
    std::ofstream stream(path); stream << text;
    assert(stream.good());
}
static std::string uidSample() {
    return "idx iface acct_tag_hex uid_tag_int cnt_set rx_bytes rx_packets tx_bytes tx_packets\n"
           "2 wlan0 0x0 10001 0 100 1 200 2\n"
           "3 rmnet_data0 0x0 10001 1 50 3 70 4\n"
           "4 wlan0 0x100000000 10001 0 999 99 888 88\n"
           "5 wlan0 0x0 20002 0 7 8 9 10\n";
}

int main(int argc, char** argv) {
    assert(argc == 3);
    propertyMode = argv[1];
    fixtureIface = fs::path(argv[2]) / "iface";
    fixtureUid = fs::path(argv[2]) / "uid";
    fs::create_directories(argv[2]);
    using namespace android::net::legacytraffic;
    const std::string emitted = kernel_fixture::sample();
    write(fixtureIface, emitted);
    write(fixtureUid, uidSample());
    Stats stats = {};
    assert(readIfaceStats(fixtureIface.c_str(), nullptr, &stats) == 0);
    assert(stats.rxBytes == 660 && stats.txBytes == 1650 && stats.rxPackets == 66);
    assert(stats.tcpRxPackets == 11 && stats.tcpTxPackets == 44);
    assert(readIfaceStats(fixtureIface.c_str(), "wlan0", &stats) == 0);
    assert(stats.rxBytes == 600 && stats.txBytes == 1500 && stats.tcpRxPackets == 10);
    assert(readUidStats(fixtureUid.c_str(), 10001, &stats) == 0);
    assert(stats.rxBytes == 150 && stats.txBytes == 270 && stats.rxPackets == 4);
    assert(stats.tcpRxPackets == UNKNOWN && stats.tcpTxPackets == UNKNOWN);
    assert(readUidStats(fixtureUid.c_str(), 20002, &stats) == 0 && stats.rxBytes == 7);
    assert(readUidStats(fixtureUid.c_str(), 33333, &stats) == 0 && stats.rxBytes == 0);
    assert(readIfaceStats(fixtureIface.c_str(), "not-present", &stats) == 0 && stats.rxBytes == 0);

    write(fixtureIface, "iface rx_bytes rx_packets tx_bytes tx_packets\nwlan0 20 2 30 3\n");
    assert(readIfaceStats(fixtureIface.c_str(), "wlan0", &stats) == 0);
    assert(stats.rxBytes == 20 && stats.tcpRxPackets == UNKNOWN);
    write(fixtureIface, emitted + "eth0 1 2 3 4\n");
    assert(readIfaceStats(fixtureIface.c_str(), nullptr, &stats) == 0);
    assert(stats.rxBytes == 661 && stats.tcpRxPackets == UNKNOWN);
    assert(readIfaceStats(fixtureIface.c_str(), "wlan0", &stats) == 0 && stats.tcpRxPackets == 10);
    // Valid empty/absent UID counters are zero; missing/unreadable files are errors.
    write(fixtureIface, "");
    assert(readIfaceStats(fixtureIface.c_str(), nullptr, &stats) == 0 && stats.rxBytes == 0);
    assert(readIfaceStats((fixtureIface.string() + ".missing").c_str(), nullptr, &stats) == -ENOENT);
    assert(readIfaceStats(argv[2], nullptr, &stats) < 0);
    // No partial aggregate escapes on malformed/truncated, negative or overflowing input.
    for (const char* bad : {"wlan0 -1 2 3 4\n", "wlan0 1x 2 3 4\n",
                                  "wlan0 18446744073709551616 2 3 4\n", "wlan0 1 2\n"}) {
        write(fixtureIface, emitted + bad);
        stats = {777, 0, 0, 0, 0, 0};
        assert(readIfaceStats(fixtureIface.c_str(), nullptr, &stats) < 0 && stats.rxBytes == 777);
    }
    write(fixtureIface, "wlan0 18446744073709551615 1 2 3\neth0 1 1 2 3\n");
    assert(readIfaceStats(fixtureIface.c_str(), nullptr, &stats) == -EOVERFLOW);
    write(fixtureIface, std::string(4096, 'x'));
    assert(readIfaceStats(fixtureIface.c_str(), nullptr, &stats) == -EOVERFLOW);
    for (const char* bad : {"2 wlan0 0x0 -1 0 1 2 3 4\n", "2 wlan0 nope 10001 0 1 2 3 4\n",
                                  "2 wlan0 0x0 10001 0 -1 2 3 4\n"}) {
        write(fixtureUid, bad);
        stats = {777, 0, 0, 0, 0, 0};
        assert(readUidStats(fixtureUid.c_str(), 10001, &stats) < 0 && stats.rxBytes == 777);
    }

    write(fixtureIface, emitted); write(fixtureUid, uidSample());
    legacyOpens = bpfReads = 0;
    if (propertyMode == "disabled") {
        assert(android::getTotalStat(nullptr, nullptr, android::RX_BYTES) == 660);
        assert(android::getIfaceStat(nullptr, nullptr, "wlan0", android::TCP_RX_PACKETS) == 10);
        assert(android::getUidStat(nullptr, nullptr, 10001, android::RX_BYTES) == 150);
        assert(android::getUidStat(nullptr, nullptr, 10001, android::TCP_RX_PACKETS) == -1);
        assert(bpfReads == 0 && legacyOpens == 4);
        write(fixtureIface, "malformed\n");
        assert(android::getTotalStat(nullptr, nullptr, android::RX_BYTES) == -1);
        fs::remove(fixtureUid);
        assert(android::getUidStat(nullptr, nullptr, 10001, android::RX_BYTES) == -1);
    } else {
        assert(android::getTotalStat(nullptr, nullptr, android::RX_BYTES) == 900);
        assert(android::getIfaceStat(nullptr, nullptr, "wlan0", android::RX_PACKETS) == 90);
        assert(android::getUidStat(nullptr, nullptr, 10001, android::TX_BYTES) == 800);
        bpfResult = -EIO;
        assert(android::getTotalStat(nullptr, nullptr, android::RX_BYTES) == -1);
        assert(android::getIfaceStat(nullptr, nullptr, "wlan0", android::RX_BYTES) == -1);
        assert(android::getUidStat(nullptr, nullptr, 10001, android::RX_BYTES) == -1);
        assert(bpfReads == 6 && legacyOpens == 0);  // No fallback hides a BPF failure.
    }
    assert(propertyReads == 1);
    assert(android::getIfaceStat(nullptr, nullptr, nullptr, android::RX_BYTES) == -1);
    return 0;
}
