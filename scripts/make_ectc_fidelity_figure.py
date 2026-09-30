#!/usr/bin/env python3
"""Candidate ECTC Fig. 1: (a) model-fidelity regime map, (b) boundary error by abstraction.

(a) For two read layouts, the cheapest model whose allowable E/bit at 19 TB/s is within 10% of the
    macro-resolved exact answer, over package cooling (R_ext/R_stack) x periphery share phi:
      1D time-averaged < 1D transient < macro-resolved, 1 ms epochs < full spatiotemporal
    Lines: the reference's allowable E/bit at 19 TB/s [pJ/bit]. Bar: B200-class liquid cooling.
(b) E_max(model) / E_max(reference) for every abstraction at three representative points
    (1 = exact, >1 optimistic, <1 pessimistic). All from fidelity_regime_map.json.
"""
import os, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.patches

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, '..', 'assets', 'sweep', 'fidelity_regime_map.json')))
OUT = os.path.join(HERE, '..', 'assets', 'figures', 'ectc-fidelity')
INK, INK2, AXIS, GRID = '#0b0b0b', '#52514e', '#b8b7b1', '#e6e5e1'
SHADE = ['#b7d3f6', '#6da7ec', '#2a78d6', '#184f95']           # blue 150 / 300 / 450 / 600, ordinal
LAB = ['1D time-averaged', '1D transient', 'macro-resolved,\n1 ms epochs', 'full\nspatiotemporal']
CASE_COL = ['#2a78d6', '#eb6834', '#1baf7a']                    # categorical slots 1-3
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'],
                     'font.size': 7, 'axes.edgecolor': AXIS, 'axes.labelcolor': INK2, 'xtick.color': INK2,
                     'ytick.color': INK2, 'text.color': INK, 'axes.unicode_minus': False})
ratios, phis, tol = np.array(R['ratios']), np.array(R['phis']), R['tol']
MAPS = [('S1 on the measured kernel trace', 'Gate-1 placement (layers 0-9),\nmeasured kernel order'),
        ('S4 page slice', 'page slice of every matrix\n(reads interleaved over the step)')]
CASES = [('S4 page slice', 5.8, 'interleaved reads, production film (5.8)'),
         ('S1 on the measured kernel trace', 3.0, 'Gate-1 placement, liquid cooling (3.0)'),
         ('S0 one block', 0.0, 'one contiguous block, die-proximate cooling (0)')]
METHODS = [('static_peak_1d', 'static peak'), ('avg_1d', '1D time-averaged'), ('trans_1d', '1D transient'),
           ('avg_3d', 'macro, time-averaged'), ('trace1ms_3d', 'macro, 1 ms epochs'),
           ('block_3d', 'macro, one 217 µs block'), ('ref', 'macro, exact schedule (ref.)')]

def g(s, r, p, key):
    return R['grid'][f'{r}|{p}|{s}'][key]

def field(s, key):
    return np.array([[g(s, r, p, key) for r in R['ratios']] for p in R['phis']])

def ok(s, key):
    return np.abs(field(s, 'ref')/field(s, key) - 1) <= tol

