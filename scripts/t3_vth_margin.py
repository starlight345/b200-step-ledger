#!/usr/bin/env python3
"""T-3, quantified: how much threshold-voltage shift can this cell actually afford?

Until now T-3 was a worry with two numbers next to each other and no arithmetic between
them: the device deck reports a read static noise margin of 155 mV, and the oxide-
semiconductor literature reports a temperature-driven threshold shift of about -1.5 V
across -25 to 105 C for the best-stabilised composition. Putting those side by side
suggests a problem but does not bound one. This bounds it.

The missing quantity is the cell's SNM sensitivity to a threshold shift, S = -dSNM/dVth,
which needs a device model nobody has given us. So S is the axis, not an assumption, and
the output is the S at which the cell runs out of read margin.

Two regimes matter and they are far apart:
  MISMATCH   the shift lands asymmetrically on one side of the cell. The butterfly curve
             is pushed sideways and SNM is consumed close to one-for-one at high S.
  UNIFORM    every transistor shifts together. A symmetric shift moves both lobes and the
             margin survives far better; what is left is second order.
Real devices sit between: a systematic temperature shift is largely uniform and partly
compensable by design, while its device-to-device spread is mismatch.

Deck source: 3DSRAM_n5a v2.0 `data/D11_회로시뮬.csv` (contact resistance corner sweep).
Literature: best reported temperature stability for a Zn-rich In-Ga-Zn-O TFT.
"""
import os, sys, csv

# --- deck circuit simulation, D11 [device deck, simulated not measured]
DECK = [
    dict(corner='0 (ideal)',     hold_mV=302, read_mV=155, write_mV=522),
    dict(corner='n2k/p11k',      hold_mV=302, read_mV=159, write_mV=514),
    dict(corner='n13k/p275k',    hold_mV=288, read_mV=159, write_mV=445),
]
READ_SNM_mV = min(d['read_mV'] for d in DECK)        # 155, the binding one

# --- literature [third-party]
DVTH_FULL_V   = 1.5      # |dVth| across -25 .. 105 C, best reported Zn-rich IGZO
T_LO, T_HI    = -25.0, 105.0
TJ_OPERATING  = (25.0, 100.0)   # the tier sits at the logic junction; room to ~Tj

# --- the mismatch component, which this script used to say nobody had published.
# Mitard et al., "Sub-40mV Sigma-VTH IGZO nFETs in 300mm Fab", ECS Trans. 98, 205 (2020)
# (arXiv:2411.16299). >100 back-gated IGZO nFETs, no failures and no filtering, L_CH from
# long down to ~120 nm and W_CH down to 200 nm, on an industry 300mm flow. The reported
# spread of V_TH-ON is "often less than 40mV with a minimum of 20mV".
#
# Two things to be careful about before using it.
#  1. It is measured AT WAFER SCALE, so it carries systematic across-wafer variation on
#     top of the local random mismatch. Variances add, so sigma_local <= sigma_wafer:
#     using it as the local mismatch is CONSERVATIVE, which is the direction we want.
#  2. No temperature dependence is reported. These are room-temperature numbers and our
#     tier sits near the logic junction, so d(sigma)/dT is what is still missing.
SIGMA_VTH_mV = (20.0, 40.0)     # (best reported, typical bound) [third-party, 300mm]
N_DEVICES_6T = (1, 2, 4)        # dominant uncorrelated contributors to one read margin
ARRAY_GB     = 4.22             # C2, 2 tiers, 800 mm^2, 2 dies -- the design point
YIELD_TARGET = 0.99

def dvth_over(t_lo, t_hi):
    """Linear interpolation of the reported shift onto our operating span."""
    return DVTH_FULL_V * (t_hi - t_lo)/(T_HI - T_LO)

