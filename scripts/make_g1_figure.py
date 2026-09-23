#!/usr/bin/env python3
"""G-1 figure: the traffic-to-time coefficient is causal, and it is the hardware's bandwidth.

The project's speedups all rest on converting delivered bytes into time at a coefficient
B_eff. On B200 that coefficient (6.40 TB/s) is a regression across four (B, N) anchors,
which moves traffic, compute and launch overhead together and so has always been labelled
"causality not validated". This closes the structure on an available Blackwell part.

Two knobs change delivered bytes by different mechanisms:
  K1  context length at fixed batch -- weight traffic constant, KV traffic = B*N*kv_bytes,
      write traffic constant, so this isolates the READ path.
  K2  batch at fixed context -- same KV byte range reached a different way, but each added
      sequence also writes its new KV token, so this sits on the READ+WRITE path.

Both land on an independently measured bandwidth probe of the same GPU, and they land on
the mode each one should: K1 on read-only, K2 on copy. The coefficient is not a fitting
artefact; it is the memory path.
"""
import os, sys, json
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures')
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':9,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,
                     'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

K1 = json.load(open(os.path.join(ROOT,'assets','sweep','g1_llama8b_K1.json')))
K2 = json.load(open(os.path.join(ROOT,'assets','sweep','g1_llama8b_K2_batch.json')))
PROBE_READ, PROBE_COPY = 1.211, 1.105

fig, ax = plt.subplots(figsize=(7.9, 5.0), facecolor=SURF)
fig.subplots_adjust(left=0.098, right=0.975, top=0.775, bottom=0.135)
ax.set_facecolor(SURF); ax.grid(True, color=GRID, lw=0.5, zorder=0)

for d, col, mk, lab in ((K1, S1, 'o', 'K1  context length, batch fixed at 8'),
                        (K2, S2, 's', 'K2  batch, context fixed at 4096')):
    x = np.array([r['kv_GB'] for r in d['rows']]); y = np.array([r['step_ms'] for r in d['rows']])
    ax.plot(x, y, color=col, lw=0, marker=mk, ms=8, mfc='white', mec=col, mew=2.0, zorder=6)
    xs = np.linspace(0, 9.2, 50)
    ax.plot(xs, d['intercept_ms'] + d['slope_ms_per_GB']*xs, color=col, lw=2.0, zorder=5, label=lab)
    ax.text(6.3, d['intercept_ms'] + d['slope_ms_per_GB']*6.3 + (0.75 if col == S1 else -0.30),
            f"slope $\\rightarrow$ {d['B_eff_TBs']:.3f} TB/s,  $R^2$ = {d['r2']:.5f}",
            fontsize=8.2, color=col, ha='right', va='bottom' if col == S1 else 'top',
            rotation=13, rotation_mode='anchor', zorder=7)

ax.axhline(K1['intercept_ms'], color=MUTED, lw=1.0, ls=(0,(4,2)), zorder=3)
ax.text(0.12, K1['intercept_ms']-0.35, 'intercept = the N-independent weight traffic (15.01 GB/step) plus fixed cost',
        fontsize=7.8, color=MUTED, va='top')

box = ('independent bandwidth probe, same GPU\n'
       f'   read only            {PROBE_READ:.3f} TB/s\n'
       f'   copy (read+write)    {PROBE_COPY:.3f} TB/s\n\n'
       f'K1 lands on read-only to {abs(K1["B_eff_TBs"]-PROBE_READ)/PROBE_READ*100:.2f}%\n'
       f'K2 lands on copy to {abs(K2["B_eff_TBs"]-PROBE_COPY)/PROBE_COPY*100:.2f}%')
ax.text(0.12, 22.6, box, fontsize=8.0, color=INK, va='top', ha='left', zorder=8,
        bbox=dict(boxstyle='round,pad=0.5', fc='white', ec=AXIS, lw=0.9))

ax.set_xlim(0, 9.2); ax.set_ylim(14.6, 23.6)
ax.set_xlabel('KV bytes delivered per decode step  [GB]')
ax.set_ylabel('decode step time  [ms]')
ax.legend(frameon=False, fontsize=8.4, loc='lower right', bbox_to_anchor=(1.0, 0.02))
fig.text(0.098, 0.965, 'Delivered bytes convert to time at the hardware\'s bandwidth -- measured, not fitted',
         fontsize=11.6, color=INK, va='top')
fig.text(0.098, 0.905, 'Llama-3.1-8B, vLLM 0.10.2, RTX PRO 5000 Blackwell. Step time is extracted by differencing two generation lengths so\n'
         'prefill cancels; prefix caching is disabled, without which the cancellation is wrong and the slope implies 2.39 TB/s on a\n'
         'part that measures 1.21. The B200 coefficient 6.40 TB/s is the same quantity with that part\'s bandwidth substituted.',
         fontsize=7.9, color=INK2, va='top', linespacing=1.5)
for ext in ('png','svg','pdf'):
    fig.savefig(os.path.join(FIG, f'g1-causal.{ext}'), dpi=260, facecolor=SURF)
print(f"K1 {K1['B_eff_TBs']:.3f} vs read {PROBE_READ}; K2 {K2['B_eff_TBs']:.3f} vs copy {PROBE_COPY}")
print('wrote assets/figures/g1-causal.{png,svg,pdf}')