fig = plt.figure(figsize=(7.4, 3.5), facecolor='white')
outer = fig.add_gridspec(1, 2, width_ratios=[2.0, 1.2], wspace=0.62, left=0.075, right=0.985, top=0.78, bottom=0.30)
inner = outer[0, 0].subgridspec(1, 2, wspace=0.08)
xs = np.arange(len(ratios))
for i, (s, title) in enumerate(MAPS):
    ax = fig.add_subplot(inner[0, i])
    reg = np.where(ok(s, 'avg_1d'), 0, np.where(ok(s, 'trans_1d'), 1, np.where(ok(s, 'trace1ms_3d'), 2, 3)))
    ax.pcolormesh(xs, phis, reg, cmap=matplotlib.colors.ListedColormap(SHADE), vmin=-0.5, vmax=3.5,
                  shading='nearest', zorder=0)
    ec = 10.0/(R['W_per_pJ']*field(s, 'ref'))
    cs = ax.contour(xs, phis, ec, levels=[0.5, 1.0, 2.0], colors='white', linewidths=0.7, linestyles='dashed', zorder=2)
    ax.clabel(cs, fmt=lambda v: f'{v:g}', fontsize=5.4, inline=True)
    lo, hi = np.interp(2.3, ratios, xs), np.interp(5.7, ratios, xs)
    ax.plot([lo, hi], [phis[0] - 0.035, phis[0] - 0.035], color=INK, lw=2.4, solid_capstyle='butt', clip_on=False)
    ax.set_xticks(xs); ax.set_xticklabels(['' if r in (0.25, 1.5) else f'{r:g}' for r in ratios], fontsize=5.6)
    ax.set_xlabel('R_ext / R_stack  (cooling worse →)', fontsize=6.3)
    ax.set_ylim(phis[0] - 0.045, phis[-1] + 0.015)
    ax.set_title(title, fontsize=6.3, color=INK, linespacing=1.05)
    if i == 0:
        ax.set_ylabel('periphery share of read power φ', fontsize=6.5)
    else:
        ax.set_yticklabels([])
    print(f'{s}: regime cells {[(reg == k).sum() for k in range(4)]}, min allowable E/bit {ec.min():.3f}')
handles = [matplotlib.patches.Patch(facecolor=c, edgecolor='none', label=l.replace(chr(10), ' ')) for c, l in zip(SHADE, LAB)]
fig.legend(handles=handles, loc='lower left', bbox_to_anchor=(0.07, 0.0), ncol=2, fontsize=5.8, frameon=False,
           handlelength=1.2, columnspacing=1.0, title='cheapest adequate model', title_fontsize=5.8, alignment='left')
fig.text(0.075, 0.955, '(a) cheapest model within ±10% of the macro-resolved allowable E/bit at 19 TB/s', fontsize=6.8, color=INK)
fig.text(0.075, 0.915, 'dashed: allowable E/bit [pJ/bit]; bar: B200-class liquid cooling;\n0.217 pJ/bit passes everywhere on both maps', fontsize=5.6, color=INK2, va='top')

ax = fig.add_subplot(outer[0, 1])
ys = np.arange(len(METHODS))[::-1]
ax.axvspan(1 - tol, 1 + tol, color=GRID, lw=0, zorder=0)
ax.axvline(1.0, color=INK2, lw=0.7, ls=(0, (2, 2)), zorder=1)
for j, (s, r, lab) in enumerate(CASES):
    p = R['phis'][-1]; ref = g(s, r, p, 'ref')
    vals = [ref/g(s, r, p, k) for k, _ in METHODS]
    ax.plot(vals, ys + (1 - j)*0.22, ls='none', marker='o', ms=4.2, mec='white', mew=0.7, color=CASE_COL[j],
            zorder=3, label=lab)
    print(lab, {m: round(v, 2) for (_, m), v in zip(METHODS, vals)})
ax.set_xscale('log'); ax.set_xlim(0.05, 14)
ax.set_yticks(ys); ax.set_yticklabels([m for _, m in METHODS], fontsize=6.0)
ax.set_xlabel('E_max(model) / E_max(reference)\n<1 pessimistic, >1 optimistic', fontsize=6.2)
ax.grid(True, axis='x', which='major', color=GRID, lw=0.5, zorder=0)
for sp in ('top', 'right'): ax.spines[sp].set_visible(False)
h, l = ax.get_legend_handles_labels()
fig.legend(h, l, loc='lower left', bbox_to_anchor=(0.50, 0.0), fontsize=5.6, frameon=False, handletextpad=0.2,
           title='representative points (R_ext/R_stack)', title_fontsize=5.8, alignment='left')
fig.text(0.66, 0.955, '(b) boundary error by abstraction, φ = 0.9', fontsize=6.8, color=INK)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
for ext in ('png', 'pdf'):
    fig.savefig(f'{OUT}.{ext}', dpi=240)
print(f'wrote {os.path.relpath(OUT)}.png/.pdf')
