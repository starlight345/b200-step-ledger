#!/usr/bin/env python3
"""Figure: the three-link hierarchy and the modeling-abstraction ladder (2026-09-20).

Panel A  where a 3D SRAM tier sits in a B200-class hierarchy: capacity vs bandwidth,
         with the HBM effective-bandwidth line that a tier must clear to be worth anything.
Panel B  what each rung of modeling refinement does to the predicted speedup for the
         largest buildable design point (C2, 2 layers, 4.22 GB).
Model calculation. Only the fixed term and HBM effective bandwidth come from measurement.
"""
import os, sys
import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
sys.path.insert(0, os.path.dirname(__file__))
import hierarchy_model as H
import sram_capacity_bandwidth_sweep as S

ROOT = os.path.join(os.path.dirname(__file__), '..')
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
BLUE, ORANGE, RED, GRAYFILL = '#2a78d6', '#eb6834', '#d03b3b', '#f0efec'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,'xtick.color':MUTED,
                     'ytick.color':MUTED,'text.color':INK})
fig = plt.figure(figsize=(12.4, 4.5), facecolor=SURF)
gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.15], left=0.055, right=0.985, top=0.785, bottom=0.155, wspace=0.24)

# ---------------- Panel A: hierarchy ----------------
ax = fig.add_subplot(gs[0, 0]); ax.set_facecolor(SURF); ax.set_xscale('log')
bw_hbm_eff = S.CAL['llama']['BW_eff_TBs']
ax.add_patch(Rectangle((1390, 5.0), 4220-1390, 15.0-5.0, facecolor=BLUE, alpha=0.16, edgecolor=BLUE, lw=1.2, zorder=2))
ax.text(2420, 15.6, '3D SRAM tier', fontsize=9, color=BLUE, ha='center', fontweight='bold')
ax.text(2420, 10.2, '1.39–4.22 GB\n5–15 TB/s\n(derate anchored\nto H100, not B200)', fontsize=7.0, color=INK2, ha='center', va='center')
ax.plot(126, 19.0, 'o', ms=9, mfc=INK, mec='white', mew=1.4, zorder=5)
ax.errorbar(126, 19.0, yerr=[[2.2],[2.0]], color=INK, lw=1.1, capsize=3, zorder=4)
ax.text(126, 22.6, 'L2  126 MB\n16.8–21 TB/s', fontsize=7.5, color=INK, ha='center', va='bottom')
ax.plot(180000, bw_hbm_eff, 'o', ms=9, mfc=INK, mec='white', mew=1.4, zorder=5)
ax.text(180000, bw_hbm_eff+0.7, f'HBM  180 GB\n{bw_hbm_eff:.1f} TB/s delivered', fontsize=7.5, color=INK, ha='center', va='bottom')
ax.plot([180000], [8.0], marker='_', ms=11, color=MUTED, mew=1.4, zorder=4)
ax.text(180000, 3.4, '8 TB/s pin spec\n(HBM-to-L2, not\na compute rate)', fontsize=6.4, color=MUTED, ha='center', va='center')
ax.axhline(bw_hbm_eff, color=RED, lw=1.3, zorder=3)
ax.text(90, bw_hbm_eff-0.55, f'what compute actually receives from HBM: {bw_hbm_eff:.1f} TB/s', fontsize=7.4, color=RED, va='top')
ax.fill_between([80, 400000], 0, bw_hbm_eff, color=RED, alpha=0.055, zorder=1)
ax.text(90, 1.5, 'a tier below this line costs\nmore time than it saves', fontsize=7.2, color=RED, va='bottom')
ax.annotate('', xy=(1390, 4.6), xytext=(126, 4.6), arrowprops=dict(arrowstyle='<->', color=MUTED, lw=0.9))
ax.text(420, 3.9, '11× capacity gap', fontsize=7.2, color=MUTED, ha='center')
ax.set_xlim(80, 400000); ax.set_ylim(0, 24)
ax.set_xticks([126, 1000, 10000, 180000]); ax.set_xticklabels(['126 MB','1 GB','10 GB','180 GB'])
ax.set_yticks([0, 5, 6.4, 10, 15, 20]); ax.set_yticklabels(['0','5','6.4','10','15','20'])
ax.set_xlabel('capacity'); ax.set_ylabel('effective rate delivered to compute [TB/s]')
ax.set_title('A  Where the tier sits', fontsize=9.5, loc='left', color=INK, pad=8)
ax.minorticks_off(); ax.tick_params(length=2.5)
for s_ in ('top','right'): ax.spines[s_].set_visible(False)
ax.grid(axis='y', color=GRID, lw=0.6, zorder=0)

# ---------------- Panel B: abstraction ladder ----------------
ax2 = fig.add_subplot(gs[0, 1]); ax2.set_facecolor(SURF)
L = H.ladder('llama', 8, 2048, 4220*1e6, 15.0)
# Every rung below M0 is drawn as a range from the serial-sum bound (tier time adds) to the
# overlapped bound (tier time hides under HBM). The cache rungs use the device table floor
# 3.8/15 for r < 0.6, which by monotonicity is an UPPER bound on a demand cache's bandwidth.
LB = H.ladder_bounds('llama', 8, 2048, 4220*1e6, 15.0)   # canon: design_point_axes.read_delivery_cap_TBs (slack_r1 scenario; 19 = via-L2 fabric cap)
rungs = [('M0  capacity only', (LB['M0'], LB['M0']), 'traffic cut = time cut'),
         ('M1  + fixed term, tier BW', LB['M1'], f"{L['t0_ms']:.2f} ms is not traffic"),
         ('M2  + L2-to-SM ceiling', LB['M2'], 'no bind below 19 TB/s'),
         ('M3  pinned store', LB['M3_pinned'], 'r = 1.0, so 15 TB/s'),
         ('M3  demand-filled cache', LB['M3_cache_floor'], 'if Slack BW(0.6) = 3.8 holds'),
         ('M4  cache + real LRU', LB['M4_LRU_floor'], 'zero hits, fills only')]
