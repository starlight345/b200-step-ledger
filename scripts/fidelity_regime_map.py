#!/usr/bin/env python3
"""Which thermal model is good enough, as a function of the package and the workload?

temporal_spatial_ablation showed that each abstraction's error depends on three things the
screening engineer controls or knows: the cooling (R_ext/R_stack: what sits above the TIM against
the die stack's own resistance), where in the macro the read power goes (the periphery share
phi), and how the tier's reads are laid out in the step (the schedule). This maps those axes
into regimes: the cheapest model whose allowable E/bit at 19 TB/s is within TOL of the
macro-resolved exact answer.

  1D, time-averaged       static-average map on a tier-uniform stack (one steady 1D solve)
  1D, transient           the exact schedule on a tier-uniform stack (1D Zth / modal, seconds)
  macro-resolved transient the reference

Two further rungs are reported but not used for the regime: the macro-resolved static average
(spatial but no time) and the macro-resolved 1 ms trace (spatial, coarse time).

Every model uses the same allowance as temporal_spatial_ablation: dT_lim = 10 W/die x R_uniform.
The allowable E/bit at 19 TB/s is E_crit = 10 W / (76 W/pJ x peak fraction), where 76 W/pJ is the
per-die burst power per pJ/bit at 19 TB/s.

  python3 scripts/fidelity_regime_map.py         # sweep -> assets/sweep/fidelity_regime_map.json
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import temporal_spatial_ablation as TA

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets', 'sweep', 'fidelity_regime_map.json')
RATIOS = (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.8, 8.0)
PHIS = tuple(np.round(np.linspace(TA.MM.PERI_AREA_FRAC, 0.9, 25), 4))
SCHEDULES = ('S0 one block', 'S1 on the measured kernel trace', 'S2 interleaved over 32 layers', 'S4 page slice')
W_PER_PJ = TA.p_burst(1.0)                    # 76 W per die per pJ/bit at 19 TB/s
TOL = 0.10

def e_crit(pf):
    return TA.BUDGET_W_DIE/(W_PER_PJ*pf)

def main():
    t0 = time.time()
    sch = TA.schedules()
    c0 = TA.Cell(0.0, nm=(0, 0), pts=[(0.0, 0.0)])          # the (0,0) mode is the 1D stack
    R_stack = TA.steady_max(TA.Mod(c0.lam, c0.uniform(1.0)))
    res = dict(ratios=RATIOS, phis=PHIS, schedules=SCHEDULES, R_stack_K_per_W=R_stack, tol=TOL,
               allowance='dT_lim = 10 W/die x R_uniform', W_per_pJ=W_PER_PJ, grid={})
    for ratio in RATIOS:
        cell = TA.Cell(ratio*R_stack)
        U = TA.Mod(cell.lam, cell.uniform(1.0)); Ru = TA.steady_max(U)
        pf_u = {s: TA.exact_peak(U, sch[s])/Ru for s in SCHEDULES}
        for phi in PHIS:
            mod = TA.Mod(cell.lam, cell.source(float(phi), 1.0))
            st = TA.steady_max(mod)
            red = TA.reduce_rows(mod, np.argsort(-mod.phi.sum(axis=1))[:6])
            for s in SCHEDULES:
                ref = TA.exact_peak(red, sch[s])/Ru
                row = dict(ref=ref, avg_1d=TA.DUTY, trans_1d=pf_u[s], avg_3d=TA.DUTY*st/Ru,
                           trace1ms_3d=TA.trace_peak(red, sch[s], 1e-3)/Ru,
                           block_3d=TA.exact_peak(red, sch['S0 one block'])/Ru, static_peak_1d=1.0)
                res['grid'][f'{ratio}|{phi}|{s}'] = row
        print(f'[{time.time() - t0:5.0f}s] R_ext/R_stack {ratio}: phi 0.285 S1m ref E_crit '
              f"{e_crit(res['grid'][f'{ratio}|{PHIS[0]}|{SCHEDULES[1]}']['ref']):.3f}, "
              f"phi 0.9 {e_crit(res['grid'][f'{ratio}|{PHIS[-1]}|{SCHEDULES[1]}']['ref']):.3f} pJ/bit", flush=True)
        json.dump(res, open(OUT, 'w'), indent=1)
    print(f'wrote {os.path.relpath(OUT)}')

if __name__ == '__main__':
    main()
