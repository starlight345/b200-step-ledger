#!/usr/bin/env python3
"""Figure: R2 — model v3 tested on real-LLM decode workloads it had not seen, every prediction frozen before measuring.
  (a) DRAM-byte MAE per predictor over every measured R2 setting (MiB per step).
  (b) Does the set-aside change the benefit? Per workload, DRAM(S 12) - DRAM(S 60) at window 127 MiB, hitRatio 0.4:
      measured vs v3, v2 and AutoScratch semantics (policy-blind tools are 0 by construction). R1 measured 3.2 / 0.7 MiB
      on its evict-first B1 workloads and 33.9 on B8.
  (c) One workload's hitRatio response at set-aside 12 and 60 MiB: measured, v3, v2.
Colors follow the entity in every panel: v3 blue, v2 green, AutoScratch orange, policy-blind tools gray, measured ink.
Reads assets/sweep/prior_sim_summary.json ('r2') and the joined rows (prior_sim_compare.load).
Usage: python3 scripts/make_r2_figure.py [WORKLOAD_FOR_C]   (default SmolLM-360M/B1/c1536)
"""
import json, os, sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'prior'))
import prior_sim_compare as PC

MiB = 1 << 20
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#fcfcfb'
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'        # validated slots 1-3 (validate_palette.py, light, #fcfcfb)
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Apple SD Gothic Neo', 'Helvetica', 'DejaVu Sans'],
                     'axes.unicode_minus': False, 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': MUTED, 'ytick.color': MUTED, 'text.color': INK})
COL = {'v3': S1, 'ours_v2': S3, 'autoscratch': S2, 'gtsim_l2': MUTED, 'memexplorer': MUTED, 'ours_v1': MUTED}
NAME = {'v3': '우리 v3 (사전 고정)', 'ours_v2': '우리 v2', 'ours_v1': '우리 v1', 'autoscratch': 'AutoScratch 의미론',
        'gtsim_l2': 'GPU-Tile-Sim L2 (LRU)', 'memexplorer': 'MemExplorer 식 (4)'}
SHOW = ('v3', 'ours_v2', 'autoscratch', 'gtsim_l2', 'memexplorer')   # v1 stays in the table (older, gray would mislabel it)

def short(wl):
    m, b, c = wl.split('/'); return f"{m.replace('SmolLM-', '')} {b} {c.replace('c', 'ctx ')}"

def style(ax):
    ax.set_facecolor(SURF); ax.grid(color=GRID, linewidth=0.6); ax.set_axisbelow(True)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)

