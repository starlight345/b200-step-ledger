#!/usr/bin/env python3
"""ECTC figure: the 3D SRAM tier's thermal envelope is set by DUTY CYCLE, not by peak P/E.

The device team's Q3 relation  BW <= P_budget / E_bit  is a STEADY-STATE relation.
Applied literally it caps a 0.5 pJ/bit tier at 5.0 TB/s on a 20 W budget, which is
below the HBM effective rate 6.40 TB/s -- and SRAM_HIERARCHY_MODEL.md:428 then finds
every design point below 1.000x. That verdict is what currently closes paper A's
physical gate.

But an LLM decode tier is not a steady-state load. At the GB-scale design point the
tier serves f_red of a 17.158 GB/step demand at B_R, so it is active only
    d = f_red * D_step / (B_R * t_step)   ~= 2-5% of wall time.
This script asks the two questions that decides whether the steady-state cap applies:

  (a) ADMISSIBILITY  what delivered BW does a given (E/bit, P_budget) allow, under the
      steady-state relation and under the duty-corrected one?
  (b) TRANSIENT      does the stack's thermal time constant actually integrate the
      burst (-> average power governs) or track it (-> peak power governs)?
      First-order periodic steady state, swept over tau; no assumed tau is needed to
      locate the crossover, only to place a design point on it.

Grades: BW_HBM_eff / t_step / D_step  regression-derived + trace replay [canon].
        E/bit, P_budget, R_th, C_th    ASSUMPTION -- swept, never a single point.
        f_red                          trace replay [Gate 1, C2 2-layer].
"""
import os, sys, math, csv
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
from canon_3dsram import get
import ectc_thermal_model as M

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures')
SWP  = os.path.join(ROOT, 'assets', 'sweep')
os.makedirs(FIG, exist_ok=True); os.makedirs(SWP, exist_ok=True)

SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,
                     'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

BW_HBM  = get('b200_baseline.hbm_effective_TBs_llama')      # 6.40, regression-derived
B_R     = 19.0            # canon: design_point_axes.read_delivery_cap_TBs (via_L2_fabric)
T_STEP  = 4.515e-3        # s, Gate 3 base step = t0 1.852 ms + 17.031 GB / 6.40 TB/s
D_STEP  = 17.158          # GB/step, unified ledger total demand [trace replay]
# Single design point for the whole ECTC figure set: C2 2-layer at the 800 mm2 geometric
# upper bound, 4.22 GB, f_red 24.0%. Taken from the shared model so the figures cannot drift
# apart (they did once: this file was on the 600 mm2 point while ectc_requirements.py was on 800).
C_DP    = M.capacity_GB(800.0, 2)
F_RED   = M.f_red(C_DP)   # 0.240 [trace replay, Gate 1 anchor scaled by capacity]
DUTY    = (F_RED * D_STEP / B_R) * 1e-3 / T_STEP            # GB/(TB/s) = ms

def bw_cap(P_W, e_pJ, duty=1.0):
    """Delivered-BW ceiling [TB/s] from a power budget. duty=1 is the steady-state relation."""
    return P_W / (8.0 * e_pJ) / duty

def pss(duty, Tp, tau):
    """Periodic steady state of a first-order node under a square wave, normalised to Pb*R.
    Returns (peak, trough). peak -> 1 means the node reaches the BURST temperature;
    peak -> duty means it perfectly averages."""
    x = Tp / tau
    a, b = math.exp(-duty*x), math.exp(-(1-duty)*x)
    hi = (1-a) / (1-a*b)
    return hi, hi*b

# ---------------------------------------------------------------- panel data
E = np.logspace(math.log10(0.05), math.log10(1.5), 240)
TAU = np.logspace(math.log10(2e-6), math.log10(2e-1), 300)
peak = np.array([pss(DUTY, T_STEP, t)[0] for t in TAU])

fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.6, 4.7), facecolor=SURF)
fig.subplots_adjust(left=0.062, right=0.985, top=0.735, bottom=0.145, wspace=0.235)
for ax in (axL, axR): ax.set_facecolor(SURF)

# ---------------- left: admissibility in the (E/bit, delivered BW) plane
# One solid line per family at 20 W, with a band spanning the 10-50 W budget range,
# so the two RELATIONS stay legible instead of six crossing lines.
axL.set_xscale('log'); axL.set_yscale('log')
axL.axhspan(0.3, BW_HBM, color=RED, alpha=0.085, zorder=1)
axL.fill_between(E, bw_cap(10, E), bw_cap(50, E), color=S2, alpha=0.13, zorder=2)
axL.fill_between(E, bw_cap(10, E, DUTY), bw_cap(50, E, DUTY), color=S3, alpha=0.13, zorder=2)
axL.plot(E, bw_cap(20, E), color=S2, lw=2.2, zorder=5)
axL.plot(E, bw_cap(20, E, DUTY), color=S3, lw=2.2, zorder=5)
axL.text(0.056, 62, 'steady-state\nBW <= P / E\n10-50 W budget', fontsize=7.6, color=S2, va='center', zorder=6)
axL.text(0.056, 1380, 'duty-corrected   BW <= P / (E * d)\nsame budget, d = %.1f%%' % (DUTY*100),
         fontsize=7.6, color=S3, va='top', zorder=6)
