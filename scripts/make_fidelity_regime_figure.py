#!/usr/bin/env python3
"""Figure: the cheapest adequate thermal model over cooling x periphery share, per schedule.

Region shade = cheapest model whose allowable E/bit at 19 TB/s is within TOL of the macro-resolved
exact answer: 1D time-averaged < 1D transient < macro-resolved transient (darker = more fidelity
needed). Lines = the reference's allowable E/bit at 19 TB/s (the feasibility boundary); the design
point sits below every one of them when it is under their minimum. The band marks B200-class
liquid-cooled packages (R_ext/R_stack 2.3-5.7, ECTC_SOTA_THERMAL 8-2).
"""
import os, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import distance_transform_edt

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, '..', 'assets', 'sweep', 'fidelity_regime_map.json')))
OUT = os.path.join(HERE, '..', 'assets', 'figures', 'fidelity-regime-map')
INK, INK2, AXIS, GRID = '#0b0b0b', '#52514e', '#b8b7b1', '#e6e5e1'
SHADE = ['#cde2fb', '#86b6ef', '#2a78d6']            # blue ramp steps 100 / 250 / 450: ordinal
LAB = ['1D time-averaged\nsufficient', '1D transient\nsufficient', 'macro-resolved\ntransient needed']
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'],
                     'font.size': 8, 'axes.edgecolor': AXIS, 'axes.labelcolor': INK2, 'xtick.color': INK2,
                     'ytick.color': INK2, 'text.color': INK, 'axes.unicode_minus': False})
ratios, phis, tol = np.array(R['ratios']), np.array(R['phis']), R['tol']
TITLE = {'S0 one block': 'one 217 µs block', 'S1 on the measured kernel trace': 'layers 0-9, measured kernel order',
         'S2 interleaved over 32 layers': '9.4 layers interleaved over 32', 'S4 page slice': 'page slice of every matrix'}

def field(s, key):
    return np.array([[R['grid'][f'{r}|{p}|{s}'][key] for r in R['ratios']] for p in R['phis']])

def e_crit(pf):
    return 10.0/(R['W_per_pJ']*pf)

fig, axs = plt.subplots(1, 4, figsize=(7.4, 2.75), sharey=True, facecolor='white')
xs = np.arange(len(ratios))
for ax, s in zip(axs, R['schedules']):
    ref = field(s, 'ref')
    ok_avg = np.abs(ref/field(s, 'avg_1d') - 1) <= tol
    ok_tr = np.abs(ref/field(s, 'trans_1d') - 1) <= tol
    reg = np.where(ok_avg, 0, np.where(ok_tr, 1, 2))
    ax.pcolormesh(xs, phis, reg, cmap=matplotlib.colors.ListedColormap(SHADE), vmin=-0.5, vmax=2.5,
                  shading='nearest', zorder=0)
    ec = e_crit(ref)
    cs = ax.contour(xs, phis, ec, levels=[0.3, 0.5, 1.0, 2.0], colors=INK, linewidths=0.8, zorder=2)
    ax.clabel(cs, fmt=lambda v: f'{v:g}', fontsize=5.8, inline=True)
    lo, hi = np.interp(2.3, ratios, xs), np.interp(5.7, ratios, xs)
    ax.plot([lo, hi], [phis[0] - 0.02, phis[0] - 0.02], color=INK, lw=2.2, solid_capstyle='butt', clip_on=False)
    for k in range(3):
        m = reg == k
        if m.sum() >= 6:
            # the cell farthest from the region's edge and the panel's edge, in grid steps
            d = distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
            iy, ix = np.unravel_index(np.argmax(d*(1 + 1e-3*np.arange(m.size).reshape(m.shape)/m.size)), m.shape)
            ax.text(xs[ix], phis[iy], LAB[k], fontsize=5.4, ha='center', va='center',
                    color=INK if k < 2 else 'white', zorder=3)
    ax.set_xticks(xs); ax.set_xticklabels([f'{r:g}' for r in ratios], fontsize=6.0, rotation=90)
    ax.set_title(TITLE[s], fontsize=7.0, color=INK)
    ax.set_xlabel('R_ext / R_stack', fontsize=7.0)
    ax.set_ylim(phis[0] - 0.03, phis[-1] + 0.015)
    print(f'{s}: min allowable E/bit {ec.min():.3f} pJ/bit; regime counts '
          f'{[(reg == k).sum() for k in range(3)]}')
axs[0].set_ylabel('share of read power in the macro periphery φ', fontsize=7.0)
fig.suptitle(f'Cheapest model within {tol:.0%} of the macro-resolved allowable E/bit at 19 TB/s; '
             'lines: allowable E/bit [pJ/bit]; bar: B200-class liquid cooling', fontsize=7.0, color=INK2, y=0.995)
fig.tight_layout()
os.makedirs(os.path.dirname(OUT), exist_ok=True)
for ext in ('png', 'pdf'):
    fig.savefig(f'{OUT}.{ext}', dpi=220)
print(f'wrote {os.path.relpath(OUT)}.png/.pdf')