if __name__ == '__main__':
    focus = sys.argv[1] if len(sys.argv) > 1 else 'SmolLM-360M/B1/c1536'
    S = json.load(open('assets/sweep/prior_sim_summary.json'))['r2']
    rows, preds = PC.load('r2')
    cls = json.load(open('assets/sweep/r2_predictions_ampere.json'))['load_classes']
    fig = plt.figure(figsize=(12.4, 4.1), facecolor=SURF)
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1.05, 1.1], wspace=0.95)
    a, b, c = (fig.add_subplot(gs[i]) for i in range(3))

    # (a) MAE bars
    ks = sorted((k for k in SHOW if k in S['abs']), key=lambda k: S['abs'][k]['mae'], reverse=True)
    y = list(range(len(ks)))
    a.barh(y, [S['abs'][k]['mae'] for k in ks], color=[COL[k] for k in ks], height=0.62, edgecolor=SURF, linewidth=1)
    for i, k in zip(y, ks):
        a.text(S['abs'][k]['mae'] + 0.6, i, f"{S['abs'][k]['mae']:.1f}", va='center', fontsize=8, color=INK2)
    a.set_yticks(y); a.set_yticklabels([NAME[k] for k in ks]); a.tick_params(axis='y', length=0)
    a.set_xlim(0, max(S['abs'][k]['mae'] for k in ks) * 1.18)
    a.set_xlabel('DRAM 읽기 오차 MAE (MiB/스텝)')
    a.set_title(f"(a) 처음 보는 {len(S['workloads'])} 워크로드, {S['n']} 설정 (R2)", loc='left', fontsize=9.5, pad=20)
    style(a); a.grid(axis='y', visible=False); a.spines['left'].set_visible(False)

    # (b) set-aside contrast per workload
    wls = [w for w in cls if w in S['workloads']]
    get = {}
    for r in rows:
        q = r['run']
        if q['window'] == 127 and q['hitratio'] == 0.4 and q['setaside'] in (12, 60):
            get[(r['wl'], q['setaside'])] = r
    for i, w in enumerate(wls):
        s12, s60 = get.get((w, 12)), get.get((w, 60))
        if not (s12 and s60): continue
        yy = len(wls) - 1 - i
        b.axhline(yy, color=GRID, linewidth=0.6, zorder=0)
        for k, mk, off in (('autoscratch', 's', 0.18), ('ours_v2', 'o', 0.06), ('v3', 'o', -0.06)):
            b.plot((s12['pred'][k] - s60['pred'][k]) / MiB, yy + off, marker=mk, markersize=6, color=COL[k],
                   markeredgecolor=SURF, markeredgewidth=0.8, linestyle='none', zorder=3)
        b.plot((s12['meas'] - s60['meas']) / MiB, yy - 0.18, marker='D', markersize=6.5, color=INK,
               markeredgecolor=SURF, markeredgewidth=0.8, linestyle='none', zorder=4)
    b.axvline(0, color=MUTED, linewidth=0.8)
    lab = []
    for w in wls:
        e = 'E' if cls[w]['classes']['q'] == 'E' else 'N'
        lab.append(f"{short(w)} · 가중치 {'evict-first' if e == 'E' else '일반'}")
    b.set_yticks(list(range(len(wls)))); b.set_yticklabels(lab[::-1], fontsize=8); b.tick_params(axis='y', length=0)
    b.set_ylim(-0.6, len(wls) - 0.4)
    b.set_xlabel('DRAM(S 12) - DRAM(S 60)  (MiB/스텝, 창 127, r 0.4)')
    b.set_title('(b) set-aside 가 이득을 바꾸는가', loc='left', fontsize=9.5, pad=20)
    style(b); b.grid(axis='y', visible=False); b.spines['left'].set_visible(False)
    hand = [Line2D([], [], marker='D', color=INK, linestyle='none', markersize=6, label='실측'),
            Line2D([], [], marker='o', color=S1, linestyle='none', markersize=6, label='우리 v3'),
            Line2D([], [], marker='o', color=S3, linestyle='none', markersize=6, label='우리 v2'),
            Line2D([], [], marker='s', color=S2, linestyle='none', markersize=6, label='AutoScratch')]
    b.legend(handles=hand, loc='lower left', bbox_to_anchor=(0, 1.0), ncol=4, fontsize=7.5, frameon=False,
             labelcolor=INK2, handletextpad=0.2, columnspacing=0.9, borderaxespad=0.2)

    # (c) one workload's hitRatio response at S 12 and S 60
    for sa, ls, mf in ((12, '-', None), (60, (0, (4, 2)), SURF)):
        sel = sorted((r for r in rows if r['wl'] == focus and r['run']['window'] == 127 and r['run']['setaside'] == sa),
                     key=lambda r: r['run']['hitratio'])
        x = [r['run']['hitratio'] for r in sel]
        for k in ('ours_v2', 'v3'):
            c.plot(x, [r['pred'][k] / MiB for r in sel], color=COL[k], linewidth=1.6, linestyle=ls, marker='o',
                   markersize=3.5, markerfacecolor=mf or COL[k])
        c.plot(x, [r['meas'] / MiB for r in sel], color=INK, linewidth=2, linestyle=ls, marker='D', markersize=4.5,
               markerfacecolor=mf or INK)
    base = [r for r in rows if r['wl'] == focus and PC.is_base(r['run'])]
    if base:
        c.axhline(base[0]['meas'] / MiB, color=MUTED, linewidth=0.8, linestyle=(0, (1, 2)))
        c.text(1.0, base[0]['meas'] / MiB, '실측 기준선\n(정책 없음)', ha='right', va='center', fontsize=7, color=INK2,
               bbox=dict(boxstyle='square,pad=0.15', facecolor=SURF, edgecolor='none'))
    hand = [Line2D([], [], color=INK, linewidth=2, marker='D', markersize=4, label='실측'),
            Line2D([], [], color=S1, linewidth=1.6, marker='o', markersize=3.5, label='우리 v3'),
            Line2D([], [], color=S3, linewidth=1.6, marker='o', markersize=3.5, label='우리 v2')]
    c.legend(handles=hand, loc='lower left', bbox_to_anchor=(0, 1.0), ncol=3, fontsize=7.5, frameon=False,
             labelcolor=INK2, handletextpad=0.3, columnspacing=1.0, borderaxespad=0.2)
    c.set_xlabel('hitRatio (창 127 MiB)'); c.set_ylabel('DRAM 읽기 (MiB/스텝)')
    c.set_title(f'(c) {short(focus)}: 실선 S 12, 점선 S 60 (속 빈 표식)', loc='left', fontsize=9.5, pad=20)
    style(c)
    fig.text(0.07, -0.1, '예측은 모두 측정 전에 고정했다. v3 의 로드 클래스(가중치를 evict-first 로 읽는가)는 각 워크로드의 SASS 에서 정했고, '
             '새로 적합한 값은 없다(φ 0.3, 16-way 는 v2 그대로).\n배치 1 은 cuBLAS gemvx(LDG.E.EF), 배치 2 이상은 CUTLASS GEMM(일반 로드). '
             '정책을 못 보는 도구(GPU-Tile-Sim, MemExplorer)는 (b) 에서 정의상 0 이다.', fontsize=7.8, color=INK2)
    for ext in ('png', 'pdf'):
        fig.savefig(f'assets/figures/r2-prospective.{ext}', dpi=200, bbox_inches='tight', facecolor=SURF)
    print('wrote assets/figures/r2-prospective.{png,pdf}')
