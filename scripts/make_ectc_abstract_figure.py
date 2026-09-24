#!/usr/bin/env python3
"""The single figure for the ECTC abstract (one figure is all the CFP allows), v2.

v1 plotted the bandwidth ceiling against E/bit and titled it "clears the bar under the
conservative rule". After the pessimistic E/bit corner was anchored to macro-level data
(0.260 -> 0.374 pJ/bit, ebit_budget.py) that margin is 4%, and the abstract's headline is the
disagreement between thermal treatments, not the steady-state margin. v2 carries the
abstract's two load-bearing paragraphs:

  (a) P3 -- one tier, three thermal treatments: the steady-state rule rejects it (5.0 TB/s),
      the single-node lumped model accepts it widely (77.3), the verified layered transient
      admits it at the fabric limit (18.6). The literature E/bit band is shaded, so P6 reads
      off the same axes.
  (b) P4/P5 -- the macro-resolved 3D transient in Ansys MAPDL: six decode steps of the
      tier periphery, array and logic (POST26 history of prod_k1_phi90), with the tier plane
      at the end of a burst as an inset (MAPDL's own render, cropped to the plan view).

English only; this goes into the submission docx.
"""
import os, sys, math
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
import ectc_thermal_model as M
import ebit_budget as B

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures'); os.makedirs(FIG, exist_ok=True)
INK, INK2, MUTED, GRID, AXIS = '#0b0b0b', '#52514e', '#898781', '#e6e5df', '#b9b8ae'
BLUE, ORANGE, GREEN, RED, GRAY = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b', '#7d7c76'
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'],
                     'font.size': 8, 'svg.fonttype': 'none', 'axes.edgecolor': AXIS,
                     'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
                     'text.color': INK, 'axes.unicode_minus': False})

P_W, E_EX = 20.0, 0.5
PF = {'steady': 1.0, 'lumped': 0.0647, 'verified': 0.2693}   # thermal_stack_solver.py, literature stack
lo, hi = B.budget(0)['total'], B.budget(1)['total']
E = np.logspace(math.log10(0.015), math.log10(1.2), 300)

fig = plt.figure(figsize=(7.4, 2.95), facecolor='white')

# ------------------------------------------------------------------ (a)
ax = fig.add_axes([0.072, 0.155, 0.425, 0.64])
ax.set_xscale('log'); ax.set_yscale('log')
ax.axhspan(0.5, M.BW_HBM, color=RED, alpha=0.07, lw=0, zorder=1)
ax.axvspan(lo, hi, color=GREEN, alpha=0.14, lw=0, zorder=1)
for key, col, lw, ls, lab in (('steady', ORANGE, 1.8, '-', 'steady-state rule  BW $\leq$ P/E'),
                              ('lumped', GRAY, 1.4, (0, (4, 2)), 'single-node lumped RC'),
                              ('verified', BLUE, 2.4, '-', 'layered transient (verified)')):
    ax.plot(E, M.bw_cap_TBs(P_W, E, PF[key]), color=col, lw=lw, ls=ls, zorder=4, label=lab)
ax.axhline(M.BW_HBM, color=INK, lw=1.1, zorder=5)
ax.axhline(M.B_R, color=INK2, lw=0.9, ls=(0, (2, 2)), zorder=5)
ax.text(0.0165, M.BW_HBM*0.82, 'HBM 6.40 TB/s: below this the tier never pays', fontsize=6.4, va='top', color=INK)
ax.text(0.0165, M.B_R*1.08, 'on-die fabric ceiling 19 TB/s', fontsize=6.4, va='bottom', color=INK2)
ax.text(0.052, 10.6, 'achievable E/bit\n%.3f–%.3f pJ/bit' % (lo, hi), fontsize=6.4, color='#128a5f',
        ha='center', va='center', weight='bold', linespacing=1.15)
pts = {k: M.bw_cap_TBs(P_W, E_EX, PF[k]) for k in PF}
box = dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.85)
for key, col, txt in (('steady', ORANGE, '%.1f  (%.1fx low)' % (pts['steady'], pts['verified']/pts['steady'])),
                      ('verified', BLUE, '%.1f' % pts['verified']),
                      ('lumped', GRAY, '%.1f  (%.2fx high)' % (pts['lumped'], pts['lumped']/pts['verified']))):
    ax.plot([E_EX], [pts[key]], 'o', ms=5.5, mfc=col, mec='white', mew=1.0, zorder=7)
    ax.text(E_EX*1.10, pts[key]*(1.18 if key == 'verified' else 1.0), txt, fontsize=6.6, color=col,
            va='center', ha='left', weight='bold', zorder=8, bbox=box)
ax.axvline(E_EX, color=INK2, lw=0.6, ls=(0, (1, 2)), zorder=2)
ax.text(E_EX, 1.62, 'device-model\nexample 0.5', fontsize=5.8, color=INK2, ha='center', va='bottom', linespacing=1.1,
        bbox=dict(boxstyle='square,pad=0.1', fc='#f8eeeb', ec='none'), zorder=6)
ax.legend(loc='upper right', fontsize=6.3, frameon=True, framealpha=1.0, edgecolor=AXIS, handlelength=2.2,
          borderpad=0.4, labelspacing=0.3)
