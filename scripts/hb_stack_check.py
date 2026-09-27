#!/usr/bin/env python3
"""Does the ECTC headline survive on a hybrid-bonded SRAM die instead of a BEOL tier?

Feasibility check for re-basing the ECTC case on a technology that ships. SRAM stacked on
logic by hybrid bonding exists: AMD 3D V-Cache (2nd generation puts the cache die UNDER the
core die) and MI300 (Infinity Cache in the base die under the compute dies). Our BEOL tier
already sits on the far side of the logic from the heat sink, so the matching hybrid-bond
case is an SRAM die bonded under the GPU logic die. Same solver, same load -- duty 4.80%,
a 38 W/die burst at 0.5 pJ/bit -- and only the stack changes:

  BEOL tier (current):   sink | TIM 50 | Si 500 | logic 1 | BEOL 8 | tier 0.05 | ILD 0.3 | x2
  hybrid bond, F2F:      sink | TIM 50 | Si 500 | logic 1 | BEOL 8 | bond | SRAM BEOL 8 |
                         SRAM device 1 | SRAM Si t          (SRAM face up, bulk away from sink)
  hybrid bond, F2B:      sink | TIM 50 | Si 500 | logic 1 | BEOL 8 | bond | SRAM Si t |
                         SRAM device 1 | SRAM BEOL 8        (SRAM bulk toward the logic)

The board side stays adiabatic, as in the BEOL model. Geometry values are placeholders to be
replaced by published ones (V-Cache / MI300 / SoIC); the thinned-die thickness t and the bond
layer are swept because they are the two numbers the answer could hinge on.

Three treatments per stack, as in the abstract: the steady-state rule (peak fraction 1),
the single-node lumped RC with the stack's own step-response tau, and the layered transient.
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(__file__))
import thermal_stack_solver as TS
import ectc_thermal_model as M

SI = TS.MAT['Si']
IGZO = TS.MAT['SRAM_tier']                   # BEOL baseline keeps its a-IGZO tier
TS.MAT['SRAM_Si']   = SI
TS.MAT['bond']      = (1.4, 2200.0, 730.0)   # SiO2 bonding dielectric; Cu pads ignored (pessimistic)
TS.MAT['bond_cu']   = (10.0, 2200.0, 730.0)  # with ~5-10% Cu pad area, an effective-medium guess

def hb_stack(orient='F2F', t_sram_si_um=20.0, bond='bond', t_bond_um=1.0,
             t_sram_beol_um=8.0, t_si_um=500.0, t_beol_um=8.0, t_tim_um=50.0):
    L = [('TIM', t_tim_um*1e-6), ('Si', t_si_um*1e-6), ('logic', 1e-6), ('BEOL', t_beol_um*1e-6),
         (bond, t_bond_um*1e-6)]
    if orient == 'F2F':
        L += [('BEOL', t_sram_beol_um*1e-6), ('SRAM_tier', 1e-6), ('SRAM_Si', t_sram_si_um*1e-6)]
    else:
        L += [('SRAM_Si', t_sram_si_um*1e-6), ('SRAM_tier', 1e-6), ('BEOL', t_sram_beol_um*1e-6)]
    return L

def vcache_stack(orient='F2B', t_sram_si_um=6.0, t_bond_um=0.425, t_logic_si_um=7.2,
                 t_dummy_um=750.0, t_dummy_bond_um=0.425, t_sram_beol_um=8.0, t_beol_um=8.0,
                 t_tim_um=50.0):
    """A stack with the dimensions published for shipping hybrid-bonded SRAM: SRAM die silicon
    ~6 um, logic die silicon 7.2 um, ~750 um dummy silicon on top on a 425 nm oxide bond
    (Ryzen 7 9800X3D teardown, T. Wassick via TweakTown, 2024 -- secondary source), 9 um
    hybrid-bond pitch with the upper die face-down onto the TSV die's back (face-to-back;
    AMD, Smith et al. ISCA 2024 for MI300). The SRAM die sits under the logic die, as in the
    9800X3D and MI300. F2B: the SRAM die's bulk faces the logic; F2F given for comparison."""
    L = [('TIM', t_tim_um*1e-6), ('Si', t_dummy_um*1e-6), ('bond', t_dummy_bond_um*1e-6),
         ('Si', t_logic_si_um*1e-6), ('logic', 1e-6), ('BEOL', t_beol_um*1e-6),
         ('bond', t_bond_um*1e-6)]
    if orient == 'F2B':
        L += [('SRAM_Si', t_sram_si_um*1e-6), ('SRAM_tier', 1e-6), ('BEOL', t_sram_beol_um*1e-6)]
    else:
        L += [('BEOL', t_sram_beol_um*1e-6), ('SRAM_tier', 1e-6), ('SRAM_Si', t_sram_si_um*1e-6)]
    return L

def use_device(material):
    """The solver tags the heat-source layer 'SRAM_tier'; its material is IGZO for the BEOL
    tier and silicon for a hybrid-bonded SRAM die."""
    TS.MAT['SRAM_tier'] = material

def treatments(layers, q_burst, duty=TS.DUTY, period=TS.PERIOD):
    tau, R = TS.tier_tau(layers, TS.DIE_AREA_M2, q_burst)
    pf_layered = TS.periodic_peak_frac(layers, TS.DIE_AREA_M2, q_burst, duty, period)[0]
    pf_lumped = M.pss_peak(duty, tau, period)
    return tau, R, pf_lumped, pf_layered

def tier_minus_logic(layers, q_burst, duty=TS.DUTY, period=TS.PERIOD):
    tt, Tt, Tl = TS.solve(layers, TS.P_LOGIC_DIE, q_burst, TS.DIE_AREA_M2, 12*period, 5e-6,
                          duty, period, T_sink=60.0, record_every=1)
    last = tt >= 11*period
    return Tt[last].max() - Tl[last].mean()

if __name__ == '__main__':
    q = M.p_burst_W(0.5)/2                      # per die, 0.5 pJ/bit example
    cases = [('BEOL tier (current abstract)', TS.build_stack(n_tiers=2))]
    for orient in ('F2F', 'F2B'):
        for t in (10.0, 20.0, 50.0, 100.0):
            cases.append((f'hybrid bond {orient}, SRAM Si {t:g} um', hb_stack(orient, t)))
    cases.append(('hybrid bond F2F, SRAM Si 20 um, Cu-rich bond', hb_stack('F2F', 20.0, bond='bond_cu')))
    print(f'load: duty {TS.DUTY*100:.2f}%, period {TS.PERIOD*1e3:.3f} ms, burst {q:.1f} W/die, '
          f'logic {TS.P_LOGIC_DIE:.1f} W/die\n')
    print(f"{'stack':>46} {'tau ms':>7} {'lumped':>7} {'layered':>8}  {'caps @20 W, 0.5 pJ/bit: ss / lumped / layered':>46}"
          f"  {'lumped/layered':>14} {'tier-logic K':>12}")
    for name, lay in cases:
        use_device(IGZO if name.startswith('BEOL') else SI)
        tau, R, pl, pv = treatments(lay, q)
        d = tier_minus_logic(lay, q)
        caps = [M.bw_cap_TBs(20.0, 0.5, pf) for pf in (1.0, pl, pv)]
        print(f'{name:>46} {tau*1e3:>7.2f} {pl:>7.4f} {pv:>8.4f}  '
              f'{caps[0]:>14.1f} / {caps[1]:>6.1f} / {caps[2]:>6.1f} TB/s{"":>6}'
              f'  {pv/pl:>13.2f}x {d:>12.3f}')
