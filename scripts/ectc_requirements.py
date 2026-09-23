#!/usr/bin/env python3
"""ECTC figure 3: the two numbers we need from the device/package team, and the one we don't.

(a) ADMISSIBILITY MAP. Given a power budget, the delivered-bandwidth ceiling of the tier
    is a function of exactly two unmeasured device quantities: E/bit and the stack's
    thermal time constant tau = R_th * C_th. Tell us those two and this map says whether
    the tier clears the HBM admission floor at all. This is the request to hand back.

(b) VERTICAL INTERCONNECT. Not a constraint, and worth saying so once so it stops being
    a reviewer question. Supplying 19 TB/s needs O(10^5) links; a reticle-sized face at
    hybrid-bond pitch offers O(10^8) sites. The cap is the RECEIVING fabric (L2->SM),
    an architecture number, not a bond pitch.
"""
import os, sys, math, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
sys.path.insert(0, os.path.dirname(__file__))
import ectc_thermal_model as M

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures'); os.makedirs(FIG, exist_ok=True)
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,
                     'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

P_BUDGET = 20.0
C_DP     = M.capacity_GB(800.0, 2)          # C2 2-layer, the realizable design point
D        = M.duty(C_DP)

fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.6, 4.8), facecolor=SURF)
fig.subplots_adjust(left=0.062, right=0.965, top=0.715, bottom=0.15, wspace=0.40)
for ax in (axL, axR): ax.set_facecolor(SURF)

# ---------------- (a) admissibility over (E/bit, tau)
E   = np.logspace(math.log10(0.03), math.log10(2.0), 260)
TAU = np.logspace(math.log10(3e-6), math.log10(1e-1), 260)
EE, TT = np.meshgrid(E, TAU)
PF  = np.vectorize(lambda t: M.pss_peak(D, t))(TT)
CAP = P_BUDGET / (8.0*EE) / PF                       # TB/s
cf = axL.contourf(EE, TT*1e6, CAP, levels=np.logspace(-1, 3.4, 40),
                  norm=LogNorm(vmin=0.1, vmax=2500), cmap='RdYlGn', zorder=1)
for lvl, col, lw, lab in ((M.BW_HBM, INK, 2.2, f'HBM {M.BW_HBM:.2f} TB/s'), (M.B_R, S1, 1.8, f'fabric {M.B_R:.0f} TB/s')):
    cs = axL.contour(EE, TT*1e6, CAP, levels=[lvl], colors=[col], linewidths=lw, zorder=5)
    axL.clabel(cs, fmt={lvl: lab}, fontsize=7.4, inline=True)
axL.axhline(M.burst_s(C_DP)*1e6, color=INK2, lw=0.9, ls=':', zorder=4)
axL.text(0.032, M.burst_s(C_DP)*1e6*1.16, f'burst {M.burst_s(C_DP)*1e6:.0f} us', fontsize=7.2, color=INK2, zorder=6)
axL.axhline(M.T_STEP*1e6, color=INK2, lw=0.9, ls=':', zorder=4)
axL.text(0.032, M.T_STEP*1e6*1.16, f'step {M.T_STEP*1e6:.0f} us', fontsize=7.2, color=INK2, zorder=6)
axL.plot([0.5],[50], marker='o', ms=8, mfc='white', mec=RED, mew=2.0, zorder=7)
axL.annotate('0.5 pJ/bit with a fast stack:\nthe steady-state verdict, 5 TB/s.\nthis is the only corner that kills it',
             xy=(0.5,50), xytext=(0.145,7.5), fontsize=7.2, color=RED, ha='left',
             arrowprops=dict(arrowstyle='-', color=RED, lw=0.9, shrinkA=2, shrinkB=5), zorder=8)
axL.plot([0.5],[3392], marker='o', ms=8, mfc='white', mec=S1, mew=2.0, zorder=7)
axL.annotate('same 0.5 pJ/bit, tau of a 5 um\n2-layer stack: 68 TB/s, fabric-bound',
             xy=(0.5,3392), xytext=(0.115,26000), fontsize=7.2, color=S1, ha='left',
             arrowprops=dict(arrowstyle='-', color=S1, lw=0.9, shrinkA=2, shrinkB=5), zorder=8)