ax.set_xlim(0.015, 1.2); ax.set_ylim(1.5, 700)
ax.set_xticks([0.02, 0.05, 0.1, 0.2, 0.5, 1.0]); ax.set_xticklabels(['0.02', '0.05', '0.1', '0.2', '0.5', '1'])
ax.set_yticks([2, 5, 10, 20, 50, 100, 200, 500]); ax.set_yticklabels(['2', '5', '10', '20', '50', '100', '200', '500'])
ax.minorticks_off()
ax.grid(True, which='major', color=GRID, lw=0.5, zorder=0)
ax.set_xlabel('tier energy per bit  [pJ/bit]', fontsize=7.4)
ax.set_ylabel('deliverable read bandwidth  [TB/s]', fontsize=7.4)
ax.tick_params(labelsize=6.8)
fig.text(0.072, 0.965, '(a)  One tier, three thermal treatments', fontsize=8.6, weight='bold', va='top')
fig.text(0.072, 0.905, '20 W tier budget; duty 4.80% (217 µs burst per 4.515 ms decode step)',
         fontsize=6.4, color=INK2, va='top')

# ------------------------------------------------------------------ (b)
H = np.loadtxt(os.path.join(ROOT, 'assets', 'mapdl', 'macro', 'png', 'history.txt'))
t_ms, peri, arr, logic = H[:, 0]*1e3, H[:, 1], H[:, 2], H[:, 3]
bx = fig.add_axes([0.625, 0.155, 0.355, 0.64])
bx.plot(t_ms, peri, color=RED, lw=1.3, label='tier periphery (max)', zorder=4)
bx.plot(t_ms, logic, color=INK2, lw=1.0, label='logic plane', zorder=3)
bx.plot(t_ms, arr, color=BLUE, lw=1.0, label='tier array', zorder=3)
bx.set_xlim(0, 32.0); bx.set_ylim(99.85, 100.95)          # room on the right for the inset
bx.set_xlabel('time  [ms]', fontsize=7.4); bx.set_ylabel('temperature  [°C]', fontsize=7.4, labelpad=2)
bx.tick_params(labelsize=6.8)
bx.grid(True, color=GRID, lw=0.5, zorder=0)
bx.legend(loc='lower left', fontsize=5.9, frameon=False, ncol=3, handlelength=1.3, borderaxespad=0.15,
          columnspacing=0.9)
last = t_ms > t_ms[-1] - 4.515                               # converged last period
i = np.flatnonzero(last)[np.argmax(peri[last])]
RES = {l.split()[0]: dict(kv.split('=') for kv in l.replace('= ', '=').split()[2:] if '=' in kv)
       for l in open(os.path.join(ROOT, 'assets', 'mapdl', 'macro', 'results.txt')) if 'RESULT' in l}
d_tl = float(RES['prod_k1_phi90']['peak']) - float(RES['prod_k1_phi90']['logic'])   # POST1: 0.482 K
bx.annotate('tier - logic %.2f K\n(1.14 K with worst-case BEOL k)' % d_tl,
            xy=(t_ms[i], peri[i]), xytext=(17.5, 100.84), fontsize=6.2, color=RED, va='center', ha='center',
            arrowprops=dict(arrowstyle='-', color=RED, lw=0.7, shrinkA=1))
pk_t = [t_ms[np.flatnonzero((t_ms > a) & (t_ms < a + 4.515))[np.argmax(peri[(t_ms > a) & (t_ms < a + 4.515)])]]
        for a in (-0.5, 4.0)]
bx.annotate('', xy=(pk_t[0], 100.67), xytext=(pk_t[1], 100.67),
            arrowprops=dict(arrowstyle='<->', color=INK2, lw=0.7))
bx.text(0.5*(pk_t[0] + pk_t[1]), 100.69, '4.515 ms', fontsize=6.0, color=INK2, ha='center', va='bottom')
tier = Image.open(os.path.join(FIG, 'mapdl-macro-tier.png')).convert('RGB')
a = np.asarray(tier).astype(int); sat = a.max(2) - a.min(2)
x0, x1, y1 = int(a.shape[1]*0.30), int(a.shape[1]*0.70), int(a.shape[0]*0.78)   # plan view only: no triad, logo or legend
ys, xs = np.where(sat[:y1, x0:x1] > 60)
plan = tier.crop((x0 + xs.min() - 3, ys.min() - 3, x0 + xs.max() + 4, ys.max() + 4))
INS_H = 0.44                                                   # of figure height
ins_w = INS_H*2.95*plan.width/plan.height/7.4                  # keep the plan view's aspect
ins_x = 0.975 - ins_w                                          # right of the last cycle (t > 27 ms)
ins = fig.add_axes([ins_x, 0.30, ins_w, INS_H])
ins.imshow(plan); ins.set_xticks([]); ins.set_yticks([])
for sp in ins.spines.values(): sp.set_edgecolor(INK2); sp.set_linewidth(0.6)
fig.text(ins_x + 0.5*ins_w, 0.285, 'tier plane\nat burst end\n100.03–\n100.61 °C', fontsize=5.3, ha='center', va='top',
         color=INK2, linespacing=1.1)
fig.text(0.625, 0.965, '(b)  Macro-resolved 3D transient (Ansys MAPDL)', fontsize=8.6, weight='bold', va='top')
fig.text(0.625, 0.905, '153 × 518 µm SRAM macro, 90% of read power in its periphery,\n'
                       'on a 349 W/die logic plane at a 100 °C junction. An independently\n'
                       'built Icepak FEA model matches its steady state to 0.06 mK.',
         fontsize=6.2, color=INK2, va='top', linespacing=1.25)

for ext in ('png', 'svg', 'pdf'):
    fig.savefig(os.path.join(FIG, f'ectc-abstract.{ext}'), dpi=300, facecolor='white')
print('three answers at 0.5 pJ/bit: ' + ', '.join('%s %.1f' % (k, v) for k, v in pts.items()))
print(f'band {lo:.3f}-{hi:.3f} pJ/bit; last-period periphery peak {peri[i]:.3f} C, logic then {logic[i]:.3f} C')
print('wrote assets/figures/ectc-abstract.{png,svg,pdf}')
