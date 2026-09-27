#!/usr/bin/env python3
"""Result 3 — prefill 발행 순서 x 정책.  출력: assets/sweep/result3_prefill_reclaim.json

Same replay as prefill_policy_replay.py: one prefill forward pass, then 32 decode steps,
C2 2-layer 600 mm2 tier + existing L2 as one pool, 1 MiB tiles. The metric is PHYSICAL
HBM traffic in the last decode step,

    V_HBM = V^R_HBM (reads the pool did not serve) + V^W_HBM (KV append, 1 MiB, every policy)

and the bar is 1 - V_HBM(policy) / V_HBM(base), base = no 3D, existing L2 only, no prefill.
Logical demand is the same 17.16 GB for every bar; V_HBM can never exceed it, so
1 - demand/base (= -0.77 %) is the floor of the axis: the pool filtered nothing.

Policies (the pool never reads an object type):
  admission  fill in arrival order while space is free; once full, admit nothing and evict
             nothing (no-allocate-on-miss).                 = prefill_policy_replay.Frozen
  reclaim    the same, plus: when a buffer is freed (a layer's activation once the layer is
             done) its tiles leave at once and the pool un-freezes.
  resident   oracle: the weight tiles decode will reuse are pinned before prefill.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import prefill_policy_replay as P

GB = 1e9
CAP = P.capacity('C2', 600, 2); CT = P.C0 + CAP

class FrozenFree(P.Frozen):
    def free(s, keys):
        got = sum(s.d.pop(k) for k in keys if k in s.d)
        if got: s.live -= got; s.frozen = False
        return got

def run_reclaim(trace):
    """Prefill with a free() of each layer's activation when the trace leaves that layer."""
    t = FrozenFree(CT); act = {}
    for k, n in trace:
        if k[1] == 'activation': act.setdefault(k[0], []).append(k)
    cur = None
    for k, n in trace:
        if k[0] != cur:
            if cur is not None: t.free(act.get(cur, []))
            cur = k[0]
        t.access(k, n)
    if cur is not None: t.free(act.get(cur, []))
    for step in range(P.STEPS):
        acc = sum(n for k, n in P.DEC if not t.access(k, n))
    return acc + P.W_DEC

ORDERS = [
    ('interleaved', '층 인터리빙 (기본)',     '층마다 weight → KV → activation', P.PRE),
    ('weight',      'Weight 먼저',            '32층 weight 전부 → 나머지',
     sorted(P.PRE, key=lambda t: t[0][1] not in ('layer_weight', 'lm_head'))),
    ('activation',  'Activation 먼저 (최악)', '32층 activation 전부 → 나머지',
     sorted(P.PRE, key=lambda t: t[0][1] != 'activation')),
]

if __name__ == '__main__':
    demand = sum(n for _, n in P.DEC) + P.W_DEC
    base = P.run(lambda: P.Cache(P.C0, 'LIP'), False)['last']
    pct = lambda v: 100*(1 - v/base)
    print(f'pool {CT/GB:.3f} GB (tier {CAP/GB:.3f} + L2 {P.C0/GB:.3f})')
    print(f'logical demand {demand/GB:.4f} GB   base V_HBM {base/GB:.4f} GB   '
          f'floor {pct(demand):.2f} %\n')
    print(f"{'order':<24} {'admission':>18} {'+ reclaim':>18} {'resident':>18} {'L2 only':>18}")
    out = dict(pool_GB=CT/GB, tier_GB=CAP/GB, demand_GB=demand/GB, base_GB=base/GB,
               floor_pct=pct(demand), orders=[])
    for key, label, desc, tr in ORDERS:
        P.PRE = tr
        v = dict(admission=P.run(lambda: P.Frozen(CT), True)['last'],
                 reclaim=run_reclaim(tr),
                 resident=P.run(lambda: P.Managed(CT, P.DEC), True)['last'],
                 l2_only=P.run(lambda: P.Cache(P.C0, 'LIP'), True)['last'])
        print(f'{label:<24}' + ''.join(f'{x/GB:>9.4f} {pct(x):>+7.2f}%' for x in v.values()))
        out['orders'].append(dict(key=key, label=label, desc=desc,
                                  **{p: dict(V_GB=x/GB, pct=pct(x)) for p, x in v.items()}))
    dst = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sweep', 'result3_prefill_reclaim.json')
    json.dump(out, open(dst, 'w'), indent=2, ensure_ascii=False)
    print('\nwrote assets/sweep/result3_prefill_reclaim.json')
