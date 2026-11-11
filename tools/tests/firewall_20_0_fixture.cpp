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
        if (row.empty() || row[0] == "*filter") continue;
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

#include "server/FirewallController.cpp"

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
    int error = 0;
    static constexpr int EX_UNSUPPORTED_OPERATION = -999;
    static Status fromExceptionCode(int error) { return {error}; }
};
}
namespace android::net {
struct Controllers { FirewallController firewallCtrl; };
static Controllers* gCtls;
static bool permission = true;
static constexpr int PERM_NETWORK_STACK = 11, PERM_MAINLINE_NETWORK_STACK = 12;
static binder::Status statusFromErrcode(int error) { return {error}; }
#define NETD_LOCKING_RPC(lock, first, second) \
    std::lock_guard<std::mutex> guard(lock); \
    assert(first == PERM_NETWORK_STACK && second == PERM_MAINLINE_NETWORK_STACK); \
    if (!permission) return statusFromErrcode(-EPERM)
struct NetdNativeService {
    binder::Status firewallSetUidRule(int32_t, int32_t, int32_t);
    binder::Status firewallEnableChildChain(int32_t, bool);
    binder::Status firewallReplaceUidChain(const std::string&, bool, const std::vector<int32_t>&, bool*);
};
// RPC_FUNCTIONS
}

