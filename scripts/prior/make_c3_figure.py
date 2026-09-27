#!/usr/bin/env python3
"""Figure: how the load instruction decides whether the access-policy window and set-aside matter (diagnostics D2 + D3;
the file names keep the older c2/c3 labels).
Synthetic cyclic stream of 268 MiB (≈ SmolLM-135M B1 decode), window = first 127 MiB, 32 kernels per step.
Bars = measured DRAM reads saved per step against the same load type with no window (ncu); markers = the same
saving from the predictions frozen before measuring (v2, v3). Bars start at zero (no truncated axis).
Usage: python3 scripts/prior/make_c3_figure.py
"""
import json, os
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

MiB = 1 << 20
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#fcfcfb'
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Apple SD Gothic Neo', 'Helvetica', 'DejaVu Sans'],
                     'axes.unicode_minus': False, 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': MUTED, 'ytick.color': MUTED, 'text.color': INK})
GROUPS = [('c2', 0, '일반 로드\n(LDG, 기본 디스크립터)'), ('c3', 3, 'ld.global.cs\n(LDG.E.EF — cuBLAS gemv)'),
          ('c3', 1, 'createpolicy\nL2::evict_first'), ('c3', 2, 'createpolicy\nL2::evict_last')]
SETTINGS = [((127, 12, 0.4), 'set-aside 12 MiB'), ((127, 60, 0.4), 'set-aside 60 MiB')]
SHADE = [S1, S3]

def load(name):
    P = {json.dumps(r['run'], sort_keys=True): r['dram_bytes'] for r in json.load(open(f'assets/sweep/{name}_predictions_ampere.json'))['runs']}
    Q = {json.dumps(r['run'], sort_keys=True): r['v3'] for r in json.load(open('assets/sweep/c23_v3_predictions_ampere.json'))['sets'][name]}
    out = {}
    for l in open(f'assets/sweep/{name}_measured_ampere.jsonl'):
        m = json.loads(l)
        if 'counters' not in m: continue
        r = m['run']; k = json.dumps(r, sort_keys=True)
        out[(r.get('hint', 0), r['layers'], r['window'], r['setaside'], r['hitratio'])] = (
            m['counters']['dram_read_per_step'] / MiB, P[k]['v2'] / MiB, Q[k] / MiB)
    return out

if __name__ == '__main__':
    D = {'c2': load('c2'), 'c3': load('c3')}
    fig, ax = plt.subplots(figsize=(8.6, 3.8), facecolor=SURF); ax.set_facecolor(SURF)
    bw = 0.3
    for g, (name, hint, label) in enumerate(GROUPS):
        b_meas, b_v2, b_v3 = D[name][(hint, 32, 0, 0, 0.0)]
        for j, ((w, s_, r), _) in enumerate(SETTINGS):
            meas, v2, v3 = D[name][(hint, 32, w, s_, r)]
            x = g + (j - 0.5) * (bw + 0.04)
            saved = max(b_meas - meas, 0.0)
            ax.bar(x, saved, width=bw, color=SHADE[j], edgecolor=SURF, linewidth=1)
            ax.plot(x, b_v2 - v2, marker='_', markersize=15, markeredgewidth=2.4, color=INK2, zorder=3)
            ax.plot(x, b_v3 - v3, marker='o', markersize=6, markerfacecolor=SURF, markeredgecolor=S2, markeredgewidth=1.8, zorder=4)
            ax.text(x, -2.2, f'{saved:.0f}', ha='center', va='top', fontsize=8, color=INK2)
    ax.set_xticks(range(len(GROUPS))); ax.set_xticklabels([g[2] for g in GROUPS], fontsize=8.2)
    ax.set_ylim(0, 62); ax.set_ylabel('창 없음 대비 줄어든 DRAM 읽기 (MiB/스텝)')
    ax.tick_params(axis='x', pad=14)
    ax.grid(axis='y', color=GRID, linewidth=0.6); ax.set_axisbelow(True)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    h = [Patch(color=SHADE[j], label=f'실측, 창 127 MiB r 0.4, {SETTINGS[j][1]}') for j in range(2)]
    h += [Line2D([], [], marker='_', linestyle='', markersize=12, markeredgewidth=2.2, color=INK2, label='v2 예측 (측정 전 고정)'),
          Line2D([], [], marker='o', linestyle='', markersize=6, markerfacecolor=SURF, markeredgecolor=S2, markeredgewidth=1.8,
                 label='v3 예측 (측정 전 고정)')]
    ax.legend(handles=h, loc='upper left', bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=8)
    ax.set_title('로드 명령이 창·set-aside 의 효과를 정한다 (합성 268 MiB 순환 ≈ SmolLM-135M 디코드, 커널 32 개)',
                 loc='left', fontsize=9.5, color=INK)
    os.makedirs('assets/figures', exist_ok=True)
    for ext in ('png', 'pdf'):
        fig.savefig(f'assets/figures/c3-load-hint.{ext}', dpi=200, bbox_inches='tight', facecolor=SURF)
    print('wrote assets/figures/c3-load-hint.{png,pdf}')
