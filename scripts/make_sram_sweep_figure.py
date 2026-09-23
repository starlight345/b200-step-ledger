#!/usr/bin/env python3
"""Figure: when does a generic on-package SRAM tier pay off? (DESIGN_POINT_3DSRAM.md, 2026-09-20)

Capacity x delivered-bandwidth map of step-time speedup for a generic (object-agnostic,
ideal-capacity) SRAM tier, on the per-model calibrated timing model
step = t0 + (T - served)/BW_eff + served/BW_tier, fit on measured B200 decode anchors.
Device design points (C3/C2/C1 at the device team's read-only delivered 15 TB/s), the
working set, HBM effective bandwidth and thermal bandwidth ceilings are overlaid.
Model calculation, not a measurement. Palette follows the dataviz reference instance.
"""
import os, sys, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
sys.path.insert(0, os.path.dirname(__file__))
import sram_capacity_bandwidth_sweep as S

ROOT = os.path.join(os.path.dirname(__file__), '..')
SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9'
BLUE = ['#cde2fb','#9ec5f4','#6da7ec','#3987e5','#256abf','#1c5cab','#104281','#0d366b']   # sequential 100..700
RED_LIGHT, RED = '#f6c9c8', '#b73535'
cmap = LinearSegmentedColormap.from_list('gainloss', [(0.0, RED), (0.35, RED_LIGHT), (0.5, '#f0efec')] + [(0.5 + 0.5*(i+1)/len(BLUE), c) for i, c in enumerate(BLUE)])
norm = TwoSlopeNorm(vcenter=1.0, vmin=0.80, vmax=2.0)

PANELS = [('llama', 8, 2048, 'Llama-3.1-8B (dense GQA)'), ('llama', 32, 8192, 'Llama-3.1-8B (dense GQA)'),
          ('llama2', 8, 2048, 'Llama-2-7B (dense MHA)'), ('granite', 32, 8192, 'granite-4.0-h-tiny (SSM hybrid)')]
C_MB = np.logspace(math.log10(64), math.log10(32768), 60)
BW = np.logspace(0, math.log10(64), 60)
DEVICE = [('C3', 278, 15.0), ('C2', 422, 15.0), ('C1', 590, 15.0)]
THERMAL = [(5.0, '0.5 pJ/b, 20 W'), (12.5, '0.5 pJ/b, 50 W'), (25.0, '0.1 pJ/b, 20 W')]

plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 8,
                     'svg.fonttype': 'none', 'axes.edgecolor': '#c3c2b7', 'axes.labelcolor': INK2, 'xtick.color': MUTED, 'ytick.color': MUTED,
                     'text.color': INK})
