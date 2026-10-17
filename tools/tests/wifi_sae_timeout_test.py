#!/usr/bin/env python3
"""Exercise Prima's actual timeout dispatch and recovery code on the host."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    args = parser.parse_args()
    base = args.kernel / "drivers/staging/prima/CORE/MAC/src/pe/lim"
    queue = (base / "limProcessMessageQueue.c").read_text()
    start = queue.index("        case SIR_LIM_MIN_CHANNEL_TIMEOUT:")
    end = queue.index("        case SIR_LIM_HEART_BEAT_TIMEOUT:", start)
    dispatch = queue[start:end]
    req = (base / "limProcessMlmReqMessages.c").read_text()
    start = req.index("static void lim_process_sae_auth_timeout(")
    handler = req[start:req.index("\n}", start) + 2]
    start = req.index("        case SIR_LIM_AUTH_SAE_TIMEOUT:")
    route = req[start:req.index("        case LIM_MLM_TSPEC_REQ:", start)]
    constants = sorted(set(re.findall(r"case (\w+):", dispatch + handler + route)))
    fixture = r'''
#include <assert.h>
#include <stddef.h>
#define LOGE 0
#define LOG1 0
#define FL(x) x
#define limLog(...) ((void)0)
#define VOS_STA_MODE 0
#define eSIR_SME_AUTH_TIMEOUT_RESULT_CODE 42
#define eSIR_MAC_UNSPEC_FAILURE_REASON 1
struct session { int peSessionId,limMlmState,limSmeState,pePersona; };
typedef struct session *tpPESession;
struct mac { struct {struct {struct {int sessionId;} sae_auth_timer;} limTimers;} lim; };
typedef struct mac *tpAniSirGlobal;
struct message {int type;};
static struct session session;
static int present=1, recovered, routed;
static tpPESession peFindSessionBySessionId(tpAniSirGlobal m,int id) {
 assert(id==7);return present ? &session : NULL;
}
static void limPrintMlmState(tpAniSirGlobal m,int level,int state) {}
static void limRestoreFromAuthState(tpAniSirGlobal m,int result,int reason,tpPESession s) {
 assert(result==eSIR_SME_AUTH_TIMEOUT_RESULT_CODE && reason==1);
 assert(s==&session);++recovered;s->limMlmState=0;
}
'''
    tests = r'''
int main(void) {
 struct mac m={.lim.limTimers.sae_auth_timer.sessionId=7};
 struct message msg={.type=SIR_LIM_AUTH_SAE_TIMEOUT};
 session.peSessionId=7;session.limMlmState=eLIM_MLM_WT_SAE_AUTH_STATE;
 dispatch(&m,&msg);
 assert(routed==1 && recovered==1 && session.limMlmState==0);
 dispatch(&m,&msg);assert(recovered==1); /* stale timeout cannot fail new state */
 session.limMlmState=eLIM_MLM_WT_SAE_AUTH_STATE;session.pePersona=1;
 dispatch(&m,&msg);assert(recovered==1); /* no station recovery for AP */
 present=0;dispatch(&m,&msg);assert(recovered==1);
 return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="gm8-sae-timeout-") as tmp:
        c = Path(tmp) / "timeout.c"
        c.write_text(fixture + "\nenum {" + ",".join(constants) + "};\n" + handler +
                     "\nstatic void limProcessMlmReqMessages(tpAniSirGlobal pMac,struct message *Msg) {"
                     "++routed;switch(Msg->type){" + route + "default:break;}}\n" +
                     "static void dispatch(tpAniSirGlobal pMac,struct message *limMsg) {"
                     "switch(limMsg->type){" + dispatch + "default:break;}}\n" + tests)
        for mbb in (False, True):
            out = Path(tmp) / ("mbb" if mbb else "no-mbb")
            subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", "-DWLAN_FEATURE_SAE",
                            *(["-DWLAN_FEATURE_LFR_MBB"] if mbb else []),
                            str(c), "-o", str(out)], check=True)
            subprocess.run([str(out)], check=True)
    print("SAE timeout: dispatch with/without MBB, station recovery and stale/AP/missing-session cases passed.")


if __name__ == "__main__":
    main()
