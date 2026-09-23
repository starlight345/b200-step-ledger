#!/usr/bin/env python3
"""T-1 filled in as a design study: a bottom-up E/bit budget for the 3D SRAM tier.

The device deck has no power model -- its own export note says so ("no power/latency
model") and its own audit table records zero measurements. Rather than wait, this builds
the budget from public silicon-SRAM energy data plus an explicit BEOL-device penalty, and
asks whether the achievable band overlaps the requirement the workload sets.

SCOPING, and it matters. The thermal question is about power dissipated IN THE TIER, so
the budget is array + periphery + vertical link. The on-die fabric traverse from the tier
to the SMs dissipates in the LOGIC die's interconnect, which is already inside the measured
698.7 W package power -- counting it here would double-count it. The transport comparison
against HBM is a separate (and much more favourable) argument and is not made here.

Grades: array energy [third-party, public 5-7 nm Si SRAM]. BEOL penalty, periphery share
and link energy [assumption, swept]. Requirement side [regression-derived + trace replay].
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(__file__))
import ectc_thermal_model as M

# ---- achievable side ---------------------------------------------------------
# Public silicon SRAM array read energy at advanced nodes [third-party]:
#   5 nm HD-SRAM ~55 fJ/bit, 5 nm HP-SRAM ~17 fJ/bit, 7 nm HD ~50 fJ/bit,
#   128 kb array ~34 fJ/bit. We carry the 5 nm HP..HD span as the array term.
ARRAY_PJ = (0.017, 0.055)
# BEOL oxide-semiconductor arrays versus 6T SRAM. The earlier 1-3x guess assumed weaker
# drive must cost energy; the literature says the opposite for the cell types that are
# actually being built in BEOL. Monolithically stackable gain-cell arrays are reported at
# ~50% of 6T SRAM read/write energy at equal access latency (8 KiB N7 arrays, sub-2 ns at
# 27 C / sub-0.3 ns at 85 C, 0.015 um2 bitcell). Our design point is a 6T-style BEOL SRAM
# rather than a gain cell, so the optimistic corner takes the reported 0.5x and the
# pessimistic corner keeps a 2x penalty for the 6T variant. [third-party + assumption]
BEOL_PENALTY = (0.5, 2.0)
# Sense amps, decoders, timing. Commonly comparable to the array itself. [ASSUMPTION]
PERIPHERY_MULT = (1.0, 2.0)
# One short vertical hop (MIV / hybrid bond) plus the tier-local bus. Sub-mm, so small
# compared with a reticle traverse. [ASSUMPTION]
LINK_PJ = (0.005, 0.040)

def budget(lo_hi=0):
    """lo_hi=0 -> optimistic corner, 1 -> pessimistic corner."""
    a = ARRAY_PJ[lo_hi]*BEOL_PENALTY[lo_hi]
    p = a*PERIPHERY_MULT[lo_hi]
    return dict(array_beol=a, with_periphery=p, link=LINK_PJ[lo_hi], total=p+LINK_PJ[lo_hi])

def requirement(P_W, bw_TBs, peak_frac):
    """E/bit the tier may spend and still deliver bw_TBs inside a P_W budget."""
    return P_W/(8.0*bw_TBs)/peak_frac

if __name__ == '__main__':
    C = M.capacity_GB(800.0, 2); d = M.duty(C)
    PF_SOLVER = 0.2724          # scripts/thermal_stack_solver.py, 2-tier stack
    print('=== achievable E/bit, bottom-up [pJ/bit] ===')
    print(f"{'term':>28} {'optimistic':>11} {'pessimistic':>12}   basis")
    lo, hi = budget(0), budget(1)
    print(f"{'Si array read':>28} {ARRAY_PJ[0]:>11.3f} {ARRAY_PJ[1]:>12.3f}   third-party, 5 nm HP..HD")
    print(f"{'x BEOL device penalty':>28} {BEOL_PENALTY[0]:>11.1f} {BEOL_PENALTY[1]:>12.1f}   ASSUMPTION (swept)")
    print(f"{'x periphery':>28} {PERIPHERY_MULT[0]:>11.1f} {PERIPHERY_MULT[1]:>12.1f}   ASSUMPTION (swept)")
    print(f"{'+ vertical link':>28} {LINK_PJ[0]:>11.3f} {LINK_PJ[1]:>12.3f}   ASSUMPTION (swept)")
    print(f"{'TOTAL':>28} {lo['total']:>11.3f} {hi['total']:>12.3f}")
    print(f"\n  achievable band: {lo['total']:.3f} - {hi['total']:.3f} pJ/bit")
    print(f"  device-deck example was 0.5 pJ/bit -- {0.5/hi['total']:.1f}x above our pessimistic corner")

    print('\n=== requirement, from the workload ===')
    print(f'  design point C2 2-layer {C:.2f} GB, duty {d*100:.2f}%')
    print(f"\n{'target':>34} {'P=10 W':>9} {'20 W':>9} {'50 W':>9}")
    for lab, bw, pf in (('clear HBM 6.40, steady-state rule', M.BW_HBM, 1.0),
                        ('clear HBM 6.40, solver transient', M.BW_HBM, PF_SOLVER),
                        ('reach fabric 19, steady-state', M.B_R, 1.0),
                        ('reach fabric 19, solver transient', M.B_R, PF_SOLVER)):
        r = [requirement(P, bw, pf) for P in (10, 20, 50)]
        print(f'{lab:>34} {r[0]:>9.3f} {r[1]:>9.3f} {r[2]:>9.3f}')

    print('\n=== does the band clear the bar? ===')
    for P in (10, 20, 50):
        for lab, bw, pf in (('HBM floor, steady-state', M.BW_HBM, 1.0),
                            ('fabric 19, solver transient', M.B_R, PF_SOLVER)):
            req = requirement(P, bw, pf)
            v = ('YES, both corners' if hi['total'] <= req else
                 'optimistic only' if lo['total'] <= req else 'NO')
            print(f'  P={P:>2} W, {lab:<28} need <= {req:6.3f}  have {lo["total"]:.3f}-{hi["total"]:.3f}  -> {v}')
    print('\n  NOTE: the on-die fabric traverse to the SMs is NOT in this budget -- it')
    print('  dissipates in the logic die and is already inside the measured 698.7 W.')