fig, axes = plt.subplots(1, 4, figsize=(13.6, 4.1), sharey=True, facecolor=SURF)
fig.subplots_adjust(left=0.048, right=0.925, top=0.80, bottom=0.15, wspace=0.10)
last = None
for ax, (mk, B, N, label) in zip(axes, PANELS):
    Z = np.empty((len(BW), len(C_MB)))
    for j, c in enumerate(C_MB):
        for i, bw in enumerate(BW):
            Z[i, j] = S.evaluate_cal(mk, B, N, c*1e6, bw, 'G1')['speedup_cal']
    info = S.evaluate_cal(mk, B, N, 1e6, 8, 'G1'); ws_mb = info['WS_GB']*1000; bw_eff = info['BW_eff_TBs']; t0 = info['t0_ms']; base = info['base_ms_cal']
    ax.set_facecolor(SURF); ax.set_xscale('log'); ax.set_yscale('log')
    last = ax.pcolormesh(C_MB, BW, Z, cmap=cmap, norm=norm, shading='nearest', rasterized=True)
    cs = ax.contour(C_MB, BW, Z, levels=[1.05, 1.10, 1.25, 1.50], colors=INK, linewidths=0.7)
    ax.clabel(cs, fmt=lambda v: f'{v:.2f}x', fontsize=6.5, inline=True, colors=INK)
    ax.contour(C_MB, BW, Z, levels=[1.0], colors=[RED], linewidths=1.0)
    ax.axhline(bw_eff, color=INK2, lw=0.9); ax.text(66, bw_eff*1.08, f'HBM effective {bw_eff:.1f} TB/s', fontsize=6.5, color=INK2, va='bottom')
    for y, t in THERMAL:
        ax.axhline(y, color=MUTED, lw=0.6); ax.text(66, y*0.80, t, fontsize=5.8, color=MUTED, ha='left', va='top')
    if ws_mb <= C_MB[-1]:
        ax.axvline(ws_mb, color=INK2, lw=0.9); ax.text(ws_mb*0.90, 2.2, f'working set {ws_mb/1000:.0f} GB', rotation=90, fontsize=6.5, color=INK2, ha='right', va='bottom')
    for name, c, bw in DEVICE:
        ax.plot(c, bw, 'o', ms=6, mfc=INK, mec='white', mew=1.2, zorder=5)
    ax.text(278*0.9, 15*1.35, 'C3', fontsize=6.5, ha='right'); ax.text(422, 15*1.35, 'C2', fontsize=6.5, ha='center'); ax.text(590*1.1, 15*1.35, 'C1', fontsize=6.5, ha='left')
    ax.plot(2360, 15*1.6, 'o', ms=6, mfc='white', mec=INK, mew=1.2, zorder=5); ax.text(2360*1.12, 15*1.6, 'C1 x2 die x2 layer', fontsize=6, va='center')
    ax.set_title(f'{label}\nB={B}, N={N}  ·  base {base:.2f} ms = {t0:.2f} + traffic/{bw_eff:.1f}', fontsize=8, color=INK, loc='left')
    ax.set_xticks([64, 256, 1024, 4096, 16384]); ax.set_xticklabels(['64 MB', '256 MB', '1 GB', '4 GB', '16 GB'])
    ax.set_yticks([1, 2, 4, 8, 16, 32, 64]); ax.set_yticklabels(['1', '2', '4', '8', '16', '32', '64'])
    ax.minorticks_off(); ax.tick_params(length=2.5)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)
    ax.set_xlabel('3D SRAM tier capacity (per GPU)')
axes[0].set_ylabel('delivered bandwidth to compute [TB/s]')
cax = fig.add_axes([0.94, 0.15, 0.011, 0.65])
cb = fig.colorbar(last, cax=cax, ticks=[0.8, 0.9, 1.0, 1.25, 1.5, 1.75, 2.0])
cb.set_label('step-time speedup vs. B200 baseline (calibrated model)', color=INK2); cb.outline.set_visible(False); cb.ax.tick_params(color=MUTED, labelcolor=MUTED, length=2.5)
fig.suptitle('Generic on-package SRAM tier: capacity x delivered bandwidth -> decode step-time speedup\n(red = tier slower than effective HBM; black dots = n5a design points C3/C2/C1 at the device team\'s 15 TB/s read-only delivered bandwidth)',
             x=0.048, y=0.975, ha='left', va='top', fontsize=8.6, color=INK)
fig.text(0.048, 0.012, 'Model calculation on structural traffic constants; timing = per-model two-parameter fit to measured B200 decode medians (B=1/8/32, N=2048/8192, vLLM 0.28.0). '
         'Tier = object-agnostic ideal-capacity cache (fraction C/WS of every byte served). Not a measurement of fabricated 3D SRAM.', fontsize=6.2, color=MUTED)
out = os.path.join(ROOT, 'assets/figures/sram-capacity-bandwidth-map')
for suffix, kw in (('svg', {}), ('pdf', {}), ('png', {'dpi': 200})):
    fig.savefig(f'{out}.{suffix}', facecolor=SURF, **kw)
print('wrote', out + '.{svg,pdf,png}')
