#!/usr/bin/env python3
"""M1 + M3 — CUDA-policy-faithful L2 abstraction, and the H1 predictions written BEFORE measuring.

What NVIDIA documents, and all this models (not the undocumented replacement FSM or associativity):
  * a set-aside S of L2 (cudaLimitPersistingL2CacheSize) is used preferentially by persisting lines;
    while persisting lines do not fill it, normal and streaming lines may use the unused part;
  * an access-policy window gives ~hitRatio of its lines hitProp=Persisting ("hitRatio 0.5 on a 32 KB
    window -> the hardware selects, at random, 16 KB"), the rest missProp=Streaming;
  * persisting lines are not pinned: when more of them compete than S holds, they evict each other;
  * streaming lines are preferentially evicted.
Where NVIDIA is silent we choose, and H1 tests the choice: LRU inside each class, per-address (not
per-access) selection by a uniform hash, streaming inserted at the LRU end and not promoted on a hit,
write-allocate on every miss (every DRAM read passes through L2), block granularity g.

Four predictors of DRAM bytes per step (M3), each a different logical -> physical conversion:
  no_residency   V = step bytes                              (no cross-step reuse; LLMCompass-like)
  capacity_only  V = step bytes - min(C, recurring bytes)    (stored = useful; MemExplorer-like)
  fixed_lru      one LRU L2 of capacity C, policy knobs ignored (GPU-Tile-Sim-like)
  cuda_policy    this model, streaming = LRU among streaming lines
  cuda_policy_lip  same, streaming = LIP-like insertion (the undocumented choice H1 decides)

Usage:  python3 l2policy_model.py predict --calib assets/sweep/h1_calib_ampere.json
"""
import argparse, json, os, sys, time
from collections import OrderedDict

MiB = 1 << 20
M64 = (1 << 64) - 1

def u01(key):
    """Deterministic uniform in [0, 1) per block (splitmix64): which lines a window selects is fixed
    per address, as in NVIDIA's example, not re-drawn on every access."""
    x = (key + 0x9E3779B97F4A7C15) & M64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & M64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & M64
    return (x ^ (x >> 31)) / 2.0**64

class CudaL2:
    """C blocks in total, S of them set aside. Persisting lines live in P (at most S); normal (Nn) and
    streaming (Ns) lines share whatever P leaves free (|P| + |Nn| + |Ns| <= C). When room is needed,
    streaming lines go first, then normal; nothing else evicts a persisting line.

    stream_mode is the one choice NVIDIA does not document and H1 decides:
      'evict_first'    the oldest streaming line leaves first (LRU among streaming lines)
      'insert_lru_end' a new streaming line enters at the eviction end (LIP-like: early ones stay)"""
    def __init__(s, C, S, stream_mode='evict_first'):
        s.C, s.S, s.mode = C, S, stream_mode
        s.P, s.Nn, s.Ns = OrderedDict(), OrderedDict(), OrderedDict()   # first = LRU end
    def _room(s):
        while len(s.P) + len(s.Nn) + len(s.Ns) > s.C:
            (s.Ns if s.Ns else s.Nn).popitem(last=False)
    def access(s, key, prop):
        if prop == 'persist' and s.S > 0:
            if key in s.P: s.P.move_to_end(key); return True
            if len(s.P) >= s.S: s.P.popitem(last=False)          # persisting evicts persisting (thrash)
            s.P[key] = 1; s._room(); return False                  # takes back borrowed set-aside
        if prop == 'stream':
            if key in s.Ns: s.Ns.move_to_end(key); return True
            s.Ns[key] = 1
            if s.mode == 'insert_lru_end': s.Ns.move_to_end(key, last=False)
            s._room(); return False
        if key in s.Nn: s.Nn.move_to_end(key); return True
        s.Nn[key] = 1; s._room(); return False

