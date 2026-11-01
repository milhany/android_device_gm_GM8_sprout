#!/usr/bin/env python3
"""Compile/run the actual Java route policy. Use javac or pass an Eclipse ECJ jar."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ecj', type=Path)
args = parser.parse_args()
source = Path(__file__).resolve().parents[2] / 'dolby/src/org/lineageos/gm8/dolby/DolbyRoutePolicy.java'
with tempfile.TemporaryDirectory() as name:
    root = Path(name)
    java = root / 'RouteTest.java'
    java.write_text('''package org.lineageos.gm8.dolby;
public class RouteTest {
    public static void main(String[] args) {
        int[] routes = {0, 1, 2, 3, 4, 8, 0x80, 0x4000, 0x4001};
        for (int mode : new int[]{-2,-1,0,1,2,3}) {
            for (int route : routes) {
                boolean actual = DolbyRoutePolicy.allowsDap(mode, route);
                if (mode != 0 || route == 0 || route == 1 || route == 3 || route == 0x4001) {
                    if (actual) throw new AssertionError("Unsafe route enabled DAP");
                } else if (!actual) throw new AssertionError("Media route blocked");
            }
        }
        // Speaker -> receiver/VoIP -> speaker restores eligibility, not a saved preference.
        if (!DolbyRoutePolicy.allowsDap(0,2) || DolbyRoutePolicy.allowsDap(3,1)
                || !DolbyRoutePolicy.allowsDap(0,2)) throw new AssertionError();
        System.out.println("PASS: actual Java route policy: media, receiver, mixed, call/VoIP and unknown routes");
    }
}''')
    compiler = (['java', '-jar', str(args.ecj), '-8', '-proc:none'] if args.ecj else
                [shutil.which('javac') or 'javac', '-source', '8', '-target', '8'])
    subprocess.run(compiler + ['-d', str(root), str(source), str(java)], check=True)
    subprocess.run(['java', '-cp', str(root), 'org.lineageos.gm8.dolby.RouteTest'], check=True)
