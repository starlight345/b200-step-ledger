#!/usr/bin/env python3
"""Figure: does finer temporal resolution converge on the reference B_max? (temporal_spatial_ablation.json)

One panel per package boundary. x = the temporal input, from the exact schedule through window
means of growing length to the static average; the static peak sits apart at the left, since it
is a bound rather than a resolution. y = B_max(method) / B_max(reference), log scale.
  - tier-uniform model vs its own exact answer        (temporal ladder, uniform power)
  - macro phi=0.9 model vs its own exact answer        (temporal ladder, concentrated power)
  - tier-uniform model vs the macro phi=0.9 reference  (temporal resolution without spatial)
"""
import os, sys, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, '..', 'assets', 'sweep', 'temporal_spatial_ablation.json')))
OUT = os.path.join(HERE, '..', 'assets', 'figures', 'temporal-spatial-ablation')
SCH = sys.argv[1] if len(sys.argv) > 1 else 'S1 on the measured kernel trace'
INK, INK2, AXIS, GRID = '#0b0b0b', '#52514e', '#b8b7b1', '#e6e5e1'
S1C, S2C, S3C = '#2a78d6', '#eb6834', '#1baf7a'          # categorical slots 1-3, fixed order
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'],
                     'font.size': 8, 'svg.fonttype': 'none', 'axes.edgecolor': AXIS,
                     'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
                     'text.color': INK, 'axes.unicode_minus': False})

W = sorted(R['design']['windows_s'])
LADDER = ['exact'] + [f'trace-{w*1e6:g}us' for w in W] + ['static-avg']
XT = ['exact'] + [f'{w*1e6:g} µs' if w < 1e-3 else f'{w*1e3:g} ms' for w in W] + ['static avg']
PKGS = ['ideal lid', 'R_ext/R_stack 2.9', 'production deck']
UNI, CON = 'tier-uniform (1D)', 'macro phi=0.900'

def c(pkg, sp):
    return R['cases'][f'{pkg} | {sp} | {SCH}']

fig, axs = plt.subplots(1, 3, figsize=(7.4, 3.1), sharey=True, facecolor='white')
x = np.arange(len(LADDER)) + 1
for ax, pkg in zip(axs, PKGS):
    u, k = c(pkg, UNI), c(pkg, CON)
    series = [(UNI + ' model, own reference', S1C, [u['exact']/u[m] for m in LADDER], u['exact']/u['static-peak']),
              ('macro φ=0.9 model, own reference', S2C, [k['exact']/k[m] for m in LADDER], k['exact']/k['static-peak']),
              ('tier-uniform model vs macro φ=0.9', S3C, [k['exact']/u[m] for m in LADDER], k['exact']/u['static-peak'])]
    ax.axhspan(1/1.05, 1.05, color=GRID, lw=0, zorder=0)
    ax.axhline(1.0, color=INK2, lw=0.8, ls=(0, (2, 2)), zorder=1)
    for lab, col, ys, sp in series:
        ax.plot(x, ys, color=col, lw=2, marker='o', ms=4, mec='white', mew=0.8, zorder=3, label=lab)
        ax.plot([0], [sp], color=col, marker='v', ms=6, mec='white', mew=0.8, ls='none', zorder=3)
    ax.set_yscale('log')
    ax.set_xticks([0] + list(x)); ax.set_xlim(-0.6, len(LADDER) + 0.6)
    ax.set_xticklabels(['static peak'] + XT, rotation=90, fontsize=6.2)
    ax.axvline(0.5, color=AXIS, lw=0.6)
    ax.set_title(pkg, fontsize=7.6, color=INK)
    ax.grid(True, axis='y', which='major', color=GRID, lw=0.5, zorder=0)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)
axs[0].set_ylabel('B_max(method) / B_max(reference)\n>1 optimistic, <1 pessimistic', fontsize=7.2)
h, l = axs[0].get_legend_handles_labels()
fig.legend(h, l, loc='lower center', ncol=3, fontsize=6.4, frameon=False, bbox_to_anchor=(0.5, 0.0))
fig.suptitle(f'Temporal input vs reference, schedule: {SCH}; shaded ±5%', fontsize=7.4, color=INK2, y=0.995)
fig.tight_layout(rect=(0, 0.07, 1, 1))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
tag = SCH.split()[0] + ('-measured' if 'measured' in SCH else '')
for ext in ('png', 'pdf'):
    fig.savefig(f'{OUT}-{tag}.{ext}', dpi=220)
print(f'wrote {os.path.relpath(OUT)}-{tag}.png/.pdf')
