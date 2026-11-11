// Includes the actual patched controller and extracted Binder method bodies.
// Android services and iptables are fixtures; no real rules or packets are sent.
#include <algorithm>
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace android::base {
static std::string propertyMode;
inline bool GetBoolProperty(const std::string& name, bool fallback) {
    assert(name == "ro.kernel.ebpf.supported" && fallback);
    return propertyMode == "default" ? fallback : propertyMode != "legacy";
}
inline std::string StringPrintf(const char* format, ...) {
    char buffer[8192]; va_list args; va_start(args, format);
    const int n = vsnprintf(buffer, sizeof(buffer), format, args); va_end(args);
    assert(n >= 0 && static_cast<size_t>(n) < sizeof(buffer)); return buffer;
}
inline void StringAppendF(std::string* text, const char* format, ...) {
    char buffer[8192]; va_list args; va_start(args, format);
    const int n = vsnprintf(buffer, sizeof(buffer), format, args); va_end(args);
    assert(n >= 0 && static_cast<size_t>(n) < sizeof(buffer)); *text += buffer;
}
inline std::string Join(const std::vector<std::string>& values, const std::string& separator) {
    std::string result;
    for (const auto& value : values) { if (!result.empty()) result += separator; result += value; }
    return result;
}
inline std::string Join(const std::vector<std::string>& values, char separator) {
    return Join(values, std::string(1, separator));
}
}

#include "server/NetdConstants.h"
using Words = std::vector<std::string>;
using Rules = std::map<std::string, std::vector<Words>>;
struct Write { bool ipv6; std::string command; };
static Rules kernel[2];
static std::vector<Write> writes;
static std::set<size_t> failCalls;
static Words words(const std::string& text) {
    std::istringstream in(text); Words result; std::string word;
    while (in >> word) result.push_back(word);
    return result;
}
static int restore(bool ipv6, const std::string& command) {
    writes.push_back({ipv6, command});
    if (failCalls.count(writes.size())) return 1;
    Rules candidate = kernel[ipv6];
    std::istringstream input(command); std::string line; bool commit = false;
    while (std::getline(input, line)) {
        Words row = words(line);
        if (row.empty() || row[0][0] == '*') continue;
        if (row[0] == "COMMIT") { commit = true; continue; }
        if (row[0] == "-6") { if (!ipv6) continue; row.erase(row.begin()); }
        if (row[0][0] == ':') { candidate[row[0].substr(1)].clear(); continue; }
        assert(row.size() >= 4);
        const std::string operation = row[0], chain = row[1];
        row.erase(row.begin(), row.begin() + 2);
        size_t position = 0;
        if (operation == "-I" && row[0][0] >= '0' && row[0][0] <= '9') {
            position = std::stoul(row[0]) - 1; row.erase(row.begin());
        }
        auto& rules = candidate[chain];
        if (operation == "-A") rules.push_back(row);
        else if (operation == "-I") {
            assert(position <= rules.size()); rules.insert(rules.begin() + position, row);
        } else if (operation == "-D") {
            const auto found = std::find(rules.begin(), rules.end(), row);
            if (found == rules.end()) return 1;
            rules.erase(found);
        } else assert(false);
    }
    assert(commit); kernel[ipv6] = std::move(candidate); return 0;
}
int execIptablesRestore(IptablesTarget family, const std::string& command) {
    if (family == V4) return restore(false, command);
    if (family == V6) return restore(true, command);
    const int four = restore(false, command), six = restore(true, command);
    return four | six;
}
bool isIfaceName(const std::string& iface) {
    return !iface.empty() && iface.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_") == std::string::npos;
}


