#!/usr/bin/env python3
"""Figure: which unmeasured quantity actually matters, and what to do about it.

Modelled on the ECTC template (ECTC 2020 face-to-face 3D microprocessor thermal study),
which pairs a diagnosis with a mitigation section rather than stopping at the diagnosis.

Left: sensitivity of the delivered-bandwidth ceiling to each unmeasured quantity, each
swept over its full literature or plausible range. Right: what buys the margin back.

The result worth the space: the memory device's own thermal conductivity, the number this
work spent the most effort pinning to measured literature, moves the answer by 0.3%. The
BEOL integration around it moves it by 95% and 73%. The thermal answer belongs to the
packaging, not to the device.
"""
import os, sys, csv
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures')
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.8,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,
                     'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

sens = list(csv.DictReader(open(os.path.join(ROOT,'assets','sweep','thermal_sensitivity.csv'))))
mit  = list(csv.DictReader(open(os.path.join(ROOT,'assets','sweep','thermal_mitigation.csv'))))
BASE = 18.57

fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.8, 4.7), facecolor=SURF,
                               gridspec_kw={'width_ratios': [1.15, 1.0]})
fig.subplots_adjust(left=0.175, right=0.975, top=0.715, bottom=0.275, wspace=0.60)
for ax in (axL, axR): ax.set_facecolor(SURF)

# ---- left: tornado
sens = [r for r in sens if 'E/bit' not in r['parameter']]     # E/bit is off-scale, noted in text
sens.sort(key=lambda r: float(r['swing_frac']))
names = [r['parameter'] for r in sens]
lo = np.array([float(r['cap_low_TBs']) for r in sens])
hi = np.array([float(r['cap_high_TBs']) for r in sens])
y = np.arange(len(sens))
for i, (a, b) in enumerate(zip(lo, hi)):
    x0, x1 = min(a, b), max(a, b)
    col = S2 if (x1-x0)/BASE > 0.25 else MUTED
    axL.barh(i, x1-x0, left=x0, height=0.56, color=col, alpha=0.75, zorder=3)
    axL.text(x1+0.7, i, f'{(x1-x0)/BASE*100:.0f}%', fontsize=7.8, color=col, va='center', zorder=5)
axL.axvline(BASE, color=INK, lw=1.4, zorder=4)
axL.text(BASE+0.5, len(sens)-0.35, f'baseline {BASE:.1f} TB/s', fontsize=7.8, color=INK, va='center')
axL.set_yticks(y); axL.set_yticklabels(names, fontsize=8.0)
axL.set_xlim(7, 32); axL.set_xlabel('delivered read bandwidth ceiling  [TB/s]')
axL.grid(True, axis='x', color=GRID, lw=0.5, zorder=0)
axL.set_title('(a)  the device\'s own thermal conductivity is the LEAST\nimportant unmeasured number; the BEOL around it is the most',
              fontsize=9.2, color=INK, loc='left', pad=8)


# ---- right: mitigation
mit = mit[::-1]
lab = [m['change'] for m in mit]
val = np.array([float(m['vs_base']) for m in mit])
cols = [S3 if v >= 1.35 else (MUTED if v < 1.1 else S1) for v in val]
axR.barh(np.arange(len(mit)), val, height=0.58, color=cols, alpha=0.8, zorder=3)
for i, v in enumerate(val):
    axR.text(v+0.015, i, f'{v:.2f}x', fontsize=8.0, color=INK2, va='center', zorder=5)
axR.axvline(1.0, color=INK, lw=1.2, zorder=4)
axR.set_yticks(np.arange(len(mit)))
axR.set_yticklabels([l.replace(' -> ', ' $\\rightarrow$ ') for l in lab], fontsize=7.6)
axR.set_xlim(0.9, 2.05); axR.set_xlabel('bandwidth ceiling, relative to the 4-tier baseline')
axR.grid(True, axis='x', color=GRID, lw=0.5, zorder=0)
axR.set_title('(b)  and the fixes are integration choices, not device choices',
              fontsize=9.2, color=INK, loc='left', pad=8)


fig.text(0.02, 0.955, 'The thermal answer belongs to the BEOL integration, not to the memory device',
         fontsize=12.0, color=INK, va='top')
fig.text(0.02, 0.893, 'Verified 1D transient solver (analytic x2; MAPDL 1D 0.02%; MAPDL 3D 1.3%). Ceiling is set by a temperature budget, '
         'dT = R$_{th}$ x 20 W,\nso that geometry changes move R$_{th}$ and the peak fraction independently rather than being hidden inside a fixed watt budget.',
         fontsize=7.8, color=INK2, va='top', linespacing=1.5)
fig.text(0.02, 0.115, 'E/bit is off the left scale: 0.014-0.260 pJ/bit spans 35.7-688 TB/s, so it remains the one measurement worth asking for.',
         fontsize=7.6, color=S3, va='top')
fig.text(0.02, 0.078, 'Substrate thinning is the odd one out: it lowers R$_{th}$ but removes the thermal mass that does the duty-cycle averaging, so the two nearly\n'
         'cancel and only 1.04x survives. A steady-state study would have credited it with the full R$_{th}$ improvement.',
         fontsize=7.6, color=RED, va='top', linespacing=1.5)
for ext in ('png','svg','pdf'):
    fig.savefig(os.path.join(FIG, f'thermal-sensitivity.{ext}'), dpi=250, facecolor=SURF)
print('wrote assets/figures/thermal-sensitivity.{png,svg,pdf}')
