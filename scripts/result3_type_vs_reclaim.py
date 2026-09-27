#!/usr/bin/env python3
"""Result 3, the fair version: does the tier need RECLAIM, or is TYPE-AWARE ADMISSION enough?

Critique of the first Result 3: the 'activation first' order cannot happen (a layer's
activation needs that layer's weight first), and a managed tier would simply never admit
activation, so nothing has to be reclaimed. This replays the same prefill -> 32 decode steps
(C2 2-layer 600 mm2 pool, 1 MiB tiles, physical V_HBM of the last decode step) with the
nominal layer-interleaved order FIXED, and adds the missing policy:

  blind        first-fill then freeze, any object may enter        (= Admission only)
  blind+free   the same + activation freed when its layer is done  (= Admission + reclaim)
  no-act       first-fill then freeze, activation never admitted   (type-aware admission)
  weight-only  first-fill then freeze, only weight / LM head       (type-aware admission)
  managed      decode's weight tiles pinned before prefill          (oracle)

The two synthetic orders are kept only as a sensitivity check: they say whether a policy's
value depends on the (unmeasured) kernel issue order.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import prefill_policy_replay as P
from result3_prefill_reclaim import FrozenFree, run_reclaim, ORDERS, CT

class Typed(P.Frozen):
    def __init__(s, cap, allow): super().__init__(cap); s.allow = allow
    def access(s, k, n):
        if k in s.d: return True
        return P.Frozen.access(s, k, n) if k[1] in s.allow else False

NO_ACT = {'layer_weight', 'full_kv', 'lm_head', 'embedding_gather'}
WEIGHT = {'layer_weight', 'lm_head'}
POLICIES = [('blind',       lambda tr: P.run(lambda: P.Frozen(CT), True)['last']),
            ('blind+free',  run_reclaim),
            ('no-act',      lambda tr: P.run(lambda: Typed(CT, NO_ACT), True)['last']),
            ('weight-only', lambda tr: P.run(lambda: Typed(CT, WEIGHT), True)['last']),
            ('managed',     lambda tr: P.run(lambda: P.Managed(CT, P.DEC), True)['last'])]

if __name__ == '__main__':
    base = P.run(lambda: P.Cache(P.C0, 'LIP'), False)['last']
    pct = lambda v: 100*(1 - v/base)
    print(f"{'order':<24}" + ''.join(f'{p:>13}' for p, _ in POLICIES))
    out = dict(base_GB=base/1e9, orders=[])
    for key, label, desc, tr in ORDERS:
        P.PRE = tr
        row = {p: pct(f(tr)) for p, f in POLICIES}
        print(f'{label:<24}' + ''.join(f'{v:>12.2f}%' for v in row.values()))
        out['orders'].append(dict(key=key, label=label, **row))
    dst = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sweep', 'result3_type_vs_reclaim.json')
    json.dump(out, open(dst, 'w'), indent=2, ensure_ascii=False)
    print('\nwrote assets/sweep/result3_type_vs_reclaim.json')