axL.set_xscale('log'); axL.set_yscale('log')
axL.set_xlabel('E/bit  [pJ/bit]      (both axes are unmeasured device quantities)')
axL.set_ylabel('stack thermal time constant  tau = R_th * C_th  [us]')
axL.set_title(f'(a)  two numbers decide the whole paper.\n{P_BUDGET:.0f} W budget, duty {D*100:.1f}% (C2 2-layer, 4.22 GB)',
              fontsize=9.2, color=INK, loc='left', pad=8)
cb = fig.colorbar(cf, ax=axL, pad=0.018, fraction=0.045,
                  ticks=[0.1, 1, M.BW_HBM, M.B_R, 100, 1000])
cb.set_label('delivered read BW ceiling  [TB/s]', fontsize=7.8, color=INK2, labelpad=2)
cb.ax.set_yticklabels(['0.1', '1', '6.4', '19', '100', '1000'])
cb.ax.tick_params(labelsize=7.2, colors=MUTED); cb.outline.set_edgecolor(AXIS)

# ---------------- (b) vertical interconnect is not the constraint
PITCH = np.logspace(math.log10(0.4), math.log10(60), 200)
AREA  = 800.0
avail = (1e6/PITCH**2)*AREA
need_bits = M.B_R*1e12*8
n_lo, n_hi = need_bits/(2.0*1e9), need_bits/(0.5*1e9)      # 2 Gb/s .. 0.5 Gb/s per link
axR.fill_between(PITCH, avail, 1e10, color=S3, alpha=0.10, zorder=1)
axR.plot(PITCH, avail, color=INK, lw=2.2, zorder=5)
axR.text(0.45, 4.6e9, f'sites available on a {AREA:.0f} mm2 face', fontsize=7.6, color=INK, va='top', zorder=6)
axR.axhspan(n_lo, n_hi, color=S2, alpha=0.22, zorder=3)
axR.text(0.46, n_hi*1.5, f'{M.B_R:.0f} TB/s needs {n_lo:,.0f} - {n_hi:,.0f} links\n(2 - 0.5 Gb/s per link)',
         fontsize=7.5, color=S2, va='bottom', zorder=6)
for px, lab in ((1.0,'hybrid bond'), (9.0,'micro-bump'), (40.0,'C4')):
    a = (1e6/px**2)*AREA
    axR.plot([px],[a], marker='o', ms=7, mfc='white', mec=INK, mew=1.7, zorder=7)
    axR.text(px*1.25, a*0.30, f'{lab}  {px:g} um\n{need_bits/1e9/a*100:.3g}% of sites used',
             fontsize=7.2, color=INK2, ha='left', va='top', zorder=6)
axR.set_xscale('log'); axR.set_yscale('log'); axR.set_xlim(0.4, 160); axR.set_ylim(2e4, 8e9)
axR.set_xlabel('vertical connection pitch  [um]')
axR.set_ylabel('vertical connections', labelpad=2)
axR.set_title('(b)  the vertical interface is not a constraint: three orders of margin.\n'
              'the cap is the RECEIVING fabric, which is an architecture number',
              fontsize=9.2, color=INK, loc='left', pad=8)
axR.grid(True, which='both', color=GRID, lw=0.5, zorder=0)

fig.text(0.062, 0.955, 'What to ask the device team for -- and what to stop asking for',
         fontsize=12.4, color=INK, va='top')
fig.text(0.062, 0.900, 'Left: nothing else in the chain is uncertain enough to matter. Capacity is geometry, read BW is fabric-bound, write BW closed at '
         '1.14% (Gate 5).\nGive us E/bit and the stack cross-section and the paper has a point on it instead of a map.',
         fontsize=7.8, color=INK2, va='top', linespacing=1.5)
for ext in ('png','svg'):
    fig.savefig(os.path.join(FIG, f'ectc-requirements.{ext}'), dpi=220, facecolor=SURF)

print(f'design point C2 2-layer {C_DP:.2f} GB, duty {D*100:.2f}%, burst {M.burst_s(C_DP)*1e6:.0f} us')
print(f'links for {M.B_R:.0f} TB/s @1 Gb/s = {need_bits/1e9:,.0f}; '
      f'hybrid-bond 1 um over {AREA:.0f} mm2 = {1e6*AREA:,.0f} sites '
      f'({need_bits/1e9/(1e6*AREA)*100:.4f}% used)')
print('wrote assets/figures/ectc-requirements.{png,svg}')
