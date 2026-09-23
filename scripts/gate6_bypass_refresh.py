#!/usr/bin/env python3
"""Independent check of the peer session's *1 and *2, on the aperiodic ledger.

*2 first, because it invalidates *1's premise. `replay_policies.Tier` freezes bypass with

    if s.p == 'LIP-bypass' and s.live >= s.cap: s.frozen = True

but the insertion path guarantees `s.live <= s.cap` afterwards, so this fires only on exact
equality, which 1 MiB tiling against a 3,296,904,864 B capacity essentially never produces.
Reproduced: in the original run LIP and LIP-bypass agree to every printed digit (+16.581% /
+16.194%, fill 14.182 GB/step both) at every trace length. **In the aperiodic experiment
'LIP-bypass' has been plain LIP all along, and rung 3b was never actually measured there.**
The correct predicate is "the first insertion that would force an eviction freezes the tier":

    if s.p == 'LIP-bypass' and s.live + n > s.cap: s.frozen = True; return False

*1 second. With rung 3b actually implemented, the peer's fair-baseline question becomes
answerable: let bypass REFRESH (flush and refill every P steps) and see whether the admission
delta survives. It is scored on both axes, because Gate 1-C established that counting only
HBM reduction is what made demand fill look good in the first place.

Scope: synthetic aperiodic ledger (Poisson arrivals, lognormal lengths, fixed seed).
"""
import os, sys, csv
HERE = os.path.dirname(os.path.abspath(__file__))
AP   = os.path.join(HERE, '..', 'assets', 'experiments', '3dsram_aperiodic_20260921')
sys.path.insert(0, AP); sys.path.insert(0, HERE)
import replay_policies as R

GB = 1e9

class Tier(R.Tier):
    """R.Tier with the freeze predicate corrected, plus an optional refresh period."""
    def __init__(s, cap, policy, period=None, fixed_freeze=True):
        super().__init__(cap, 'LIP-bypass' if policy.startswith('bypass') else policy)
        s.period = period; s.refreshes = 0; s.fixed = fixed_freeze
        s.is_bypass = policy.startswith('bypass')
    def tick(s, i):
        if s.period and i > 0 and i % s.period == 0:
            s.d.clear(); s.live = 0; s.frozen = False; s.refreshes += 1
    def access(s, k, n, obj):
        if s.fixed and s.is_bypass and not s.frozen and k not in s.d and s.live + n > s.cap:
            s.frozen = True                      # first insertion that would evict -> freeze
        return super().access(k, n, obj)

def run(stl, wr, cap, policy, period=None, fixed_freeze=True, warm=1):
    """Warm pass then the reported pass, matching replay_policies.run: without it the one-off
    cold fill is smeared across every step and swamps the steady-state fill."""
    t = Tier(R.C0+cap, policy, period, fixed_freeze)
    for _ in range(warm+1):
        t.read = t.fill = 0; t.refreshes = 0; hbm = 0; last = 0
        for i, st in enumerate(stl):
            t.step = i; t.tick(i); h0 = hbm
            for k, b, obj in st:
                if not t.access(k, b, obj): hbm += b
            hbm += wr[i]; last = hbm-h0
    n = len(stl)
    return dict(hbm=hbm/n, hbm_ss=last, fill=t.fill/n, refreshes=t.refreshes)

if __name__ == '__main__':
    cap = R.cap_bytes('C2', 600)
    LENS = (10000, 60, 30)
    rows = []
    print(f'tier C2 600 mm2 2-layer 2-die = {cap/GB:.3f} GB (+ existing L2 {R.C0/GB:.3f} GB)')
    print('aperiodic ledger, 128 steps, warm pass. reduction vs existing-L2-LIP baseline.\n')
    for L in LENS:
        stl, wr = R.tiles(os.path.join(AP, 'inputs', f'aperiodic-b8-s128-L{L}.jsonl'))
        base = run(stl, wr, 0, 'LIP')
        mg   = run(stl, wr, cap, 'managed')
        mg_ss = 100*(1-mg['hbm_ss']/base['hbm_ss'])
        print(f'--- mean request length {L} steps ---')
        print(f"{'policy':>28} {'red avg':>9} {'red ss':>9} {'fill/step':>10} {'vs managed':>11}")
        cases = [('managed (rung 4)', 'managed', None, True),
                 ('LIP (demand fill)', 'LIP', None, True),
                 ('bypass AS SHIPPED (buggy)', 'bypass', None, False),
                 ('bypass, freeze fixed', 'bypass', None, True)]
        cases += [(f'bypass fixed, refresh P={P}', 'bypass', P, True) for P in (32, 16, 8, 4)]
        for lab, pol, P, fx in cases:
            r = run(stl, wr, cap, pol, P, fx)
            red = 100*(1-r['hbm']/base['hbm']); red_ss = 100*(1-r['hbm_ss']/base['hbm_ss'])
            rows.append(dict(mean_len=L, policy=lab, reduction_avg_pct=red, reduction_ss_pct=red_ss,
                             tier_fill_GB_step=r['fill']/GB, delta_vs_managed_ss_pp=red_ss-mg_ss))
            print(f'{lab:>28} {red:>+8.3f}% {red_ss:>+8.3f}% {r["fill"]/GB:>9.3f}G {red_ss-mg_ss:>+10.3f}p')
        print()
    with open(os.path.join(HERE, '..', 'assets', 'sweep', 'gate6_bypass_refresh.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print('wrote assets/sweep/gate6_bypass_refresh.csv')
