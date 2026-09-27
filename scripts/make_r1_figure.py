#!/usr/bin/env python3
"""R1 figures — actual prior-work tools vs our model on real LLM decode (DRAM bytes per step).
  1. predicted vs measured, one panel per predictor (identity line = perfect; a policy-blind tool
     collapses to one vertical line per workload)
  2. hitRatio response at one (workload, set-aside): measured vs every predictor
Usage: python3 make_r1_figure.py assets/sweep/r1_predictions_ampere.json assets/sweep/r1_measured_ampere.jsonl
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
PANELS = [('llmcompass', 'LLMCompass (실제 도구)'), ('genz', 'GenZ (실제 도구)'),
          ('memexplorer', 'MemExplorer 식 (4)'), ('gtsim_l2', 'GPU-Tile-Sim L2 (LRU)'),
          ('ours_v1', '우리 v1 (문서 의미)'), ('ours_v2', '우리 v2 (세트 단위)')]
WL = {'SmolLM-135M/B1': '135M B1', 'SmolLM-135M/B8': '135M B8', 'SmolLM-360M/B1': '360M B1'}

def load(pp, mp):
    P = {json.dumps(r['run'], sort_keys=True): r for r in json.load(open(pp))['runs']}
    out = []
    for l in open(mp):
        m = json.loads(l); p = P.get(json.dumps(m['run'], sort_keys=True))
        if p and 'counters' in m: out.append((m['run'], p, m))
    return out

def wl(run): return f"{run['model']}/B{run['batch']}"

if __name__ == '__main__':
    rows = load(sys.argv[1], sys.argv[2])
    out = Path('assets/figures'); out.mkdir(parents=True, exist_ok=True)
    meas = lambda m: m['counters']['dram_read_per_step'] / MiB

    # --- 1. predicted - measured per predictor, relative to the workload's logical step ---------------
    # (the three workloads differ 2.6x in size, so plot the error, not the raw bytes)
    fig, axes = plt.subplots(1, 6, figsize=(13.6, 3.3), facecolor=SURF, sharey=True)
    order = list(WL)
    for ax, (k, name) in zip(axes, PANELS):
        ax.set_facecolor(SURF)
        errs = []
        for j, w in enumerate(order):
            rs = [t for t in rows if wl(t[0]) == w]
            e = [(t[1]['dram_read_bytes'][k] / MiB - meas(t[2])) for t in rs]; errs += e
            xs = [j + (i % 9 - 4) * 0.045 for i in range(len(e))]
            ax.scatter(xs, e, s=10, color=S1 if k == 'ours_v2' else INK2, alpha=.7, lw=0, zorder=3)
        ax.axhline(0, color=MUTED, lw=1, ls=(0, (4, 3)), zorder=1)
        mae = st.mean(abs(x) for x in errs)
        ax.set_title(f'{name}\n평균 오차 {mae:.1f} MiB', fontsize=9, color=INK, loc='left')
        ax.set_xticks(range(len(order))); ax.set_xticklabels([WL[w] for w in order], fontsize=8)
        ax.set_xlim(-.6, len(order) - .4)
        ax.grid(axis='y', color=GRID, lw=.6); ax.set_axisbelow(True)
        for sp in ('top', 'right'): ax.spines[sp].set_visible(False)
    axes[0].set_ylabel('예측 − 실측 DRAM  [MiB / step]')
    fig.tight_layout()
    fig.savefig(out / 'r1-prediction-error.png', dpi=200, facecolor=SURF)

    # --- 2. hitRatio response: the (workload, set-aside) with the widest measured swing --------------
    groups = {}
    for run, p, m in rows:
        if run['window'] == 127: groups.setdefault((wl(run), run['setaside']), []).append((run, p, m))
    g, rs = max(groups.items(), key=lambda kv: max(meas(t[2]) for t in kv[1]) - min(meas(t[2]) for t in kv[1]))
    rs.sort(key=lambda t: t[0]['hitratio'])
    base = [t for t in rows if wl(t[0]) == g[0] and t[0]['window'] == 0 and t[0]['setaside'] == 0][0]
    x = [t[0]['hitratio'] for t in rs]
    fig, ax = plt.subplots(figsize=(6.8, 3.8), facecolor=SURF); ax.set_facecolor(SURF)
    ax.plot(x, [meas(t[2]) for t in rs], color=INK, lw=2.2, marker='o', ms=6, label='실측', zorder=6)
    ax.plot(x, [t[1]['dram_read_bytes']['ours_v2'] / MiB for t in rs], color=S1, lw=2, marker='o', ms=4.5,
            label='우리 v2', zorder=5)
    ax.plot(x, [t[1]['dram_read_bytes']['ours_v1'] / MiB for t in rs], color=S2, lw=2, marker='o', ms=4.5,
            label='우리 v1', zorder=4)
    flat = [('llmcompass', 'LLMCompass'), ('genz', 'GenZ'), ('gtsim_l2', 'GPU-Tile-Sim'), ('memexplorer', 'MemExplorer')]
    for k, name in flat:
        y = rs[0][1]['dram_read_bytes'][k] / MiB
        ax.axhline(y, color=MUTED, lw=1, ls=(0, (2, 2)), zorder=2)
        ax.text(1.0, y, f' {name}', va='center', ha='left', fontsize=7.5, color=INK2, transform=ax.get_yaxis_transform())
    ax.axhline(meas(base[2]), color=INK, lw=1, ls=(0, (6, 3)), alpha=.5, zorder=2)
    ax.text(0.0, meas(base[2]), ' 정책 없음(실측)', va='bottom', fontsize=7.5, color=INK2)
    ax.axvline(g[1] / 127, color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.set_xlabel('hitRatio  (창 127 MiB)'); ax.set_ylabel('DRAM 읽기  [MiB / step]')
    ax.set_title(f'{WL[g[0]]}, set-aside {g[1]} MiB: 정책에 따른 실제 트래픽', fontsize=9.5, loc='left')
    ax.grid(color=GRID, lw=.6); ax.set_axisbelow(True)
    for sp in ('top', 'right'): ax.spines[sp].set_visible(False)
    ax.legend(frameon=False, fontsize=8.5, loc='lower left')
    fig.tight_layout(rect=(0, 0, .88, 1))
    fig.savefig(out / 'r1-hitratio-response.png', dpi=200, facecolor=SURF)
    print('wrote assets/figures/r1-prediction-error.png, r1-hitratio-response.png;', g)