int main(int argc, char** argv) {
    assert(argc == 2); android::base::propertyMode = argv[1];
    using namespace android::net;
    Controllers controllers; gCtls = &controllers; auto& fw = controllers.firewallCtrl;
    NetdNativeService rpc;
    assert(fw.setupIptablesHooks() == 0);
    if (android::base::propertyMode != "legacy") {
        assert(writes.size() == 2);
        assert(writes[0].command.find("fw_gm8") == std::string::npos);
        assert(fw.setUidRule(1, 10001, 1) == -EOPNOTSUPP);
        assert(rpc.firewallSetUidRule(1, 10001, 1).error == android::binder::Status::EX_UNSUPPORTED_OPERATION);
        assert(writes.size() == 2);
        assert(fw.setFirewallType(ALLOWLIST) == 0);
        assert(fw.setInterfaceRule("wlan0", ALLOW) == 0);
        assert(writes.back().command.find("-I fw_INPUT -i wlan0 -j RETURN") != std::string::npos);
        assert(writes.back().command.find("fw_gm8") == std::string::npos);
        return 0;
    }
    for (bool ipv6 : {false, true}) {
        assert(kernel[ipv6]["fw_INPUT"][0] == words("-j fw_gm8_INPUT"));
        assert(kernel[ipv6]["fw_OUTPUT"][0] == words("-j fw_gm8_OUTPUT"));
    }
    bool replaced = false;
    assert(rpc.firewallEnableChildChain(1, true).error == 0);
    assert(rpc.firewallSetUidRule(1, 10001, 1).error == 0);
    for (bool ipv6 : {false, true}) {
        assert(evaluate(ipv6, "fw_gm8_INPUT", {10001}) == RETURN);
        assert(evaluate(ipv6, "fw_gm8_OUTPUT", {20002}) == DROP);
        assert(evaluate(ipv6, "fw_gm8_INPUT", {9999}) == RETURN);
        assert(evaluate(ipv6, "fw_gm8_INPUT", {-1}) == RETURN);
        assert(evaluate(ipv6, "fw_gm8_INPUT", {20002, "esp"}) == RETURN);
        assert(evaluate(ipv6, "fw_gm8_INPUT", {20002, "tcp", true}) == RETURN);
    }
    assert(evaluate(true, "fw_gm8_INPUT", {20002, "icmpv6", false, "neighbour-solicitation"}) == RETURN);
    assert(rpc.firewallEnableChildChain(2, true).error == 0);
    assert(rpc.firewallSetUidRule(2, 10001, 2).error == 0);
    assert(evaluate(false, "fw_gm8_OUTPUT", {10001}) == DROP);
    assert(rpc.firewallEnableChildChain(2, false).error == 0);
    assert(evaluate(false, "fw_gm8_OUTPUT", {10001}) == RETURN);
    failCalls = {writes.size() + 2};
    assert(rpc.firewallEnableChildChain(2, true).error == -EREMOTEIO);
    assert(evaluate(false, "fw_gm8_OUTPUT", {10001}) == RETURN);
    assert(evaluate(true, "fw_gm8_OUTPUT", {10001}) == RETURN);
    failCalls.clear();
    for (const auto& chain : LegacyUidFirewall::CHAINS) {
        assert(rpc.firewallReplaceUidChain(chain.name, chain.allowlist, {10001, 10001}, &replaced).error == 0 && replaced);
        assert(evaluate(false, chain.name, {10001}) == (chain.allowlist ? RETURN : DROP));
        assert(evaluate(true, chain.name, {20002}) == (chain.allowlist ? DROP : RETURN));
    }
    const size_t beforeInvalid = writes.size();
    assert(rpc.firewallSetUidRule(1, -1, 1).error == -EINVAL);
    assert(rpc.firewallSetUidRule(1, 10001, 88).error == -EINVAL);
    assert(rpc.firewallEnableChildChain(6, true).error == -EOPNOTSUPP);
    assert(rpc.firewallSetUidRule(0, 10001, 1).error == -EOPNOTSUPP);
    assert(rpc.firewallEnableChildChain(99, true).error == -EINVAL);
    assert(rpc.firewallReplaceUidChain("fw_dozable\nCOMMIT", true, {}, &replaced).error == -EINVAL && !replaced);
    assert(rpc.firewallReplaceUidChain("fw_dozable", false, {}, &replaced).error == -EINVAL);
    assert(writes.size() == beforeInvalid);
    permission = false;
    assert(rpc.firewallSetUidRule(1, 20002, 1).error == -EPERM);
    assert(rpc.firewallEnableChildChain(1, false).error == -EPERM);
    assert(rpc.firewallReplaceUidChain("fw_dozable", true, {}, &replaced).error == -EPERM);
    assert(writes.size() == beforeInvalid); permission = true;

    // Failure in family two restores both families and keeps the prior UID set.
    failCalls = {writes.size() + 2};
    assert(rpc.firewallReplaceUidChain("fw_dozable", true, {20002}, &replaced).error == -EREMOTEIO && !replaced);
    assert(evaluate(false, "fw_dozable", {10001}) == RETURN);
    assert(evaluate(true, "fw_dozable", {10001}) == RETURN);
    assert(evaluate(false, "fw_dozable", {20002}) == DROP);
    failCalls.clear();
    failCalls = {writes.size() + 1};
    assert(rpc.firewallSetUidRule(1, 20002, 1).error == -EREMOTEIO);
    assert(evaluate(false, "fw_dozable", {20002}) == DROP);
    failCalls.clear();
    assert(rpc.firewallSetUidRule(1, 20002, 1).error == 0);
    // Parent resets and global interface allow rules must retain the UID anchor first.
    assert(fw.resetFirewall() == 0);
    assert(fw.setInterfaceRule("wlan0", ALLOW) == 0);
    assert(kernel[0]["fw_INPUT"][0] == words("-j fw_gm8_INPUT"));
    assert(kernel[0]["fw_INPUT"][1] == words("-i wlan0 -j RETURN"));
    for (const auto& write : writes) {
        assert(write.command.find("--socket-exists") == std::string::npos);
    }
    // A failed rollback invalidates cached state; no later API can report a no-op success.
    failCalls = {writes.size() + 2, writes.size() + 3};
    assert(rpc.firewallReplaceUidChain("fw_dozable", true, {}, &replaced).error == -EREMOTEIO);
    const size_t failed = writes.size();
    assert(rpc.firewallSetUidRule(1, 10001, 1).error == -ENODEV);
    assert(rpc.firewallEnableChildChain(1, true).error == -ENODEV);
    assert(writes.size() == failed);
    failCalls.clear(); assert(fw.setupIptablesHooks() == 0);
    assert(rpc.firewallSetUidRule(1, 10001, 1).error == 0);
    assert(fw.setFirewallType(DENYLIST) == 0);
    failCalls = {writes.size() + 1};
    assert(fw.setFirewallType(ALLOWLIST) == -EREMOTEIO);
    assert(rpc.firewallSetUidRule(1, 10001, 1).error == -ENODEV);
    failCalls.clear(); assert(fw.setupIptablesHooks() == 0);
    failCalls = {writes.size() + 3}; // after base flush, initialization fails before anchors attach
    assert(fw.setupIptablesHooks() == -EREMOTEIO);
    assert(rpc.firewallEnableChildChain(1, true).error == -ENODEV);
    return 0;
}
