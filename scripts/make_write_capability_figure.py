#!/usr/bin/env python3
"""Figure: how much write/fill capability a demand-filled 3D SRAM cache needs (2026-09-21).
x = beta = B_W / B_R (write capability relative to the deck's read projection 17.7 TB/s)
y = predicted decode step-time speedup, C2 2-layer 4.22 GB, Llama-3.1-8B B=8 N=2048.
Series: pinned store (reads only), tag-first demand cache, parallel-tag/data demand cache.
Solid = overlapped bound, faint = serial bound. Markers: Slack-implied beta band, L2's measured floor."""
import os, sys, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
import cache_write_capability as W
ROOT = os.path.join(os.path.dirname(__file__), '..')
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'    # categorical slots 1-3, status critical
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})
mk,B,N,C = 'llama',8,2048,4220*1e6
B_R, PEAK = W.read_projection_TBs('C2', 800, 2, 2)          # fabric-bound 19.0 at the GB-scale point
bh = W.S.CAL[mk]['BW_eff_TBs']
h = min(1.0, C/W.S.workload(mk,B,N)[1])
betas = np.linspace(0.05, 1.0, 96)
fig, ax = plt.subplots(figsize=(8.6, 4.6), facecolor=SURF); fig.subplots_adjust(left=0.085, right=0.975, top=0.80, bottom=0.165)
ax.set_facecolor(SURF)
for org, col, name in (('tag-first', S2, 'demand cache, tag-first (r = h)'), ('parallel', S3, 'demand cache, tag/data parallel')):
    ovl = [W.step(mk,B,N,C,b,B_R,org,'overlapped')[0] for b in betas]
    ser = [W.step(mk,B,N,C,b,B_R,org,'serial')[0] for b in betas]
    ax.plot(betas, ovl, color=col, lw=2.0, label=name, zorder=4)
    ax.plot(betas, ser, color=col, lw=1.2, alpha=0.35, zorder=3)
pin_o = W.step(mk,B,N,C,1.0,B_R,'tag-first','overlapped',mode='pinned')[0]
pin_s = W.step(mk,B,N,C,1.0,B_R,'tag-first','serial',mode='pinned')[0]
ax.axhline(pin_o, color=S1, lw=2.0, zorder=4, label='pinned resident store (reads only)')
ax.axhline(pin_s, color=S1, lw=1.2, alpha=0.35, zorder=3)
ax.axhline(1.0, color=AXIS, lw=1.0, zorder=2)
# markers
ib = W.implied_beta_from_slack(); lo, hi = min(ib.values()), max(ib.values())
ax.axvspan(lo, hi, color=RED, alpha=0.10, zorder=1)
ax.text((lo+hi)/2, 0.46, f'Slack table implies\nbeta {lo:.2f}-{hi:.2f}\n(unconfirmed)', fontsize=7.2, color=RED, ha='center', va='bottom')
be_t = W.breakeven_beta(mk,B,N,C,B_R,'tag-first','overlapped'); be_p = W.breakeven_beta(mk,B,N,C,B_R,'parallel','overlapped')
bc_t = W.beta_ceiling(h, B_R, 'tag-first', bh); bc_p = W.beta_ceiling(h, B_R, 'parallel', bh)
for be, bc, col, yy in ((be_t, bc_t, S2, 1.225), (be_p, bc_p, S3, 1.195)):
    ax.plot([be], [1.0], marker='o', ms=7, mfc=col, mec='white', mew=1.2, zorder=6)          # break-even: speedup = 1
    ax.plot([bc], [pin_o], marker='s', ms=6.5, mfc='white', mec=col, mew=1.6, zorder=6)     # ceiling: reaches pinned
    ax.text(be, yy, f'break-even {be:.2f}\n(speedup = 1)', fontsize=7.0, color=col, ha='center', va='bottom')
    ax.text(bc, pin_o-0.025, f'reaches pinned\nceiling at {bc:.2f}', fontsize=7.0, color=col, ha='center', va='top')
bl2 = 6.4/19.0
ax.axvline(bl2, color=INK2, lw=0.9, zorder=2)
ax.text(bl2+0.012, 0.44, f'B200 L2 under the same test:\nbeta_L2 >= {bl2:.2f}, an inferred lower bound\n(6.4 achieved / 19 read, assuming\nnear-zero L2 hit on streaming traffic)', fontsize=6.9, color=INK2, va='bottom')
ax.text(0.80, pin_o+0.012, f'pinned {pin_s:.3f}-{pin_o:.3f}x', fontsize=7.6, color=S1, va='bottom')
ax.set_xlim(0.05, 1.0); ax.set_ylim(0.40, 1.32)
ax.set_xlabel(f'write / fill capability of the 3D tier relative to its read delivery B_R = {B_R:.0f} TB/s   (beta = B_W / B_R)')
ax.set_ylabel('predicted decode step-time speedup')
ax.set_title('How much write capability makes a demand-filled 3D SRAM cache viable?  C2 2-layer 4.22 GB (800 mm² full-placement upper bound), Llama-3.1-8B B=8 N=2048', fontsize=9.0, loc='left', pad=8)
for s_ in ('top','right'): ax.spines[s_].set_visible(False)
ax.grid(axis='y', color=GRID, lw=0.6, zorder=0); ax.tick_params(length=2.5)
leg = ax.legend(loc='lower right', fontsize=7.6, frameon=False)
fig.text(0.085, 0.905, f'Read delivery at this point: array peak {PEAK:.0f} TB/s (40,353 macros x 22.4 GB/s) far exceeds the fabric, so B_R = min(array/3.37, L2-to-SM) = {B_R:.0f} TB/s. The deck\'s 17.7 was the 320 mm² array figure.', fontsize=6.8, color=MUTED)
fig.text(0.085, 0.875, 'Everything on the x axis is an architectural assumption we sweep. Solid = overlapped bound, faint = serial bound. Shared-port service T = R/B_R + W/(beta B_R). HBM effective 6.4 TB/s from the measured B200 fit.', fontsize=6.9, color=MUTED)
fig.text(0.085, 0.035, 'Model calculation, not a measurement. Tag-first: hit reads, miss fills (R = hD, W = (1-h)D). Parallel: every access reads the data array (R = D).', fontsize=6.8, color=MUTED)
fig.text(0.085, 0.010, 'The serial bound never breaks even for beta <= 1. Slack-implied beta re-expresses the 2026-09-20 reply (r = 0.8 -> 9.4, r = 0.6 -> 3.8 TB/s) in this model; it is not a deck value.', fontsize=6.8, color=MUTED)
out = os.path.join(ROOT, 'assets/figures/sram-write-capability')
for suf, kw in (('svg',{}),('pdf',{}),('png',{'dpi':200})): fig.savefig(f'{out}.{suf}', facecolor=SURF, **kw)
print('wrote', out+'.{svg,pdf,png}')
