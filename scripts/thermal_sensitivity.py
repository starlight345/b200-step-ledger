#!/usr/bin/env python3
"""Sensitivity ranking and mitigation study -- the two things the ECTC template has and we did not.

Calibration against ECTC practice. The closest structural precedent is the ECTC 2020 thermal
study of a face-to-face bonded 3D microprocessor: one headline claim carried by a number pair
(worst-case rise 6 C for logic-over-memory versus 12 C for naive stacking), tile-based power
maps from two workload vectors, boundary conditions calibrated to a fabricated test chip, and
-- importantly -- a mitigation section. It also models configurations that were never built,
which is precedent for a design study. Two elements of that template were missing here:

  (a) SENSITIVITY. The Thermal/Mechanical subcommittee solicits "sensitivity & statistical
      analysis" in as many words. We had sweeps but no ranking, so we could not say which
      unmeasured quantity actually deserves a measurement.
  (b) MITIGATION. Their paper ends with what to do about it. Ours ended at the diagnosis.

Everything below runs on the verified 1D solver (analytic x2, MAPDL 1D 0.02%, MAPDL 3D 1.3%).
"""
import os, sys, math, csv
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import thermal_stack_solver as T
import ectc_thermal_model as M

ROOT = os.path.join(os.path.dirname(__file__), '..')
Q_TIER = 38.0
DUTY   = M.duty(M.capacity_GB(800.0, 2))

def variant(n_tiers=2, igzo_k=None, beol_k=None, t_ild_um=0.30, t_beol_um=8.0,
            t_si_um=500.0):
    """Returns (peak_frac, peak_K_per_burst_watt) for a stack variant.

    peak_frac alone is NOT comparable across geometries: changing the stack changes R_th
    too, and a fixed WATT budget silently assumes a fixed R_th. The physical constraint is
    a temperature budget, so the transferable quantity is the periodic peak rise per burst
    watt, theta = peak / P_burst [K/W]. Delivered bandwidth then follows from
        BW <= dT_budget / (8 * E_bit * theta).
    Restores MAT afterwards."""
    save = dict(T.MAT)
    try:
        if igzo_k is not None:
            k, rho, cp = T.MAT['SRAM_tier']; T.MAT['SRAM_tier'] = (igzo_k, rho, cp)
        if beol_k is not None:
            k, rho, cp = T.MAT['BEOL']; T.MAT['BEOL'] = (beol_k, rho, cp)
        lay = T.build_stack(n_tiers=n_tiers, t_ild_um=t_ild_um, t_beol_um=t_beol_um,
                            t_si_um=t_si_um)
        pf, pk, tr, R = T.periodic_peak_frac(lay, T.DIE_AREA_M2, Q_TIER)
        return pf, pk/Q_TIER, R/Q_TIER   # theta [K/burst-W], R_th [K/W] steady
    finally:
        T.MAT.clear(); T.MAT.update(save)

DT_BUDGET = None        # set from the baseline so the baseline reproduces 18.6 TB/s

def cap_from_theta(theta, e=0.5, dT=None):
    """BW [TB/s] allowed by a temperature budget: dT = theta * P_burst = theta*8*E*BW."""
    return (dT if dT is not None else DT_BUDGET)/(8.0*e*theta)