static bool legacyMode() { return !android::base::GetBoolProperty("ro.kernel.ebpf.supported", true); }
namespace android::net {
struct FirewallController {
    static bool isLegacyMode() { return legacyMode(); }
    static std::string makeCriticalCommands(IptablesTarget target, const char* chain) {
        std::string result;
        if (target == V6) for (const char* type : {"packet-too-big", "router-solicitation", "router-advertisement",
                "neighbour-solicitation", "neighbour-advertisement", "redirect"}) {
            result += "-A " + std::string(chain) + " -p icmpv6 --icmpv6-type " + type + " -j RETURN\n";
        }
        return result;
    }
};
}
using android::net::FirewallController;
using android::base::Join;
using android::base::StringPrintf;
using android::base::StringAppendF;
static constexpr unsigned uidBillingMask = 0x100000, CLAT_MARK = 0xdead;
#define IPSEC_IFACE_PREFIX "ipsec"
#define XT_BPF_DENYLIST_PROG_PATH "PIN_DENY"
#define XT_BPF_ALLOWLIST_PROG_PATH "PIN_ALLOW"
#define XT_BPF_INGRESS_PROG_PATH "PIN_INGRESS"
#define XT_BPF_EGRESS_PROG_PATH "PIN_EGRESS"
static const std::string COMMIT_AND_CLOSE = "COMMIT\n";
// ACCOUNTING_FUNCTIONS
#include "server/BandwidthController.h"
static int restoreOutput(IptablesTarget family, const std::string& command, std::string*) {
    return execIptablesRestore(family, command);
}
int (*BandwidthController::iptablesRestoreFunction)(IptablesTarget, const std::string&, std::string*) = restoreOutput;
// BANDWIDTH_FUNCTIONS
void BandwidthController::flushCleanTables(bool) {
    execIptablesRestore(V4V6, "*filter\n:bw_INPUT -\n:bw_OUTPUT -\n:bw_costly_shared -\n:bw_penalty_box -\n:bw_happy_box -\n:bw_data_saver -\nCOMMIT\n");
}
const char* BandwidthController::jumpToString(IptJumpOp op) {
    return op == IptJumpReject ? " -j REJECT" : " -j RETURN";
}
struct Packet { int64_t uid; std::string proto = "tcp"; bool rst = false; std::string icmp = ""; };
enum Verdict { RETURN, DROP };
static Verdict evaluate(bool ipv6, const std::string& chain, const Packet& packet, unsigned depth = 0) {
    assert(depth < 16);
    for (const auto& row : kernel[ipv6].at(chain)) {
        bool match = true, invert = false; std::string target;
        for (size_t i = 0; i < row.size(); ++i) {
            if (row[i] == "!") { invert = true; continue; }
            if (row[i] == "-m") { assert(row[++i] == "owner"); continue; }
            if (row[i] == "--uid-owner") {
                const std::string range = row[++i]; const size_t dash = range.find('-');
                const int64_t low = std::stoll(range.substr(0, dash));
                const int64_t high = dash == std::string::npos ? low : std::stoll(range.substr(dash + 1));
                const bool owns = packet.uid >= low && packet.uid <= high;
                match &= invert ? !owns : owns; invert = false;
            } else if (row[i] == "-p") match &= packet.proto == row[++i];
            else if (row[i] == "--tcp-flags") { assert(row[i + 1] == "RST" && row[i + 2] == "RST"); i += 2; match &= packet.rst; }
            else if (row[i] == "--icmpv6-type") match &= packet.icmp == row[++i];
            else if (row[i] == "-j") { target = row[++i]; break; }
            else assert(false); // The policy test must not silently ignore an unknown matcher.
        }
        if (!match) continue;
        if (target == "RETURN") return RETURN;
        if (target == "DROP" || target == "REJECT") return DROP;
        if (evaluate(ipv6, target, packet, depth + 1) == DROP) return DROP;
    }
    return RETURN;
}