if __name__ == '__main__':
    span = dvth_over(*TJ_OPERATING)
    print('=== the two numbers ===')
    for d in DECK:
        print(f"  deck corner {d['corner']:<14} hold {d['hold_mV']} mV   "
              f"read {d['read_mV']} mV   write {d['write_mV']} mV")
    print(f'  binding read SNM: {READ_SNM_mV} mV')
    print(f'  literature |dVth|: {DVTH_FULL_V*1e3:.0f} mV over {T_LO:.0f}..{T_HI:.0f} C')
    print(f'  our span {TJ_OPERATING[0]:.0f}..{TJ_OPERATING[1]:.0f} C is '
          f'{(TJ_OPERATING[1]-TJ_OPERATING[0])/(T_HI-T_LO)*100:.0f}% of that '
          f'-> |dVth| ~ {span*1e3:.0f} mV if linear\n')

    print('=== what S would have to be for the cell to survive ===')
    print('  S = -dSNM/dVth [mV of read SNM lost per mV of threshold shift]\n')
    print(f"{'S':>6} {'tolerable |dVth|':>18} {'vs full 1500 mV':>17} {'vs our span':>14}")
    rows = []
    for S in (0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0):
        tol_mV = READ_SNM_mV/S
        ok_full = tol_mV >= DVTH_FULL_V*1e3
        ok_span = tol_mV >= span*1e3
        rows.append(dict(S=S, tolerable_dVth_mV=tol_mV,
                         survives_full_range=ok_full, survives_operating_span=ok_span))
        print(f'{S:>6.2f} {tol_mV:>15.0f} mV {"OK" if ok_full else "FAILS":>17} '
              f'{"OK" if ok_span else "FAILS":>14}')

    S_break_full = READ_SNM_mV/(DVTH_FULL_V*1e3)
    S_break_span = READ_SNM_mV/(span*1e3)
    print(f'\n  break-even S against the full reported range: {S_break_full:.3f}')
    print(f'  break-even S against our operating span:      {S_break_span:.3f}')
    print(f'\n  For a 6T cell a MISMATCH shift typically consumes read SNM with S in the')
    print(f'  0.3-1.0 range. Both break-even values are an order of magnitude below that.')
    print(f'  -> If the reported shift lands as mismatch, the cell has no read margin left.')
    print(f'  -> It survives only if the shift is close to UNIFORM (S well under {S_break_span:.2f}),')
    print(f'     i.e. systematic with temperature and compensable, with the device-to-device')
    print(f'     SPREAD being what actually has to be small.')
    print(f'\n  This is the measurement to ask for: not the absolute dVth(T), which is')
    print(f'  published, but its MISMATCH component across a die at operating temperature.')

    # ---------------------------------------------------------------- sigma closure
    from statistics import NormalDist
    nbits   = ARRAY_GB * 1e9 * 8
    p_fail  = (1.0 - YIELD_TARGET) / nbits
    n_sigma = -NormalDist().inv_cdf(p_fail)
    print('\n=== closing it with the published mismatch number ===')
    print(f'  sigma(V_TH-ON) = {SIGMA_VTH_mV[0]:.0f}..{SIGMA_VTH_mV[1]:.0f} mV '
          f'(300mm, >100 devices, L_CH ~120 nm; wafer scale, so an UPPER bound on local)')
    print(f'  array {ARRAY_GB:.2f} GB = {nbits:.3e} bits, yield {YIELD_TARGET:.0%}'
          f'  ->  per-cell P_fail < {p_fail:.2e}  ->  need {n_sigma:.2f} sigma\n')
    print(f'  criterion:  S * sigma * sqrt(k) * n_sigma  <=  {READ_SNM_mV} mV')
    print(f'  so the largest S the cell can afford is  S_max = SNM / (n_sigma * sigma * sqrt(k))\n')
    print(f"{'sigma [mV]':>11} {'k':>3} {'S_max':>8}   verdict against real 6T S = 0.3..1.0")
    srows = []
    for sig in SIGMA_VTH_mV:
        for k in N_DEVICES_6T:
            s_max = READ_SNM_mV / (n_sigma * sig * k**0.5)
            if   s_max >= 1.0: v = 'clears the whole range'
            elif s_max >= 0.3: v = f'decided inside the range (fails above S={s_max:.2f})'
            else:              v = 'fails the whole range'
            srows.append(dict(sigma_mV=sig, k=k, n_sigma=round(n_sigma,3),
                              S_max=round(s_max,4), verdict=v))
            print(f'{sig:>11.0f} {k:>3d} {s_max:>8.3f}   {v}')
    lo = min(r['S_max'] for r in srows); hi = max(r['S_max'] for r in srows)
    print(f'\n  S_max spans {lo:.2f}..{hi:.2f} across the reported sigma and the mismatch')
    print(f'  multiplicity k. Real 6T cells sit at S = 0.3..1.0, so the boundary now lands')
    print(f'  INSIDE that range instead of an order of magnitude below it.')
    print(f'\n  What changed: T-3 used to be unbounded -- the only published number was the')
    print(f'  {DVTH_FULL_V*1e3:.0f} mV MEAN shift, and a mean shift told us nothing about margin.')
    print(f'  With a published spread the question is no longer open-ended. It is now two')
    print(f'  numbers: where in 0.3..1.0 this cell sits, and how sigma grows with temperature.')

    outs = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sweep', 't3_sigma_margin.csv')
    with open(outs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(srows[0])); w.writeheader(); w.writerows(srows)
    print(f'\nwrote {os.path.relpath(outs)}')

    out = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sweep', 't3_vth_margin.csv')
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f'\nwrote {os.path.relpath(out)}')