if __name__ == '__main__':
    base_pf, base_th, base_Rth = variant()
    # The temperature budget is what a 20 W CONTINUOUS load would have produced under the
    # device model's own steady-state reading: dT_max = R_th * P_budget. Pinning it to the
    # steady R_th (not to theta) is what makes the baseline reproduce the verified
    # 18.57 TB/s while still letting geometry changes move R_th and theta independently.
    globals()['DT_BUDGET'] = base_Rth*20.0
    base_cap = cap_from_theta(base_th)
    print(f'baseline: peak_frac {base_pf:.4f}, R_th {base_Rth*1e3:.3f} mK/W, '
          f'theta {base_th*1e3:.3f} mK/W')
    print(f'  dT budget = R_th x 20 W = {DT_BUDGET:.4f} K  ->  cap {base_cap:.2f} TB/s @0.5 pJ/bit')
    print(f'  (steady-state reading of the same 20 W would be {M.bw_cap_TBs(20,0.5,1.0):.2f} TB/s)\n')

    print('=== (a) sensitivity: which UNMEASURED quantity moves the answer? ===')
    print('    each swept across its full literature / plausible range, others at nominal\n')
    print(f"{'parameter':>34} {'low':>9} {'high':>9} | {'cap low':>9} {'cap high':>9} {'swing':>8}")
    rows = []
    cases = [
        ('a-IGZO k [W/m/K]',        'third-party measured', 1.4, 2.6, lambda v: variant(igzo_k=v)[1]),
        ('BEOL effective k [W/m/K]','estimate, swept',      1.0, 5.0, lambda v: variant(beol_k=v)[1]),
        ('inter-tier ILD [um]',     'third-party 0.30',     0.15, 1.00, lambda v: variant(t_ild_um=v)[1]),
        ('BEOL above tier [um]',    'estimate, swept',      4.0, 16.0, lambda v: variant(t_beol_um=v)[1]),
        ('Si substrate [um]',       'scenario',             200.0, 775.0, lambda v: variant(t_si_um=v)[1]),
        ('tier count',              'design axis',          1, 8,      lambda v: variant(n_tiers=int(v))[1]),
    ]
    for name, grade, lo, hi, fn in cases:
        c_lo, c_hi = cap_from_theta(fn(lo)), cap_from_theta(fn(hi))
        swing = abs(c_hi-c_lo)/base_cap
        rows.append(dict(parameter=name, grade=grade, low=lo, high=hi,
                         cap_low_TBs=c_lo, cap_high_TBs=c_hi, swing_frac=swing))
        print(f'{name:>34} {lo:>9.2f} {hi:>9.2f} | {c_lo:>9.2f} {c_hi:>9.2f} {swing*100:>7.1f}%')
    # E/bit enters the cap linearly and is not a stack parameter; report it for comparison
    import ebit_budget as B
    e_lo, e_hi = B.budget(0)['total'], B.budget(1)['total']
    c_lo, c_hi = cap_from_theta(base_th, e=e_hi), cap_from_theta(base_th, e=e_lo)
    rows.append(dict(parameter='E/bit [pJ/bit]', grade='third-party + swept', low=e_lo, high=e_hi,
                     cap_low_TBs=c_lo, cap_high_TBs=c_hi, swing_frac=abs(c_hi-c_lo)/base_cap))
    print(f'{"E/bit [pJ/bit]":>34} {e_lo:>9.3f} {e_hi:>9.3f} | {c_lo:>9.2f} {c_hi:>9.2f} '
          f'{abs(c_hi-c_lo)/base_cap*100:>7.1f}%')
    rows.sort(key=lambda r: -r['swing_frac'])
    print(f'\n  ranked: ' + ' > '.join(r['parameter'].split(' [')[0] for r in rows))
    print(f'  -> the measurement worth asking for is the top one, not the one that feels most uncertain.')

    print('\n=== (b) mitigation: what buys thermal margin back? ===')
    print('    all at 4 tiers, where the stack starts to cost something\n')
    base4_th = variant(n_tiers=4)[1]
    print(f"{'change':>44} {'peak_frac':>10} {'theta mK/W':>11} {'cap [TB/s]':>11} {'vs base':>8}")
    mits = [
        ('baseline, 4 tiers', dict(n_tiers=4)),
        ('thinner inter-tier ILD, 300 -> 150 nm', dict(n_tiers=4, t_ild_um=0.15)),
        ('higher-k ILD (2.5 -> 5.0 W/m/K)', dict(n_tiers=4, beol_k=5.0)),
        ('tier closer to Si: BEOL 8 -> 4 um', dict(n_tiers=4, t_beol_um=4.0)),
        ('thinned substrate 500 -> 200 um', dict(n_tiers=4, t_si_um=200.0)),
        ('higher-k ILD + BEOL 4 um combined', dict(n_tiers=4, beol_k=5.0, t_beol_um=4.0)),
    ]
    out2 = []
    for name, kw in mits:
        pf, th, _ = variant(**kw); c = cap_from_theta(th)
        out2.append(dict(change=name, peak_frac=pf, theta_mK_W=th*1e3, cap_TBs=c,
                         vs_base=c/cap_from_theta(base4_th)))
        print(f'{name:>44} {pf:>10.4f} {th*1e3:>11.4f} {c:>11.2f} '
              f'{c/cap_from_theta(base4_th):>7.2f}x')
    with open(os.path.join(ROOT, 'assets', 'sweep', 'thermal_sensitivity.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(os.path.join(ROOT, 'assets', 'sweep', 'thermal_mitigation.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out2[0])); w.writeheader(); w.writerows(out2)
    print('\nwrote assets/sweep/thermal_sensitivity.csv, thermal_mitigation.csv')