namespace android::binder {
struct Status {
    int error=0;
    static constexpr int EX_UNSUPPORTED_OPERATION=-999;
    static Status fromExceptionCode(int error) { return {error}; }
    static Status ok() { return {}; }
};
}
namespace android::net {
struct Controllers { BandwidthController bandwidthCtrl; };
static Controllers* gCtls;
static bool permission=true;
static constexpr int PERM_NETWORK_STACK=11, PERM_MAINLINE_NETWORK_STACK=12;
static binder::Status statusFromErrcode(int error) { return {error}; }
#define NETD_LOCKING_RPC(lock, a, b) std::lock_guard<std::mutex> guard(lock); assert(a==PERM_NETWORK_STACK && b==PERM_MAINLINE_NETWORK_STACK); if (!permission) return statusFromErrcode(-EPERM)
struct NetdNativeService {
    binder::Status bandwidthAddNaughtyApp(int32_t);
    binder::Status bandwidthRemoveNaughtyApp(int32_t);
    binder::Status bandwidthAddNiceApp(int32_t);
    binder::Status bandwidthRemoveNiceApp(int32_t);
    binder::Status bandwidthEnableDataSaver(bool, bool*);
};
// BANDWIDTH_RPC
}
int main(int argc, char** argv) {
    assert(argc==2); android::base::propertyMode=argv[1];
    using namespace android::net;
    assert(getBasicAccountingCommands(true)==getOriginalAccountingCommands());
    const auto legacy=getBasicAccountingCommands(false);
    assert(std::count(legacy.begin(),legacy.end(),"-A bw_INPUT -m owner --socket-exists")==1);
    assert(std::count(legacy.begin(),legacy.end(),"-A bw_OUTPUT -m owner --socket-exists")==1);
    assert(std::count(legacy.begin(),legacy.end(),"-A bw_raw_PREROUTING -m owner --socket-exists")==1);
    assert(std::count(legacy.begin(),legacy.end(),"-A bw_mangle_POSTROUTING -m owner --socket-exists")==1);
    for (const auto& line:legacy) assert(line.find("--object-pinned")==std::string::npos);
    Controllers controllers; gCtls=&controllers; auto& bw=controllers.bandwidthCtrl;
    NetdNativeService rpc; bool enabled=false;
    if (!legacyMode()) {
        assert(bw.enableBandwidthControl()==0);
        assert(rpc.bandwidthAddNiceApp(10001).error==android::binder::Status::EX_UNSUPPORTED_OPERATION);
        return 0;
    }
    assert(rpc.bandwidthAddNiceApp(10001).error==-ENODEV);
    assert(bw.enableBandwidthControl()==0);
    assert(rpc.bandwidthEnableDataSaver(true,&enabled).error==0 && enabled);
    for(bool v6:{false,true}) {
        assert(evaluate(v6,"bw_penalty_box",{20002})==DROP);
        assert(evaluate(v6,"bw_penalty_box",{1000})==RETURN);
    }
    assert(rpc.bandwidthAddNiceApp(10001).error==0);
    assert(evaluate(false,"bw_penalty_box",{10001})==RETURN);
    assert(rpc.bandwidthAddNaughtyApp(10001).error==0);
    assert(evaluate(false,"bw_penalty_box",{10001})==DROP);
    assert(rpc.bandwidthRemoveNaughtyApp(10001).error==0);
    assert(evaluate(false,"bw_penalty_box",{10001})==RETURN);
    assert(rpc.bandwidthRemoveNiceApp(10001).error==0);
    assert(evaluate(false,"bw_penalty_box",{10001})==DROP);
    const size_t count=writes.size();
    assert(rpc.bandwidthRemoveNiceApp(10001).error==0 && writes.size()==count);
    assert(rpc.bandwidthAddNiceApp(-1).error==-EINVAL && writes.size()==count);
    permission=false;
    assert(rpc.bandwidthAddNaughtyApp(20002).error==-EPERM);
    assert(rpc.bandwidthEnableDataSaver(false,&enabled).error==-EPERM);
    assert(writes.size()==count); permission=true;
    assert(evaluate(true,"bw_penalty_box",{20002,"icmpv6",false,"neighbour-solicitation"})==RETURN);
    failCalls={writes.size()+2};
    assert(rpc.bandwidthAddNiceApp(20002).error==-EREMOTEIO);
    assert(evaluate(false,"bw_penalty_box",{20002})==DROP);
    assert(evaluate(true,"bw_penalty_box",{20002})==DROP);
    failCalls.clear();
    assert(rpc.bandwidthAddNiceApp(20002).error==0);
    failCalls={writes.size()+2};
    assert(rpc.bandwidthEnableDataSaver(false,&enabled).error==0 && !enabled);
    assert(evaluate(false,"bw_penalty_box",{30003})==DROP);
    assert(evaluate(true,"bw_penalty_box",{30003})==DROP);
    failCalls.clear();
    assert(rpc.bandwidthEnableDataSaver(false,&enabled).error==0 && enabled);
    assert(evaluate(false,"bw_penalty_box",{30003})==RETURN);
    failCalls={writes.size()+2,writes.size()+3};
    assert(rpc.bandwidthAddNaughtyApp(30003).error==-EREMOTEIO);
    const size_t failed=writes.size();
    assert(rpc.bandwidthAddNiceApp(10001).error==-ENODEV && writes.size()==failed);
    failCalls.clear(); assert(bw.enableBandwidthControl()==0);
    assert(rpc.bandwidthAddNiceApp(10001).error==0);
    assert(bw.setupIptablesHooks()==0);
    assert(rpc.bandwidthAddNiceApp(10001).error==-ENODEV);
    assert(bw.enableBandwidthControl()==0);
    assert(bw.disableBandwidthControl()==0);
    assert(rpc.bandwidthAddNiceApp(10001).error==-ENODEV);
    return 0;
}