axL.axhline(BW_HBM, color=INK2, lw=1.1, zorder=4)
axL.text(1.42, BW_HBM*1.14, 'HBM effective %.2f TB/s -- admission floor' % BW_HBM,
         fontsize=7.4, color=INK2, ha='right', va='bottom', zorder=6)
axL.axhline(B_R, color=S1, lw=1.1, ls=(0,(4,2)), zorder=4)
axL.text(1.42, B_R*0.87, 'via-L2 fabric cap %.0f TB/s' % B_R, fontsize=7.4, color=S1, ha='right', va='top', zorder=6)
axL.text(1.42, 0.40, 'tier delivers less than HBM:\nno capacity makes it pay',
         fontsize=7.4, color=RED, ha='right', va='bottom', zorder=6)
axL.plot([0.5],[5.0], marker='o', ms=8, mfc=RED, mec='white', mew=1.3, zorder=8)
axL.annotate('device-team example\n0.5 pJ/bit, 20 W -> 5.0 TB/s\nthis point is what closes paper A',
             xy=(0.5,5.0), xytext=(0.245,1.15), fontsize=7.3, color=RED, ha='center',
             arrowprops=dict(arrowstyle='-', color=RED, lw=0.9, shrinkA=2, shrinkB=5), zorder=8)
axL.plot([0.5],[bw_cap(20,0.5,DUTY)], marker='o', ms=8, mfc=S3, mec='white', mew=1.3, zorder=8)
axL.annotate('same device, same 20 W, duty-corrected -> %.0f TB/s.\nThe VERIFIED answer is 18.4 (panel b): the two\nrelations bracket it by 4.2x in opposite directions.' % bw_cap(20,0.5,DUTY),
             xy=(0.5,bw_cap(20,0.5,DUTY)), xytext=(0.95,300), fontsize=7.3, color=S3, ha='center',
             arrowprops=dict(arrowstyle='-', color=S3, lw=0.9, shrinkA=2, shrinkB=5), zorder=8)
axL.set_xlim(0.05,1.5); axL.set_ylim(0.3,1500)
axL.set_xlabel('E/bit  [pJ/bit]   -- unmeasured; this is the axis, not a point')
axL.set_ylabel('delivered read bandwidth ceiling  [TB/s]')
axL.set_title('(a)  the same device is admissible or useless\ndepending on which power relation you apply',
              fontsize=9.2, color=INK, loc='left', pad=8)
axL.grid(True, which='both', color=GRID, lw=0.5, zorder=0)

# ---------------- right: does the stack see peak or average?
axR.set_xscale('log')
axR.fill_between(TAU*1e6, DUTY, peak, color=S2, alpha=0.11, zorder=1)
axR.plot(TAU*1e6, peak, color=S2, lw=2.1, zorder=5, label='peak temperature reached, / (P_burst  *  R_th)')
axR.axhline(DUTY, color=S3, lw=1.6, zorder=4)
axR.text(2.4, DUTY*1.35, f'perfect averaging = duty {DUTY*100:.1f}%\n(temperature set by P_avg)',
         fontsize=7.4, color=S3, va='bottom')
axR.axhline(1.0, color=RED, lw=1.2, ls=(0,(4,2)), zorder=4)
axR.text(2.4, 0.94, 'tracks the burst  (temperature set by P_peak)', fontsize=7.4, color=RED, va='top')
for x, lab, col in ((F_RED*D_STEP/B_R*1e3, f'burst {F_RED*D_STEP/B_R*1e3:.0f} us', INK2),
                    (T_STEP*1e6, f'decode step {T_STEP*1e6:.0f} us', INK2)):
    axR.axvline(x, color=col, lw=0.9, ls=':', zorder=3)
    axR.text(x*1.1, 0.014, lab, fontsize=7.2, color=col, rotation=90, va='bottom')
# The 1D stack solver's own answer, which is what panel (b)'s curve is being tested against.
# scripts/thermal_stack_solver.py, 2-tier stack, verified vs two analytic solutions.
TAU_SOLVER, PF_SOLVER = 6.78e-3, 0.2693
pf_lumped_at_tau = pss(DUTY, T_STEP, TAU_SOLVER)[0]   # pss returns (peak, trough)
axR.plot([TAU_SOLVER*1e6], [pf_lumped_at_tau], marker='o', ms=7, mfc='white', mec=S2, mew=1.8, zorder=7)
axR.plot([TAU_SOLVER*1e6], [PF_SOLVER], marker='D', ms=8, mfc=S1, mec='white', mew=1.3, zorder=8)
axR.annotate('', xy=(TAU_SOLVER*1e6, PF_SOLVER*0.86), xytext=(TAU_SOLVER*1e6, pf_lumped_at_tau*1.14),
             arrowprops=dict(arrowstyle='<->', color=S1, lw=1.3), zorder=8)
