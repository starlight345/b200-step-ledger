#!/usr/bin/env python3
"""Model v2 — set-level CUDA-policy L2, built from what H1 showed (v1 in l2policy_model.py is frozen).

Structure (inferred, not fitted):
  * L2 is A-way set-associative, A = 16. Evidence: the device's persisting maximum is exactly 10/16 of L2
    on this GPU (60 of 96 MiB) and on B200 (79.06 of 126.5 MiB), and every set-aside we swept is a whole
    number of C/A = 6 MiB "ways". A set-aside S therefore reserves k = S / (C/A) ways in every set.
  * hitRatio selects each window line independently with probability r (NVIDIA: "random with a
    probability of approximately hitRatio"), so a set's persisting count is Binomial(window lines, r).
  * In a set: persisting lines keep up to k reserved ways and are only displaced by persisting lines.
    Reserved ways they do not use serve normal/streaming lines. If more than k persisting lines map to
    the set they cannot all stay reserved and compete with normal lines for all A ways — so when the
    whole working set fits in L2 everything still hits (llm ws=48), otherwise they thrash.
  * Recurring normal lines hit only if everything that passes through the set between two uses
    (recurring normal + fresh lines) fits in its ways (LRU on a cyclic stream: all or nothing per set).
  * Streaming lines are evicted first: they never displace normal lines, and hit only in leftover room.
Fitted (one number): phi, how unevenly addresses spread over sets. Each class's per-set line count has
variance phi * mean (0 = perfectly even, 1 = Poisson). Fitted on H1, validated on unseen sizes (H1c).
"""
import json, sys
import numpy as np

MiB = 1 << 20
A_WAYS = 16

def _counts(mean, phi, n, rng):
    """Per-set line counts with mean `mean` and variance phi*mean."""
    if mean <= 0: return np.zeros(n, dtype=np.int64)
    if phi <= 0:
        base = np.floor(mean)
        return (base + (rng.random(n) < mean - base)).astype(np.int64)
    if phi >= 1: return rng.poisson(mean, n)
    trials = max(int(np.ceil(mean)), int(round(mean / (1 - phi))))
    return rng.binomial(trials, mean / trials, n)

def classes(run):
    """Bytes per step: window (recurring, policy-marked), recurring normal, fresh (never reused)."""
    if run['mode'] == 'llm':
        W = min(run['window'], run['ws']); return W, run['ws'] - W, 0.0, run['ws']
    W = min(run['window'], run['hot']); return W, run['hot'] - W, run['chunk'], run['hot'] + run['chunk']

def predict_v2(run, C_bytes, phi, A=A_WAYS, n_sets=20000, seed=1):
    rng = np.random.default_rng(seed)
    way = C_bytes / A                                  # bytes held by one way across all sets
    W, N, F, step = classes(run)
    w = _counts(W * MiB / way, phi, n_sets, rng)
    n = _counts(N * MiB / way, phi, n_sets, rng)
    f = _counts(F * MiB / way, phi, n_sets, rng)
    r = run['hitratio'] if W > 0 else 0.0
    p = rng.binomial(w, r)                            # persisting-marked window lines in each set
    s = w - p                                         # streaming-marked (missProp) window lines
    k = int(round(run['setaside'] * MiB / way)) if W > 0 else 0
    if W <= 0:                                        # no window: everything is normal
        p = np.zeros_like(w); s = np.zeros_like(w); k = 0
    reserved_fit = (p <= k) & (k > 0)
    cap = np.where(reserved_fit, A - p, A)            # ways left for the normal pool
    extra = np.where(reserved_fit, 0, p)              # persisting lines that must compete as normal
    pool = n + extra + f
    fits = pool <= cap
    hits = np.where(reserved_fit, p, 0) + np.where(fits, n + extra, 0)
    room = np.where(fits, cap - pool, 0)
    hits = hits + np.where(s <= room, s, 0)
    hit_bytes = hits.mean() * way
    return step * MiB - hit_bytes

if __name__ == '__main__':
    pass
