#!/usr/bin/env python3
"""Exact references for the AEDT Icepak V-Cache column runs (scripts/aedt/buildvcache.py ...).

The column is 10 x 10 um with adiabatic sides, so it IS the 1D problem, and every body starts at
the sink temperature (20 C): a cold start, which Icepak runs as is. The reference is therefore not
the periodic state but the same cold start, solved exactly mode by mode (sota_comparators.Modal):
the tier's largest temperature in each period, for each Icepak case.

  lid  / S0    TIM outer face held at 20 C, one 216.72 us block per 4.515 ms  (buildvcache+loadburst)
  lid  / S1    the same face, burst_shape's Gate-1 schedule (layers 0-9, 1.5 us per kernel)
  film / S0    the face cooled by the production decks' film, h = 8368.4 W/m2K to 20 C
  film / S1

P_COL = 0.4817196 mW puts the burst-power steady rise at exactly 100 K with the ideal lid, so the
lid rows read directly as percent of the static-peak rise. The film rows use the same P_COL.

  python3 scripts/aedt_vcache_reference.py     # -> assets/aedt/vcache_reference.json
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_stack_solver as TS
import hb_stack_check as HB
import sota_comparators as SC
import burst_shape as BS
import package_boundary as PB
import mapdl_vcache as MV

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'aedt', 'vcache_reference.json')
A_COL = 1e-10
N_PER = 4
T_SINK = 20.0

def cold_start_peaks(mod, segs, q_scale, n_per=N_PER, n_sub=8):
    """Tier maximum in each of n_per periods from the zero state (K above the sink), and its time."""
    lam, w = mod.lam, mod.w
    y = np.zeros_like(lam); out = []; t = 0.0
    for _ in range(n_per):
        best, tb = -1.0, 0.0
        for d, q in segs:
            qq = q*q_scale
            if qq > 0:
                s = np.linspace(d/n_sub, d, n_sub)[:, None]
                ys = y*np.exp(-lam*s) + w/lam*(-np.expm1(-lam*s))*qq
                v = (ys @ mod.phi.T).max(axis=1)
                if v.max() > best: best, tb = v.max(), t + s[v.argmax(), 0]
            y = y*np.exp(-lam*d) + w/lam*(-np.expm1(-lam*d))*qq
            t += d
        out.append((best, tb))
    return out

def main():
    HB.use_device(HB.SI)
    lay = MV.LAYERS
    res = {'A_col_m2': A_COL, 't_sink_C': T_SINK, 'n_periods': N_PER, 'cases': {}}
    # per-column network: the per-die solvers scale by area, so per watt of COLUMN power the
    # response is the per-die response x (A_die / A_col)
    for bname, r_ext in (('lid', 0.0), ('film', PB.R_EXT_PROD)):
        mod = PB.modal_with_film(lay, r_ext)
        scale = TS.DIE_AREA_M2/A_COL
        R_col_lid = SC.Modal(lay, TS.DIE_AREA_M2).R*scale
        p_col = 100.0/R_col_lid                                 # W: 100 K steady rise with the lid
        for sname in ('S0', 'S1'):
            segs = BS.schedule(sname, 'mixed')
            # schedule watts are per die at 38 W; the column carries p_col during a full-rate burst
            pk = cold_start_peaks(mod, segs, p_col/BS.P_BURST*scale)
            per = BS.periodic_peak(mod, segs)[0]/BS.P_BURST*p_col*scale
            res['cases'][f'{bname}/{sname}'] = dict(
                P_col_W=p_col, R_ext_K_per_W_die=r_ext,
                cold_start_peak_C=[T_SINK + v for v, _ in pk], cold_start_peak_time_s=[t for _, t in pk],
                periodic_peak_rise_K=per, static_peak_rise_K=mod.R*scale*p_col)
            print(f'{bname}/{sname}: P_col {p_col*1e3:.7f} mW; cold-start tier peaks '
                  + ', '.join(f'{T_SINK + v:.4f} C @ {t*1e3:.3f} ms' for v, t in pk)
                  + f'; periodic {T_SINK + per:.4f} C, static-peak {T_SINK + mod.R*scale*p_col:.2f} C')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, 'w'), indent=1)
    print(f'wrote {os.path.relpath(OUT)}')

if __name__ == '__main__':
    main()
