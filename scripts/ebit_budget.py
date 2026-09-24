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
# Silicon SRAM array read energy per bit [third-party, published ESTIMATE]:
#   B. Dieny et al., "Opportunities and challenges for spintronics in the microelectronics
#   industry," Nat. Electron. 3, 446-459 (2020), Table 1: HP-SRAM 5 nm 17, HD-SRAM 5 nm 55,
#   HD-SRAM 7 nm 50 fJ/bit. The table's own source is a 2018 process-roadmap post that gives
#   no energies, and the table does not say whether periphery is included -- so this is an
#   estimate, and it sets only the OPTIMISTIC end below.
#   (The "128 kb array ~34 fJ/bit" once listed here is Marinella et al., IEEE JETCAS 8, 86
#   (2018), at 14/16 nm -- not an advanced node. Dropped.)
ARRAY_PJ = (0.017, 0.055)
# Macro-level anchor [third-party]: N. P. Jouppi et al., "Ten lessons from three generations
# shaped Google's TPUv4i," Proc. ISCA 2021, Table 2 -- energy per 64-bit SRAM read at ~7 nm,
# periphery and in-macro wiring included: 8 KB 7.5 pJ, 32 KB 8.5 pJ, 1 MB 14 pJ, i.e. 117 /
# 133 / 219 fJ/bit. Per-bit energy grows with macro size, and the device team's macro is 1 Mb
# = 128 KB (DESIGN_POINT_3DSRAM.md), log-interpolated to 0.167 pJ/bit.
# CORRECTION (2026-09-24): the pessimistic corner used to be array 0.055 x periphery 2.0 =
# 0.110 pJ/bit, which is what an 8 KB macro costs, not a 1 Mb one. It now takes the
# macro-level value at our macro size (periphery already inside) -- 7 nm data for a 5 nm-class
# design, so conservative. Pessimistic total 0.260 -> 0.374 pJ/bit.
MACRO_7NM = ((8, 7.5/64), (32, 8.5/64), (1024, 14.0/64))    # (KB, pJ/bit)
MACRO_KB = 128

def macro_pj(kb=MACRO_KB):
    """Jouppi's 7 nm per-bit macro read energy, log-interpolated in macro size."""
    for (k0, e0), (k1, e1) in zip(MACRO_7NM, MACRO_7NM[1:]):
        if k0 <= kb <= k1:
            return e0 + (e1 - e0)*math.log(kb/k0)/math.log(k1/k0)
    raise ValueError(kb)

# BEOL oxide-semiconductor arrays versus 6T SRAM. The earlier 1-3x guess assumed weaker
# drive must cost energy; the literature says the opposite for the cell types actually
# being built in BEOL. The measured claim, checked against the source rather than a note
# about it: Waqar et al. report an IWO 2T gain-cell last-level-cache macro at 3 nm giving
# "29% lower read latency and 18% lower read energy with comparable write
# performance/energy at ~0.5x the leakage and total area" versus 3 nm SRAM.
#
# CORRECTION (2026-09-23): this file previously carried 0.5 as the optimistic energy
# ratio. That 0.5x in the source is LEAKAGE AND AREA, not energy. The reported energy
# advantage is 18%, i.e. a ratio of 0.82. The optimistic corner now uses 0.82.
# Our design point is a 6T-style BEOL SRAM rather than a gain cell, so the pessimistic
# corner keeps a 2x penalty for the 6T variant. [third-party + assumption]
BEOL_PENALTY = (0.82, 2.0)
# Sense amps, decoders, timing. Commonly comparable to the array itself. [ASSUMPTION]
PERIPHERY_MULT = (1.0, 2.0)
# One short vertical hop (MIV / hybrid bond) plus the tier-local bus. Sub-mm, so small
# compared with a reticle traverse. [ASSUMPTION]
LINK_PJ = (0.005, 0.040)

def budget(lo_hi=0, macro_level=True):
    """lo_hi=0 -> optimistic corner, 1 -> pessimistic corner.

    The pessimistic corner takes the macro-level energy (periphery included) at our macro
    size; macro_level=False gives the superseded array x periphery-multiplier version."""
    if lo_hi == 1 and macro_level:
        a = macro_pj()*BEOL_PENALTY[1]
        p = a
    else:
        a = ARRAY_PJ[lo_hi]*BEOL_PENALTY[lo_hi]
        p = a*PERIPHERY_MULT[lo_hi]
    return dict(array_beol=a, with_periphery=p, link=LINK_PJ[lo_hi], total=p+LINK_PJ[lo_hi])

def requirement(P_W, bw_TBs, peak_frac):
    """E/bit the tier may spend and still deliver bw_TBs inside a P_W budget."""
    return P_W/(8.0*bw_TBs)/peak_frac

if __name__ == '__main__':
    C = M.capacity_GB(800.0, 2); d = M.duty(C)
    PF_SOLVER = 0.2693          # scripts/thermal_stack_solver.py, 2-tier literature stack (5-C);
                                # 0.2724 was the pre-literature 1 um / 1 um guess
    print('=== achievable E/bit, bottom-up [pJ/bit] ===')
    print(f"{'term':>28} {'optimistic':>11} {'pessimistic':>12}   basis")
    lo, hi = budget(0), budget(1)
    print(f"{'Si array read':>28} {ARRAY_PJ[0]:>11.3f} {'':>12}   Dieny 2020 Table 1, 5 nm HP (estimate)")
    print(f"{'Si 1 Mb macro read':>28} {'':>11} {macro_pj():>12.3f}   Jouppi 2021 Table 2, 7 nm, periphery incl.")
    print(f"{'x BEOL device penalty':>28} {BEOL_PENALTY[0]:>11.2f} {BEOL_PENALTY[1]:>12.2f}   Waqar 2025 gain cell / 6T assumption")
    print(f"{'x periphery':>28} {PERIPHERY_MULT[0]:>11.1f} {'(in macro)':>12}   ASSUMPTION (optimistic end)")
    print(f"{'+ vertical link':>28} {LINK_PJ[0]:>11.3f} {LINK_PJ[1]:>12.3f}   ASSUMPTION (swept)")
    print(f"{'TOTAL':>28} {lo['total']:>11.3f} {hi['total']:>12.3f}")
    print(f"  (superseded array-level pessimistic corner: {budget(1, macro_level=False)['total']:.3f} pJ/bit"
          f" -- an 8 KB macro's energy)")
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
