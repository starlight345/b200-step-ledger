#!/usr/bin/env python3
"""H1c (held-out) validation figures.
  1. predicted vs measured DRAM bytes per step, one panel per predictor (identity line = perfect)
  2. hitRatio response of one held-out group: measured vs the predictors
Usage: python3 make_h1c_figure.py assets/sweep/h1c_predictions_ampere.json assets/sweep/h1c_measured_ampere.jsonl
"""
import json, sys, statistics as st
from pathlib import Path
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

MiB = 1 << 20
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#fcfcfb'
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'          # validated categorical slots 1-3 (all-pairs safe)
plt.rcParams.update({'font.family': 'sans-serif',
                     'font.sans-serif': ['Apple SD Gothic Neo', 'Helvetica', 'DejaVu Sans'],
                     'axes.unicode_minus': False, 'font.size': 9, 'axes.edgecolor': GRID,
                     'axes.labelcolor': INK2, 'xtick.color': MUTED, 'ytick.color': MUTED, 'text.color': INK})
PANELS = [('capacity_only', '용량만 (MemExplorer식)'), ('fixed_lru', 'LRU 고정 (GPU-Tile-Sim식)'),
          ('cuda_policy', '우리 v1 (문서 의미만)'), ('v2', '우리 v2 (세트 단위)')]

def load(pp, mp):
    P = {json.dumps(r['run'], sort_keys=True): r for r in json.load(open(pp))['runs']}
    out = []
    for l in open(mp):
        m = json.loads(l); p = P.get(json.dumps(m['run'], sort_keys=True))
        if p and 'counters' in m: out.append((m['run'], p, m))
    return out

if __name__ == '__main__':
    rows = load(sys.argv[1], sys.argv[2])
    out = Path('assets/figures'); out.mkdir(parents=True, exist_ok=True)
    meas = [m['counters']['dram_read_per_step'] / MiB for _, _, m in rows]
    top = max(max(meas), max(p['dram_bytes'][k] / MiB for _, p, _ in rows for k, _ in PANELS)) * 1.04

    fig, axes = plt.subplots(1, 4, figsize=(12.4, 3.4), facecolor=SURF, sharex=True, sharey=True)
    for ax, (k, name) in zip(axes, PANELS):
        pred = [p['dram_bytes'][k] / MiB for _, p, _ in rows]
        mae = st.mean(abs(a - b) for a, b in zip(pred, meas))
        ax.set_facecolor(SURF)
        ax.plot([0, top], [0, top], color=MUTED, lw=1, ls=(0, (4, 3)), zorder=1)
        ax.scatter(pred, meas, s=22, color=S1 if k == 'v2' else INK2, alpha=.75, lw=0, zorder=3)
        ax.set_title(f'{name}\n오차 {mae:.1f} MiB', fontsize=9.5, color=INK, loc='left')
        ax.set_xlim(0, top); ax.set_ylim(0, top)
        ax.grid(color=GRID, lw=.6); ax.set_axisbelow(True)
        for sp in ('top', 'right'): ax.spines[sp].set_visible(False)
        ax.set_xlabel('예측 DRAM  [MiB / step]')
    axes[0].set_ylabel('실측 DRAM  [MiB / step]')
    fig.tight_layout()
    fig.savefig(out / 'h1c-predicted-vs-measured.png', dpi=200, facecolor=SURF)

    # --- hitRatio response of the held-out group with the widest measured swing ----------------------
    groups = {}
    for run, p, m in rows:
        if run['window'] > 0 and run['setaside'] > 0:
            g = (run['mode'], run.get('ws', run.get('hot')), run['setaside'])
            groups.setdefault(g, []).append((run, p, m))
    g, rs = max(groups.items(), key=lambda kv: max(t[2]['counters']['dram_read_per_step'] for t in kv[1])
                - min(t[2]['counters']['dram_read_per_step'] for t in kv[1]))
    rs.sort(key=lambda t: t[0]['hitratio'])
    x = [t[0]['hitratio'] for t in rs]
    fig, ax = plt.subplots(figsize=(6.4, 3.6), facecolor=SURF); ax.set_facecolor(SURF)
    ax.plot(x, [t[2]['counters']['dram_read_per_step'] / MiB for t in rs], color=INK, lw=2, marker='o', ms=6, label='실측', zorder=5)
    for k, name, c in (('v2', '우리 v2', S1), ('cuda_policy', '우리 v1', S2), ('fixed_lru', 'LRU 고정', S3)):
        ax.plot(x, [t[1]['dram_bytes'][k] / MiB for t in rs], color=c, lw=2, marker='o', ms=4.5, label=name, zorder=4)
    ax.axvline(g[2] / rs[0][0]['window'], color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(g[2] / rs[0][0]['window'], ax.get_ylim()[1], ' set-aside / 창', va='top', fontsize=8, color=INK2)
    ax.set_xlabel('hitRatio'); ax.set_ylabel('DRAM  [MiB / step]')
    size = f"ws={g[1]:g}" if g[0] == 'llm' else f"hot={g[1]:g}"
    ax.set_title(f'처음 보는 설정: {g[0]} {size} MiB, set-aside {g[2]:g} MiB', fontsize=9.5, loc='left')
    ax.grid(color=GRID, lw=.6); ax.set_axisbelow(True)
    for sp in ('top', 'right'): ax.spines[sp].set_visible(False)
    ax.legend(frameon=False, fontsize=8.5, loc='best')
    fig.tight_layout()
    fig.savefig(out / 'h1c-hitratio-response.png', dpi=200, facecolor=SURF)
    print('wrote assets/figures/h1c-predicted-vs-measured.png, h1c-hitratio-response.png;', g)
