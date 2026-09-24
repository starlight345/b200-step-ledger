#!/usr/bin/env python3
"""The single figure for the ECTC abstract (one figure is all the CFP allows).

It has to carry the whole argument at once:
  - what the workload demands of the tier (the HBM admission floor, and the fabric ceiling)
  - how far apart three thermal models put the ceiling for the SAME device
  - and whether a bottom-up E/bit budget clears the bar

The result the figure exists to show: the achievable E/bit band lies entirely to the LEFT
of where the conservative steady-state rule crosses the admission floor at a 20 W tier
budget. The tier is admissible under the pessimistic rule, not only the generous one.
"""
import os, sys, math
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
import ectc_thermal_model as M
import ebit_budget as B

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures'); os.makedirs(FIG, exist_ok=True)
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':9,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,
                     'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

P_W   = 20.0
PF_SOLVER = 0.2693   # thermal_stack_solver + MAPDL agree to 0.02%
C_DP  = M.capacity_GB(800.0, 2); DUTY = M.duty(C_DP)
lo, hi = B.budget(0)['total'], B.budget(1)['total']
E = np.logspace(math.log10(0.015), math.log10(1.2), 300)

fig, ax = plt.subplots(figsize=(7.6, 5.0), facecolor=SURF)
fig.subplots_adjust(left=0.098, right=0.975, top=0.80, bottom=0.135)
ax.set_facecolor(SURF); ax.set_xscale('log'); ax.set_yscale('log')

ax.axhspan(0.4, M.BW_HBM, color=RED, alpha=0.085, zorder=1)
ax.axvspan(lo, hi, color=S3, alpha=0.13, zorder=2)
ax.text(math.sqrt(lo*hi), 620, 'achievable E/bit, bottom-up\n%.3f - %.3f pJ/bit' % (lo, hi),
        fontsize=8.2, color=S3, ha='center', va='top', zorder=7)

for pf, col, lw, lab in ((1.0, S2, 2.4, 'steady-state rule  BW $\\leq$ P/E\n(what the device model applies)'),
                         (PF_SOLVER, S1, 2.4, 'transient, 1D stack solver\n(verified vs analytic)'),
                         (DUTY, MUTED, 1.4, 'perfect averaging (floor)')):
    ax.plot(E, M.bw_cap_TBs(P_W, E, pf), color=col, lw=lw, zorder=5)

ax.axhline(M.BW_HBM, color=INK, lw=1.4, zorder=6)
ax.text(0.0157, M.BW_HBM*1.14, 'HBM effective 6.40 TB/s -- below this the tier never pays',
        fontsize=8.0, color=INK, va='bottom', zorder=7)
ax.axhline(M.B_R, color=INK2, lw=1.2, ls=(0, (4, 2)), zorder=6)
ax.text(0.0157, M.B_R*1.14, 'fabric ceiling 19 TB/s', fontsize=8.0, color=INK2, va='bottom', zorder=7)

ax.text(0.40, 190, 'steady-state rule', fontsize=8.2, color=S2, ha='left', rotation=-31)
ax.text(0.115, 175, 'transient', fontsize=8.2, color=S1, ha='left', rotation=-31)

ax.plot([0.5], [M.bw_cap_TBs(P_W, 0.5, 1.0)], marker='o', ms=9, mfc=RED, mec='white', mew=1.4, zorder=8)
ax.annotate('device-model example 0.5 pJ/bit\n$\\rightarrow$ 5.0 TB/s, below the floor.\n'
            '%.1f$\\times$ above our pessimistic corner' % (0.5/hi),
            xy=(0.5, 5.0), xytext=(0.115, 0.85), fontsize=8.0, color=RED, ha='left',
            arrowprops=dict(arrowstyle='-', color=RED, lw=1.0, shrinkA=2, shrinkB=6), zorder=8)

x_cross = P_W/(8*M.BW_HBM)
ax.plot([x_cross], [M.BW_HBM], marker='o', ms=8, mfc='white', mec=S2, mew=2.0, zorder=8)
ax.annotate('the bar, read the hard way:\n%.2f pJ/bit at %.0f W' % (x_cross, P_W),
            xy=(x_cross, M.BW_HBM), xytext=(0.47, 22), fontsize=8.0, color=S2, ha='left',
            arrowprops=dict(arrowstyle='-', color=S2, lw=1.0, shrinkA=2, shrinkB=6), zorder=8)

ax.text(1.16, 0.52, 'tier slower than HBM', fontsize=8.0, color=RED, ha='right', va='bottom', zorder=7)
ax.set_xlim(0.015, 1.2); ax.set_ylim(0.4, 900)
ax.set_xlabel('tier energy per bit  [pJ/bit]')
ax.set_ylabel('delivered read bandwidth ceiling  [TB/s]')
ax.grid(True, which='both', color=GRID, lw=0.5, zorder=0)

fig.text(0.098, 0.965, 'A %.0f W BEOL SRAM tier clears the bar under the conservative rule, not just the generous one' % P_W,
         fontsize=11.4, color=INK, va='top')
fig.text(0.098, 0.905, 'Llama-3.1-8B decode on a measured B200 ledger, B=8 N=2048. C2 2-layer 800 mm$^2$ = %.2f GB, tier duty %.2f%%,\n'
         'burst %.0f $\\mu$s in a %.3f ms step. Achievable band: 5 nm SRAM array estimate at the optimistic end, 7 nm 1 Mb macro read\n'
         '(periphery included) x 2 BEOL penalty at the pessimistic end. Geometry and materials: a literature-anchored design study.'
         % (C_DP, DUTY*100, M.burst_s(C_DP)*1e6, M.T_STEP*1e3),
         fontsize=7.9, color=INK2, va='top', linespacing=1.5)
for ext in ('png', 'svg', 'pdf'):
    fig.savefig(os.path.join(FIG, f'ectc-abstract.{ext}'), dpi=300, facecolor=SURF)
print(f'band {lo:.3f}-{hi:.3f} pJ/bit; bar at {x_cross:.3f} pJ/bit ({P_W:.0f} W, steady-state)')
print(f'margin at the pessimistic corner: {x_cross/hi:.2f}x')
print('wrote assets/figures/ectc-abstract.{png,svg,pdf}')
