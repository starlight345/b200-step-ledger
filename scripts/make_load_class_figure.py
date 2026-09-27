#!/usr/bin/env python3
"""Figure: three load classes decide what the access-policy window and the set-aside do (D3 + D3b).
Synthetic cyclic stream of 268 MiB as 32 kernels (≈ SmolLM-135M B1 decode), window = first 127 MiB, hitRatio 0.4.
Bars = measured DRAM reads saved per step against the same load type with no window (ncu), at set-aside 12 and 60 MiB.
Markers = the same saving predicted before measuring: v3 (priority only) and, for the D3b loads, v3_desc (the window reaches
only loads that carry the driver's default descriptor). Plain and ld.global.cs come from the D3b session (19:53, which
reproduced D2/D3 within 1 MiB); createpolicy evict_first / evict_last from D3 (02:50; no v3_desc prediction was frozen then).
Usage: python3 scripts/make_load_class_figure.py
"""
import json, os
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

MiB = 1 << 20
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#fcfcfb'
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Apple SD Gothic Neo', 'Helvetica', 'DejaVu Sans'],
                     'axes.unicode_minus': False, 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': MUTED, 'ytick.color': MUTED, 'text.color': INK})
# (source, hint, label, class)
GROUPS = [('d3b', 0, '일반 LDG', 1), ('d3b', 3, 'ld.global.cs\n(LDG.E.EF)', 2),
          ('c3', 1, 'createpolicy\nevict_first', 3), ('c3', 2, 'createpolicy\nevict_last', 3),
          ('d3b', 4, 'createpolicy\nevict_normal', 3), ('d3b', 5, 'createpolicy\nevict_unchanged', 3),
          ('d3b', 6, 'TMA 벌크 복사\n(힌트 없음)', 3), ('d3b', 7, 'TMA 벌크 복사\n+ evict_normal', 3)]
CLASS = {1: '① 기본 디스크립터\n일반 우선순위', 2: '② 기본 디스크립터\nevict-first', 3: '③ 커널이 만든 디스크립터 · TMA'}
SET = [(127, 12, 0.4), (127, 60, 0.4)]
SHADE = [S1, S3]

def key(q): return (q.get('hint', 0), q['window'], q['setaside'], q['hitratio'])

def measured(path):
    return {key(m['run']): m['counters']['dram_read_per_step'] / MiB
            for m in map(json.loads, open(path)) if 'counters' in m and m['run'].get('layers') == 32}

if __name__ == '__main__':
    M = {'d3b': measured('assets/sweep/d3b_measured_ampere.jsonl'), 'c3': measured('assets/sweep/c3_measured_ampere.jsonl')}
    Pd = {key(r['run']): r['dram_bytes'] for r in json.load(open('assets/sweep/d3b_predictions_ampere.json'))['runs']}
    Pc = {key(r['run']): {'v3': r['v3']} for r in json.load(open('assets/sweep/c23_v3_predictions_ampere.json'))['sets']['c3']}
    P = {'d3b': Pd, 'c3': Pc}
    fig, ax = plt.subplots(figsize=(11.2, 4.0), facecolor=SURF); ax.set_facecolor(SURF)
    bw = 0.34
    for g, (src, h, label, cl) in enumerate(GROUPS):
        base = M[src][(h, 0, 0, 0)]
        pb = P[src][(h, 0, 0, 0)]
        for j, s in enumerate(SET):
            x = g + (j - 0.5) * (bw + 0.04)
            saved = base - M[src][(h,) + s]
            ax.bar(x, max(saved, 0.0), width=bw, color=SHADE[j], edgecolor=SURF, linewidth=1)
            ax.text(x, -1.6, f'{saved:.0f}' if abs(saved) >= 0.5 else '0', ha='center', va='top', fontsize=7.8, color=INK2)
            ps = P[src][(h,) + s]
            ax.plot(x, (pb['v3'] - ps['v3']) / MiB, marker='o', markersize=6, markerfacecolor=SURF, markeredgecolor=S2,
                    markeredgewidth=1.8, zorder=4, linestyle='')
            if 'v3_desc' in ps:
                ax.plot(x, (pb['v3_desc'] - ps['v3_desc']) / MiB, marker='x', markersize=6.5, markeredgewidth=1.8,
                        color=INK, zorder=5, linestyle='')
    # class brackets
    for cl, (a, b) in {1: (0, 0), 2: (1, 1), 3: (2, 7)}.items():
        ax.plot([a - 0.42, b + 0.42], [64, 64], color=INK2, linewidth=1)
        ax.text((a + b) / 2, 65, CLASS[cl], ha='center', va='bottom', fontsize=8.1, color=INK, linespacing=1.15)
    for xv in (0.5, 1.5):
        ax.axvline(xv, color=GRID, linewidth=0.8, zorder=0)
    ax.set_xticks(range(len(GROUPS))); ax.set_xticklabels([g[2] for g in GROUPS], fontsize=8)
    ax.tick_params(axis='x', pad=13)
    ax.set_ylim(0, 74); ax.set_ylabel('창 없음 대비 줄어든 DRAM 읽기 (MiB/스텝)')
    ax.grid(axis='y', color=GRID, linewidth=0.6); ax.set_axisbelow(True)
    for sp in ('top', 'right'): ax.spines[sp].set_visible(False)
    hd = [Patch(color=SHADE[j], label=f'실측, set-aside {SET[j][1]} MiB') for j in range(2)]
    hd += [Line2D([], [], marker='o', linestyle='', markersize=6, markerfacecolor=SURF, markeredgecolor=S2, markeredgewidth=1.8,
                  label='v3 예측 (우선순위만 봄, 측정 전 고정)'),
           Line2D([], [], marker='x', linestyle='', markersize=6.5, markeredgewidth=1.8, color=INK,
                  label='v3.1 규칙 예측 (창은 기본 디스크립터에만, D3b 전 고정)')]
    ax.legend(handles=hd, loc='upper left', bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=8)
    ax.set_title('창이 먹는 로드는 드라이버 기본 디스크립터를 단 LDG 뿐이다 (합성 268 MiB 순환, 창 127 MiB, r 0.4)',
                 loc='left', fontsize=9.5, color=INK, pad=22)
    fig.text(0.01, -0.06, '①·② 는 D3b 세션(D2·D3 를 1 MiB 안에서 재현), evict_first·evict_last 는 D3. 막대 아래 숫자는 실측 절감(MiB). '
             '③ 은 모든 설정에서 창 없는 기준선과 0.1 MiB 안에서 같다.', fontsize=7.8, color=INK2)
    os.makedirs('assets/figures', exist_ok=True)
    for ext in ('png', 'pdf'):
        fig.savefig(f'assets/figures/load-class-window.{ext}', dpi=200, bbox_inches='tight', facecolor=SURF)
    print('wrote assets/figures/load-class-window.{png,pdf}')
