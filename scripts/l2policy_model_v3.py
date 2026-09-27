#!/usr/bin/env python3
"""Model v3 — v2 plus the eviction priority that the load INSTRUCTIONS carry (v2 in l2policy_model_v2.py is frozen).

Why (2026-09-27, after R1): cuBLAS's gemvx kernel reads LLM weights with LDG.E.EF (ld.global.cs, evict-first in
L1 and L2), and on the real decode the persisting benefit did not depend on the set-aside. v2 had no notion of
per-instruction priority, so every non-window line was 'normal' and competed with persisting lines.

One new class, nothing new fitted (phi and the 16-way structure are v2's):
  E  recurring lines loaded with an evict-first hint (ld.global.cs, L2::evict_first) outside the window.
     They are handled like the window's streaming lines: evicted first, never displacing normal or persisting
     lines, hitting only in the room those leave.
  Window lines keep the access-policy window's properties whatever the instruction says (hitRatio -> persisting,
  the rest -> streaming), as R1 showed (savings track the persisting bytes although the weights are EF).
  L  evict-last hints: v3 has no rule for them and treats them as normal (C3 hint 2 is therefore exploratory).
Workload classes per step (MiB): W window, N recurring normal, E recurring evict-first, F fresh (never reused).

Usage: import predict_v3(classes_dict, setaside_mib, hitratio, C_bytes, phi)
"""
import numpy as np
from l2policy_model_v2 import _counts, A_WAYS

MiB = 1 << 20

def predict_v3(cls, setaside, hitratio, C_bytes, phi, A=A_WAYS, n_sets=20000, seed=1):
    """cls = dict(W=, N=, E=, F=) in MiB per step. Returns DRAM read bytes per steady-state step."""
    rng = np.random.default_rng(seed)
    way = C_bytes / A
    W, N, E, F = (cls.get(k, 0.0) for k in 'WNEF')
    w = _counts(W * MiB / way, phi, n_sets, rng)
    n = _counts(N * MiB / way, phi, n_sets, rng)
    e = _counts(E * MiB / way, phi, n_sets, rng)
    f = _counts(F * MiB / way, phi, n_sets, rng)
    r = hitratio if W > 0 else 0.0
    p = rng.binomial(w, r)                            # persisting-marked window lines
    s = w - p                                         # streaming-marked window lines
    k = int(round(setaside * MiB / way)) if W > 0 else 0
    reserved_fit = (p <= k) & (k > 0)
    cap = np.where(reserved_fit, A - p, A)            # ways left for the normal pool
    extra = np.where(reserved_fit, 0, p)              # persisting lines that must compete as normal
    pool = n + extra + f
    fits = pool <= cap
    hits = np.where(reserved_fit, p, 0) + np.where(fits, n + extra, 0)
    room = np.where(fits, cap - pool, 0)
    # evict-first lines (window streaming + instruction-hinted E) share the leftover room; cyclic, so a set's
    # evict-first lines hit only if all of them fit (all or nothing, as v2 does for streaming)
    ef = s + e
    hits = hits + np.where(ef <= room, ef, 0)
    step = W + N + E + F
    return step * MiB - hits.mean() * way

def synth_classes(run, hint):
    """Synthetic l2policy_bench workloads; hint 1/3 = evict-first on every load (window lines keep the window's
    properties), hint 0/2 = normal (v3 has no evict-last rule)."""
    if run['mode'] == 'llm':
        W = min(run['window'], run['ws']); rest = run['ws'] - W; fresh = 0.0
    else:
        W = min(run['window'], run['hot']); rest = run['hot'] - W; fresh = run['chunk']
    if hint in (1, 3): return dict(W=W, N=0.0, E=rest, F=fresh)
    return dict(W=W, N=rest, E=0.0, F=fresh)
