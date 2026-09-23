#!/usr/bin/env python3
"""V-2 figure: what the 1D model cannot see, and why it is still the right model here.

MAPDL 3D steady conduction on a repeating 4 mm unit cell of the stack, total tier power
held at the die-average density, concentrated into a square patch of side L. Adiabatic
lateral faces make it a periodic array of identical hotspots.

Two things come out. At L = full cell the 3D result reproduces the 1D solver to 1.4%,
which is the third independent check on it. As L shrinks the peak runs away as roughly
1/L^2 rather than the 1/L of classical spreading, because the bottleneck is not silicon
spreading but the 8 um low-k BEOL directly under the tier: until the heat has spread
laterally it must cross that layer through the patch area alone.

The workload closes the loop. Decode streams the whole resident weight set every step and
that set is spread over every macro, so the tier is close to uniformly active and the
left-hand end of this plot is the operating point. A workload that localises tier reads
would walk right and the low-k BEOL would dominate.
"""
import os, sys, math
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
import thermal_stack_solver as T

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures'); os.makedirs(FIG, exist_ok=True)
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':9,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,
                     'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

# MAPDL 3D steady results, assets/mapdl/hotspot_*.dat  [Ansys MAPDL 26.1]
CELL_UM = 4000.0
MAPDL = [(CELL_UM, 0.8476753), (1000.0, 6.220460),
         (500.0, 18.02689), (200.0, 96.93106), (100.0, 425.4633)]
T1D = 0.8363          # scripts/thermal_stack_solver.py, same stack, uniform

L  = np.array([m[0] for m in MAPDL])
Tp = np.array([m[1] for m in MAPDL])
frac = (L/CELL_UM)**2

fig, ax = plt.subplots(figsize=(7.8, 4.9), facecolor=SURF)
fig.subplots_adjust(left=0.10, right=0.975, top=0.775, bottom=0.14)
ax.set_facecolor(SURF); ax.set_xscale('log'); ax.set_yscale('log')
ax.grid(True, which='both', color=GRID, lw=0.5, zorder=0)

ax.axhspan(0.4, 10.0, color=S3, alpha=0.09, zorder=1)
ax.plot(frac*100, Tp, color=S2, lw=2.4, marker='o', ms=6, mfc='white', mec=S2, mew=1.7, zorder=5)
ax.plot([100], [T1D], marker='D', ms=9, mfc=S1, mec='white', mew=1.4, zorder=7)
ax.annotate('1D solver, uniform: %.3f K\n3D MAPDL, uniform: %.3f K\n-> agree to %.1f%%'
            % (T1D, Tp[0], abs(T1D-Tp[0])/Tp[0]*100),
            xy=(100, T1D), xytext=(0.073, 1.75), fontsize=8.0, color=S1, ha='left', va='top',
            arrowprops=dict(arrowstyle='-', color=S1, lw=1.0, shrinkA=3, shrinkB=6), zorder=8)

# 1/area reference slope anchored at the smallest patch
ref = Tp[-1]*(frac[-1]/frac)
ax.plot(frac*100, ref, color=MUTED, lw=1.1, ls=(0, (4, 2)), zorder=3)
ax.text(0.09, ref[-1]*0.42, 'slope $\\propto$ 1/area', fontsize=7.8, color=MUTED, ha='left')

for f, t, l in zip(frac, Tp, L):
    if l in (100.0, 500.0, 1000.0):
        ax.text(f*100*1.35, t, f'{l:.0f} $\\mu$m patch', fontsize=7.6, color=INK2, va='center')

ax.axhline(10.0, color=RED, lw=1.3, ls=(0, (4, 2)), zorder=6)
ax.text(150, 11.5, 'example 10 K headroom', fontsize=8.0, color=RED, ha='right', va='bottom')
ax.text(2.0, 0.46, 'decode operating point: the resident weight set is\nstreamed from every macro, so the tier is uniformly active',
        fontsize=8.0, color=S3, ha='left', va='bottom', zorder=7)

ax.set_xlim(0.05, 160); ax.set_ylim(0.4, 900)
ax.set_xlabel('fraction of the tier actually active during the burst  [%]      (same total watts)')
ax.set_ylabel('peak tier temperature rise  [K]')
fig.text(0.10, 0.965, 'The 1D model is right where this workload sits, and the low-k BEOL is what punishes leaving it',
         fontsize=11.2, color=INK, va='top')
fig.text(0.10, 0.902, 'Ansys MAPDL 26.1, 3D steady conduction, 4 mm repeating unit cell, adiabatic lateral faces (a periodic hotspot array).\n'
         'Total tier power held at the die-average density throughout, so only the concentration changes. Stack is the stated design study.',
         fontsize=7.9, color=INK2, va='top', linespacing=1.5)
for ext in ('png', 'svg', 'pdf'):
    fig.savefig(os.path.join(FIG, f'hotspot-spreading.{ext}'), dpi=260, facecolor=SURF)
print(f'uniform: 1D {T1D:.4f} K vs MAPDL 3D {Tp[0]:.4f} K -> {abs(T1D-Tp[0])/Tp[0]*100:.2f}%')
for f, t, l in zip(frac, Tp, L):
    print(f'  patch {l:>6.0f} um = {f*100:7.3f}% of the cell -> {t:9.3f} K  ({t/Tp[0]:6.1f}x uniform)')
print('wrote assets/figures/hotspot-spreading.{png,svg,pdf}')
