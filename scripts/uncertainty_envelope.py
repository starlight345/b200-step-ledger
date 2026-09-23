#!/usr/bin/env python3
"""Does the verdict survive every unmeasured property being wrong at once?

The honest weakness of this work is that the stack cross-section and its material
properties are literature-anchored, not characterised by us. The sensitivity study answers
"which one matters"; it does not answer "what if they are all bad together". This does.

No invented distributions. Each axis is taken at the two ends of the range already
declared in thermal_sensitivity.py, and every combination is evaluated -- 2^5 corners.
The temperature budget is held FIXED across corners, because it is a physical allowance
(what the tier may rise by), not something that should be re-derived per geometry. Only
theta = peak rise per burst watt moves, and the delivered bandwidth follows.

The question is whether the worst corner still clears the 6.40 TB/s HBM floor, since
below that floor the tier cannot pay for itself no matter what the thermal answer is.
"""
import os, sys, csv, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_sensitivity as S
import ectc_thermal_model as M

E_BIT = 0.5      # pJ/bit, the device model's own conservative example -- same as headline
AXES = [
    ('a-IGZO k [W/m/K]',      'igzo_k',    1.4,   2.6,   'third-party measured'),
    ('BEOL effective k',      'beol_k',    1.0,   5.0,   'estimate, swept'),
    ('inter-tier ILD [um]',   't_ild_um',  0.15,  1.00,  'third-party 0.30'),
    ('BEOL above tier [um]',  't_beol_um', 4.0,   16.0,  'estimate, swept'),
    ('Si substrate [um]',     't_si_um',   200.0, 775.0, 'scenario'),
]

if __name__ == '__main__':
    base_pf, base_th, base_Rth = S.variant()
    S.DT_BUDGET = base_Rth * 20.0            # same pinning the sensitivity study uses
    base_cap = S.cap_from_theta(base_th, e=E_BIT)
    print(f'nominal stack: theta = {base_th:.5f} K/W  ->  cap = {base_cap:.2f} TB/s')
    print(f'temperature budget held fixed at {S.DT_BUDGET:.3f} K '
          f'(= nominal R_th x 20 W)\n')
    print('axes, each at both ends of its declared range:')
    for name, _, lo, hi, prov in AXES:
        print(f'  {name:<24} {lo:>7g} .. {hi:<7g}  [{prov}]')
    print(f'\nevaluating {2**len(AXES)} corners at E/bit = {E_BIT} pJ/bit ...\n')

    rows = []
    for combo in itertools.product(*[(a[2], a[3]) for a in AXES]):
        kw = {a[1]: v for a, v in zip(AXES, combo)}
        pf, th, Rth = S.variant(**kw)
        cap = S.cap_from_theta(th, e=E_BIT)
        rows.append(dict(**{a[1]: v for a, v in zip(AXES, combo)},
                         theta_K_W=round(th, 6), cap_TBs=round(cap, 3),
                         clears_hbm_floor=cap >= M.BW_HBM))
    rows.sort(key=lambda r: r['cap_TBs'])
    worst, best = rows[0], rows[-1]
    print(f"{'cap [TB/s]':>11} {'theta':>9}   corner")
    for r in rows[:3] + [None] + rows[-2:]:
        if r is None: print(f"{'...':>11}"); continue
        c = ', '.join(f"{a[1]}={r[a[1]]:g}" for a in AXES)
        print(f"{r['cap_TBs']:>11.2f} {r['theta_K_W']:>9.5f}   {c}")

    n_ok = sum(r['clears_hbm_floor'] for r in rows)
    print(f'\n  worst corner: {worst["cap_TBs"]:.2f} TB/s   best corner: {best["cap_TBs"]:.2f} TB/s')
    print(f'  spread {best["cap_TBs"]/worst["cap_TBs"]:.2f}x about a nominal of {base_cap:.2f}')
    print(f'  HBM floor {M.BW_HBM:.2f} TB/s cleared in {n_ok}/{len(rows)} corners')
    if n_ok == len(rows):
        print(f'\n  Every corner clears the floor. The verdict "this tier is admissible" does')
        print(f'  not depend on any of the five unmeasured quantities: taking all five at')
        print(f'  their worst simultaneously still leaves {worst["cap_TBs"]/M.BW_HBM:.2f}x margin.')
        print(f'  What the properties DO decide is how much headroom there is, not whether')
        print(f'  there is any -- which is why the paper reports a bracket, not a point.')
    else:
        bad = [r for r in rows if not r['clears_hbm_floor']]
        print(f'\n  {len(bad)} corners fail. The binding one is:')
        print('   ', ', '.join(f"{a[1]}={bad[0][a[1]]:g}" for a in AXES))
        print(f'  So the verdict IS property-dependent and the paper must say so.')

    out = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sweep', 'uncertainty_corners.csv')
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f'\nwrote {os.path.relpath(out)}')