axR.text(TAU_SOLVER*1e6*0.72, math.sqrt(PF_SOLVER*pf_lumped_at_tau),
         '4.2x', fontsize=8.6, color=S1, ha='right', va='center', zorder=9)
axR.annotate('1D stack solver at the same tau -- a thin\nlow-k tier on a thick substrate is NOT one\n'
             'first-order node, so the lumped curve\nunderpredicts the peak by 4.2x.',
             xy=(TAU_SOLVER*1e6*0.93, PF_SOLVER), xytext=(4.2, 0.215), fontsize=7.2, color=S1, ha='left',
             arrowprops=dict(arrowstyle='-', color=S1, lw=0.9, shrinkA=2, shrinkB=4), zorder=8)
axR.text(1.1e5, 0.0385, 'single-node lumped model\n(this curve)', fontsize=7.2, color=S2,
         ha='right', va='top', zorder=7)
axR.set_yscale('log'); axR.set_ylim(0.012,1.7); axR.set_xlim(2,2e5)
axR.set_xlabel('thermal time constant of the stacked layer  tau = R_th  *  C_th  [us]   -- ASSUMPTION axis')
axR.set_ylabel('peak temperature rise / (P_burst  *  R_th)')
axR.set_title('(b)  and the reduced-order model you pick moves the answer by 4.2x:\n'
              'tau >> step => average governs;  tau << burst => peak governs',
              fontsize=9.2, color=INK, loc='left', pad=8)
axR.grid(True, which='both', color=GRID, lw=0.5, zorder=0)

fig.text(0.062, 0.955, 'Duty cycle, not peak P/E, sets the 3D SRAM tier\'s thermal envelope',
         fontsize=12.4, color=INK, va='top')
fig.text(0.062, 0.898, f'Llama-3.1-8B decode, B=8 N=2048, C2 2-layer 800 mm2 = {C_DP:.2f} GB.  Tier serves {F_RED*100:.0f}% of a '
         f'{D_STEP:.2f} GB/step demand at {B_R:.0f} TB/s -> active {DUTY*100:.1f}% of a {T_STEP*1e3:.3f} ms step.\n'
         f'E/bit, R_th and C_th are unmeasured and are swept, never assumed.  Decode is the verified thermal worst case: '
         f'prefill duty is 0.08-0.41% (scripts/prefill_phase.py).',
         fontsize=7.8, color=INK2, va='top', linespacing=1.5)

for ext in ('png','svg'):
    fig.savefig(os.path.join(FIG, f'ectc-thermal-envelope.{ext}'), dpi=220, facecolor=SURF)

with open(os.path.join(SWP, 'ectc_thermal_envelope.csv'), 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['quantity','value','unit','grade'])
    w.writerow(['duty_cycle', f'{DUTY:.5f}', 'fraction', 'trace-replay-derived'])
    w.writerow(['burst_length', f'{F_RED*D_STEP/B_R*1e3:.1f}', 'us', 'trace-replay-derived'])
    w.writerow(['step_time', f'{T_STEP*1e3:.3f}', 'ms', 'regression-derived'])
    for P in (10,20,50):
        w.writerow([f'ebit_breakeven_vs_HBM_{P}W', f'{P/(8*BW_HBM):.4f}', 'pJ/bit', 'derived'])
        w.writerow([f'ebit_breakeven_vs_HBM_{P}W_dutycorrected', f'{P/(8*BW_HBM)/DUTY:.4f}', 'pJ/bit', 'derived'])
        w.writerow([f'ebit_for_fabric_cap_{P}W', f'{P/(8*B_R):.4f}', 'pJ/bit', 'derived'])

print(f'duty = {DUTY*100:.2f}%   burst = {F_RED*D_STEP/B_R*1e3:.1f} us   step = {T_STEP*1e3:.3f} ms')
print('\nE/bit required to clear the HBM 6.40 TB/s admission floor [pJ/bit]:')
print(f"{'P_budget':>10} {'steady-state':>14} {'duty-corrected':>16}")
for P in (10,20,50):
    print(f'{P:>8} W {P/(8*BW_HBM):>14.3f} {P/(8*BW_HBM)/DUTY:>16.2f}')
print('\nwrote assets/figures/ectc-thermal-envelope.{png,svg}, assets/sweep/ectc_thermal_envelope.csv')
