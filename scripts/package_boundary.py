#!/usr/bin/env python3
"""How much of the burst the junction sees depends on what sits above the TIM.

sota_comparators, hotspot_rerun, burst_shape and the AEDT column all hold the TIM's top face at
a fixed temperature: an ideal lid. The production MAPDL decks (mapdl_vcache prod_*) instead end
the stack in a film calibrated so the logic junction sits at 100 C with 349 W/die, which puts
R_ext = 0.149 K/W per die beyond the TIM -- 5.8x the die stack's own 0.026 K/W. The external
path is slow (R_ext x the die's heat capacity ~ 0.15 s >> 4.5 ms), so it carries the tier's
AVERAGE power and only the die stack sees the burst:

    pf = (R_ext D + pf_stack R_stack) / (R_ext + R_stack)

Here the film is added to the network and each schedule is solved exactly, from R_ext = 0 (the
ideal lid behind every number so far) to the production decks' calibration and beyond. The
static-peak map is pf = 1 and the static-average map pf = D at every R_ext, so the two error
factors are 1/pf and pf/D.

  python3 scripts/package_boundary.py      # table + assets/sweep/package_boundary.json
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_stack_solver as TS
import hb_stack_check as HB
import sota_comparators as SC
import burst_shape as BS
import mapdl_vcache as MV

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'sweep', 'package_boundary.json')
R_EXT_PROD = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets',
                                         'mapdl', 'vcache', 'reference.json')))['r_conv_K_per_W']
R_EXTS = (0.0, 0.01, 0.025, 0.05, 0.075, 0.10, R_EXT_PROD, 0.25)
SCHEDULES = [('S0', 'mixed'), ('S1', 'mixed'), ('S1', 'host'), ('S3', 'mixed'), ('S4', 'mixed')]

def modal_with_film(layers, r_ext, area=TS.DIE_AREA_M2):
    """The sota_comparators network with a massless film of r_ext (K/W per die) between the
    TIM's top face and the fixed temperature."""
    dz, k, rc, tag = TS.discretise(layers, 0.5e-6, 80)
    n = len(dz); G = np.zeros(n + 1)
    for i in range(1, n): G[i] = 1.0/(dz[i-1]/(2*k[i-1]) + dz[i]/(2*k[i]))
    G[0] = 1.0/(dz[0]/(2*k[0]) + r_ext*area)
    A = np.diag(G[:n] + G[1:])
    for i in range(1, n): A[i, i-1] = A[i-1, i] = -G[i]
    return SC.Modal.network(A, rc*dz, [i for i, t in enumerate(tag) if t == 'SRAM_tier'], area)

def main():
    HB.use_device(HB.SI)
    lay = MV.LAYERS
    res = {'R_ext_prod_K_per_W': R_EXT_PROD, 'rows': []}
    base = SC.Modal(lay, TS.DIE_AREA_M2)
    chk = modal_with_film(lay, 0.0)
    print(f'check, R_ext = 0: R {chk.R*1e3:.4f} vs sota_comparators {base.R*1e3:.4f} mK/W; one block '
          f'{BS.periodic_peak(chk, BS.schedule("S0"))[0]/(chk.R*BS.P_BURST):.5f} vs {base.square_pss():.5f}')
    print(f'\nV-Cache F2B 6 um, exact peak fraction (TB/s at 20 W, 0.5 pJ/bit); static-peak = 1, static-average = {TS.DUTY}')
    print(f"{'R_ext K/W/die':>13} {'R_ext/R_stack':>13} " + ' '.join(f'{a+"/"+b:>17}' for a, b in SCHEDULES))
    for r in R_EXTS:
        mod = modal_with_film(lay, r)
        row = dict(R_ext=r, R_total=mod.R)
        for key in SCHEDULES:
            row['/'.join(key)] = BS.periodic_peak(mod, BS.schedule(*key))[0]/(mod.R*BS.P_BURST)
        res['rows'].append(row)
        tag = ' (prod decks)' if r == R_EXT_PROD else ''
        print(f'{r:>13.4f} {r/base.R:>13.2f} ' + ' '.join(
            f"{row['/'.join(k)]:>8.4f} ({5.0/row['/'.join(k)]:>5.1f})" for k in SCHEDULES) + tag)
    json.dump(res, open(OUT, 'w'), indent=1)
    print(f'\nwrote {os.path.relpath(OUT)}')
    pr = [r for r in res['rows'] if r['R_ext'] == R_EXT_PROD][0]
    print(f"prod-deck film, one block: static-average optimistic {pr['S0/mixed']/TS.DUTY:.2f}x, "
          f"static-peak pessimistic {1/pr['S0/mixed']:.1f}x (ideal lid: {res['rows'][0]['S0/mixed']/TS.DUTY:.2f}x, "
          f"{1/res['rows'][0]['S0/mixed']:.1f}x)")
    # does the die-thinning result survive the package film?
    print('\nSRAM die thickness (hybrid-bond F2F, as in ECTC_SOTA_THERMAL 3-4): exact TB/s')
    print(f"{'SRAM Si':>8} " + ' '.join(f'{f"{s}, R_ext {r:g}":>22}' for r in (0.0, R_EXT_PROD) for s in ('S0', 'S1')))
    res['thickness'] = {}
    for t in (10.0, 20.0, 50.0, 100.0):
        lay_t = HB.hb_stack('F2F', t); cells = []
        for r in (0.0, R_EXT_PROD):
            mod = modal_with_film(lay_t, r)
            for s in ('S0', 'S1'):
                pf = BS.periodic_peak(mod, BS.schedule(s, 'mixed'))[0]/(mod.R*BS.P_BURST)
                res['thickness'][f'{t:g}um/{s}/{r:g}'] = pf; cells.append(5.0/pf)
        print(f'{t:>6.0f}um ' + ' '.join(f'{c:>22.1f}' for c in cells))
    # the ECTC_SOTA_THERMAL section 3 practices, re-run on the realistic boundaries
    print('\npractice -> TB/s (x = practice / exact; >1 optimistic), V-Cache F2B 6 um')
    res['practices'] = {}
    cols = [(r, s) for r in (0.0, 0.075, R_EXT_PROD) for s in ('S0', 'S1')]
    print(f"{'practice':>22} " + ' '.join(f'{f"{s} R_ext {r:.3f}":>19}' for r, s in cols))
    table = {}
    for r, s in cols:
        mod = modal_with_film(lay, r); segs = BS.schedule(s, 'mixed'); ref = mod.R*BS.P_BURST
        ex = BS.periodic_peak(mod, segs)[0]/ref
        t = {'exact (burst-resolved)': ex, 'static-peak map': 1.0, 'static-average map': TS.DUTY}
        for w, lab in ((200e-6, 'trace 200 us'), (1e-3, 'trace 1 ms'), (10e-3, 'trace 10 ms')):
            t[lab] = BS.trace_peak(mod, segs, w)/ref
        table[(r, s)] = t
        res['practices'][f'{s}/{r:g}'] = t
    for lab in table[cols[0]]:
        print(f'{lab:>22} ' + ' '.join(
            f'{5.0/table[c][lab]:>8.1f} ({table[c]["exact (burst-resolved)"]/table[c][lab]:>5.2f}x)   ' for c in cols))
    json.dump(res, open(OUT, 'w'), indent=1)

if __name__ == '__main__':
    main()
