#!/usr/bin/env python3
"""AutoScratch-style L2 residency semantics (Fu et al., MLSys 2023, NVIDIA) as a predictor of DRAM bytes per step.

AutoScratch is the closest prior work that models NVIDIA's L2 residency controls: its simulation infrastructure
(an NVArchSim-like trace simulator feeding a functional Python L2 model, reported within 3 % geomean of L4
silicon for DRAM-traffic reduction) is not public. What the paper states about the semantics, and all this
implements:
  * data marked L2-resident "cannot be evicted from the cache by hardware" (pinned);
  * the resident capacity is capped by the set-aside ("maximum L2-resident capacity of 36MB", a constraint);
  * everything else is "subject to the default hardware cache replacement mechanism" — LRU here;
  * residency is a per-address yes/no choice; there is no hitRatio and no streaming (missProp) class.
Mapping our settings onto those semantics: the lines a window selects with probability hitRatio (the same
per-address hash our other models use) are the resident ones; they are pinned first-come until the set-aside is
full, and any further ones are ordinary lines; missProp=Streaming lines are ordinary lines. No fitted parameter.

Usage: python3 scripts/prior/autoscratch_pin.py   (self-test on two cyclic cases)
"""
import os, sys
from collections import OrderedDict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import l2policy_model as V1

MiB = 1 << 20

class PinL2:
    """C blocks; up to S pinned blocks that nothing evicts; ordinary blocks LRU in the remaining C - |pinned|."""
    def __init__(s, C, S):
        s.C, s.S = C, S
        s.pin, s.N = set(), OrderedDict()                  # N: first = LRU end
    def access(s, key, resident):
        if key in s.pin: return True
        hit = key in s.N
        if resident and len(s.pin) < s.S:                  # becomes resident (fetched once if it was not in L2)
            if hit: del s.N[key]
            s.pin.add(key)
            while len(s.N) > s.C - len(s.pin): s.N.popitem(last=False)
            return hit
        if hit: s.N.move_to_end(key); return True
        s.N[key] = 1
        while len(s.N) > s.C - len(s.pin): s.N.popitem(last=False)
        return False

def simulate(run, C_bytes, g=64 * 1024, warm=6, meas=4):
    """Mean DRAM (miss) bytes per steady-state step, same workloads and selection hash as l2policy_model."""
    steps, nwin, _, _ = V1.workload(run, g)
    L2 = PinL2(int(C_bytes // g), int(run['setaside'] * MiB // g))
    r, miss = run['hitratio'], 0
    for k in range(warm + meas):
        m = 0
        for key in steps(k):
            res = (key >> 32) == 0 and (key & 0xFFFFFFFF) < nwin and V1.u01(key) < r
            if not L2.access(key, res): m += 1
        if k >= warm: miss += m
    return miss / meas * g

if __name__ == '__main__':
    C = 96 * MiB
    # ws 192 MiB cyclic, window 127, S 60, r 1: 60 MiB pinned, 132 MiB cycles through 36 MiB of LRU -> 132 MiB miss
    print(simulate(dict(mode='llm', ws=192, layers=32, window=127, setaside=60, hitratio=1.0), C) / MiB)
    # same with S 0: nothing can be resident -> plain LRU thrash -> 192 MiB
    print(simulate(dict(mode='llm', ws=192, layers=32, window=127, setaside=0, hitratio=1.0), C) / MiB)