y = np.arange(len(rungs))[::-1]
ax2.axvline(1.0, color=AXIS, lw=1.1, zorder=2)
for yy, (lbl, (ser, ovl), note) in zip(y, rungs):
    good = min(ser, ovl) >= 1.0
    col = BLUE if good else RED
    lo, hi = min(ser, ovl), max(ser, ovl)
    if abs(hi-lo) < 1e-6:
        ax2.barh(yy, hi-1.0, left=1.0, height=0.52, color=col, zorder=3)
        ax2.text(hi+0.012, yy, f'{hi:.3f}x', fontsize=8.5, va='center', ha='left', color=INK, fontweight='bold')
    elif good:
        ax2.barh(yy, lo-1.0, left=1.0, height=0.52, color=col, zorder=3)          # serial (conservative) solid
        ax2.barh(yy, hi-lo, left=lo, height=0.52, color=col, alpha=0.35, zorder=3)  # to overlapped
        ax2.text(hi+0.012, yy, f'{lo:.3f}-{hi:.3f}x', fontsize=8.5, va='center', ha='left', color=INK, fontweight='bold')
    else:
        ax2.barh(yy, hi-1.0, left=1.0, height=0.52, color=col, zorder=3)          # overlapped (least bad) solid
        ax2.barh(yy, lo-hi, left=hi, height=0.52, color=col, alpha=0.35, zorder=3)  # down to serial
        ax2.text(lo-0.012, yy, f'{lo:.2f}-{hi:.2f}x', fontsize=8.5, va='center', ha='right', color=INK, fontweight='bold')
    ax2.text(0.32, yy+0.30, note, fontsize=7, color=MUTED, va='bottom')
ax2.set_yticks(y); ax2.set_yticklabels([r[0] for r in rungs], fontsize=8.2, color=INK)
ax2.set_xlim(0.30, 1.62); ax2.set_ylim(-0.95, 5.65); ax2.set_xticks([0.5, 0.75, 1.0, 1.25, 1.5]); ax2.set_xticklabels(['0.50','0.75','1.00','1.25','1.50'])
ax2.set_xlabel('predicted decode step-time speedup vs. B200 baseline')
ax2.set_title('B  What each rung of modeling refinement does', fontsize=9.5, loc='left', color=INK, pad=8)
ax2.tick_params(length=2.5)
for s_ in ('top','right','left'): ax2.spines[s_].set_visible(False)
ax2.grid(axis='x', color=GRID, lw=0.6, zorder=0)
m0, (m1s, m1o) = LB['M0'], LB['M1']
ax2.text(1.02, y[0]-0.46, f'M0->M1 splits: fixed 1.85 ms term {m0:.3f}->{m1o:.3f} ({(m1o-m0)*100:+.0f}%p);\nfinite tier service {m1o:.3f}->{m1s:.3f} ({(m1s-m1o)*100:+.0f}%p, serial bound)', fontsize=6.9, color=ORANGE, va='center')
ax2.text(1.02, y[4]-0.02, 'harmful iff mixed-traffic BW < HBM 6.4;\nserial bound needs only the deck (27.7 > 17.7)', fontsize=7, color=RED, va='center')
ax2.text(1.49, -0.72, 'bars: solid = serial-sum bound, faint = overlapped bound', fontsize=6.8, color=MUTED, va='center', ha='right')

fig.suptitle('A 3D SRAM tier on a B200-class GPU: C2, 2 layers, 4.22 GB (geometric upper bound: full 800 mm² placement per layer per die) on Llama-3.1-8B decode, B=8, N=2048',
             x=0.055, y=0.972, ha='left', fontsize=9.6, color=INK)
fig.text(0.055, 0.912, 'All three rates are bytes a kernel consumes per unit time, not link pin rates. HBM: logical bytes / measured B200 decode step time, fitted slope over four anchors.', fontsize=7.0, color=MUTED, ha='left')
fig.text(0.055, 0.878, 'L2: Vulkan compute-shader benchmark, 21 TB/s within a partition and 16.8 across. 3D: device-team deck gives 17.7 read-oriented (3.37x derate calibrated on H100 L2); the read/fill mix table is from a Slack reply, not the deck.', fontsize=7.0, color=MUTED, ha='left')
fig.text(0.055, 0.040, 'Model calculation, not a measurement. BW(r) = 15 / 9.4 / 3.8 at r = 1.0 / 0.8 / 0.6 comes from a device-team Slack reply (2026-09-20), not the audited deck; its derivation is unconfirmed.', fontsize=6.8, color=MUTED)
fig.text(0.055, 0.012, 'The cache rungs therefore hold only if that table holds: the serial bound (solid) needs no such table, the overlapped bound (faint) rests on BW(0.6) = 3.8 < 6.4. B200 L2 is not a counterexample: its 19 TB/s exceeds HBM.', fontsize=6.8, color=MUTED)
out = os.path.join(ROOT, 'assets/figures/sram-hierarchy-ladder')
for suf, kw in (('svg', {}), ('pdf', {}), ('png', {'dpi': 200})):
    fig.savefig(f'{out}.{suf}', facecolor=SURF, **kw)
print('wrote', out + '.{svg,pdf,png}')