# ------------------------------------------------------------------ workloads (mirror l2policy_bench.cu)
def workload(run, g):
    """Per-step block sequences. Keys: (buffer << 32) | block. Returns steps(k) -> list, window blocks,
    recurring bytes, kernel launches per step."""
    if run['mode'] == 'llm':
        nb = int(run['ws'] * MiB // g)
        seq = [b for b in range(nb)]
        return (lambda k: seq), int(min(run['window'], run['ws']) * MiB // g), run['ws'] * MiB, run['layers']
    nh, nc = int(run['hot'] * MiB // g), int(run['chunk'] * MiB // g)
    slots = max(1, int(run['pool'] // run['chunk']))
    hot = [b for b in range(nh)]
    def steps(k):
        base = (k % slots) * nc
        return hot + [(1 << 32) | (base + i) for i in range(nc)]
    return steps, int(min(run['window'], run['hot']) * MiB // g), run['hot'] * MiB, 2

def simulate(run, C_bytes, g, knobs=True, warm=6, meas=4, stream_mode='evict_first'):
    """Mean DRAM (miss) bytes per steady-state step. knobs=False ignores set-aside/window (fixed LRU)."""
    steps, nwin, _, _ = workload(run, g)
    S = int(run['setaside'] * MiB // g) if knobs else 0
    L2 = CudaL2(int(C_bytes // g), S, stream_mode)
    r = run['hitratio']
    miss = 0
    for k in range(warm + meas):
        m = 0
        for key in steps(k):
            if knobs and (key >> 32) == 0 and (key & 0xFFFFFFFF) < nwin:
                prop = 'persist' if u01(key) < r else 'stream'
            else:
                prop = 'normal'
            if not L2.access(key, prop): m += 1
        if k >= warm: miss += m
    return miss / meas * g

def predict(run, C_bytes, cal, g=64 * 1024):
    steps, _, recurring, launches = workload(run, g)
    step_bytes = len(steps(0)) * g
    V = {'no_residency': step_bytes,
         'capacity_only': step_bytes - min(C_bytes, recurring),
         'fixed_lru': simulate(run, C_bytes, g, knobs=False),
         'cuda_policy': simulate(run, C_bytes, g, knobs=True),
         'cuda_policy_lip': simulate(run, C_bytes, g, knobs=True, stream_mode='insert_lru_end')}
    t = {}
    for k, v in V.items():
        fixed = launches * cal['t_launch_ms']
        dram_ms = v / cal['B_dram_Bps'] * 1e3
        l2_ms = step_bytes / cal['B_l2_Bps'] * 1e3
        t[k] = {'overlap_ms': fixed + max(dram_ms, l2_ms),
                'serial_ms': fixed + dram_ms + (step_bytes - v) / cal['B_l2_Bps'] * 1e3}
    return {'step_bytes': step_bytes, 'dram_bytes': V, 'time': t}

def near(sa, W):
    """Two extra points bracketing the predicted thrash onset hitRatio = S/W."""
    if sa <= 0 or W <= 0: return []
    x = sa / W
    return [round(f * x, 4) for f in (0.9, 1.1) if 0 < f * x < 1]

def grid(C_mib, S_max_mib, W_max_mib):
    """H1 grid for one machine, derived from its probed constants (nothing hard-coded)."""
    sas = [round(S_max_mib * f, 2) for f in (0, 0.2, 0.4, 0.6, 0.8, 1.0)]
    hrs = [0.0, 0.25, 0.5, 0.75, 1.0]
    runs = []
    for ws in (0.5 * C_mib, 1.0 * C_mib, 2.0 * C_mib, 4.0 * C_mib):
        runs.append(dict(mode='llm', ws=ws, layers=32, window=0, setaside=0, hitratio=0))
        for sa in sas:
            W = min(ws, W_max_mib)
            for hr in hrs + near(sa, W):
                runs.append(dict(mode='llm', ws=ws, layers=32, window=W, setaside=sa, hitratio=hr))
    for hot in (0.5 * C_mib, 1.0 * C_mib, min(W_max_mib, 4 / 3 * C_mib)):
        runs.append(dict(mode='clean', hot=hot, chunk=C_mib, pool=2048, window=0, setaside=0, hitratio=0))
        for sa in sas:
            for hr in hrs + near(sa, hot):
                runs.append(dict(mode='clean', hot=hot, chunk=C_mib, pool=2048, window=hot, setaside=sa, hitratio=hr))
    return runs

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['predict'])
    ap.add_argument('--probe', default='assets/sweep/gpu_probe_ampere.json')
    ap.add_argument('--calib', required=True)
    ap.add_argument('--out', default='assets/sweep/h1_predictions_ampere.json')
    a = ap.parse_args()
    pr = json.load(open(a.probe)); cal = json.load(open(a.calib))
    C = int(pr['gpu.l2_cache_bytes']); Smax = int(pr['gpu.persisting_l2_max_bytes'])
    Wmax = int(pr['gpu.access_policy_max_window_bytes'])
    runs = grid(C / MiB, Smax / MiB, Wmax / MiB)
    t0 = time.time(); out = []
    for run in runs:
        out.append(dict(run=run, **predict(run, C, cal)))
    doc = dict(created=time.strftime('%Y-%m-%d %H:%M:%S %Z'), machine=pr.get('host'), l2_bytes=C,
               persist_max=Smax, window_max=Wmax, calib=cal, granularity_bytes=64 * 1024,
               note='Written before H1 measurements. Do not edit after the sweep runs.', runs=out)
    json.dump(doc, open(a.out, 'w'), indent=1)
    print(f'{len(out)} runs predicted in {time.time() - t0:.1f}s -> {a.out}')
