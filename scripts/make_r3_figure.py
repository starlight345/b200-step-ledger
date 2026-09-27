#!/usr/bin/env python3
"""Figure: R3 — changing how the decode kernels load their weights (evict-first, as cuBLAS gemv does at batch 1)
changes the DRAM traffic and the set-aside decision, as model v3 predicted before measuring.
  (a) per workload: baseline DRAM per step before (R2) and after (R3) the intervention, measured, and v3's prediction.
  (b) per workload: DRAM(S 12) - DRAM(S 60) at window 127 MiB, hitRatio 0.4 — how much the set-aside matters —
      before and after, measured vs v3.
  (c) SmolLM-135M B2: hitRatio response at set-aside 12 and 60 MiB before (R2) and after (R3), with v3's prediction.
Colors follow the entity: measured after = ink, measured before = gray, v3 = blue (after: filled, before: hollow).
Usage: python3 scripts/make_r3_figure.py
"""
import json, os
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

MiB = 1 << 20
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#fcfcfb'
S1 = '#2a78d6'
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Apple SD Gothic Neo', 'Helvetica', 'DejaVu Sans'],
                     'axes.unicode_minus': False, 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': MUTED, 'ytick.color': MUTED, 'text.color': INK})
ORDER = ('SmolLM-135M/B2/c512', 'SmolLM-135M/B4/c512', 'SmolLM-360M/B4/c512', 'SmolLM-360M/B8/c512')

def wl(r): return f"{r['run']['model']}/B{r['run']['batch']}/c{r['run']['context']}"
def key(r): return (r['run']['window'], r['run']['setaside'], r['run']['hitratio'])

def table(path, field=None):
    out = {}
    if not os.path.exists(path): return out
    rows = json.load(open(path))['runs'] if path.endswith('.json') else [json.loads(l) for l in open(path)]
    for r in rows:
        if field is None and 'counters' not in r: continue
        v = r['counters']['dram_read_per_step'] if field is None else (r[field] if field != 'v3' else r['dram_read_bytes']['v3'])
        out[(wl(r), key(r))] = v / MiB
    return out

def short(w):
    m, b, c = w.split('/'); return f"{m.replace('SmolLM-', '')} {b}"

if __name__ == '__main__':
    R3 = table('assets/sweep/r3_measured_ampere.jsonl'); R2 = table('assets/sweep/r2_measured_ampere.jsonl')
    V3 = table('assets/sweep/r3_predictions_ampere.json', 'v3')
    V3o = table('assets/sweep/r3_predictions_ampere.json', 'v3_without_intervention')
    done = [w for w in ORDER if (w, (0, 0, 0.0)) in R3 or (w, (0, 0, 0)) in R3]
    B = (0, 0, 0)
    fig = plt.figure(figsize=(12.4, 4.2), facecolor=SURF)
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.15], wspace=0.55)
    a, b, c = (fig.add_subplot(gs[i]) for i in range(3))
    for ax in (a, b, c): ax.set_facecolor(SURF)
    ys = range(len(done))
    for i, w in enumerate(done):
        step0 = V3o[(w, B)]
        # (a) baseline change relative to the logical step (v3 without intervention = logical step for N workloads)
        a.plot([R2[(w, B)] - step0], [i], marker='D', color=MUTED, markersize=6, linestyle='')
        a.plot([R3[(w, B)] - step0], [i], marker='D', color=INK, markersize=6, linestyle='')
        a.plot([V3[(w, B)] - step0], [i], marker='o', color=S1, markersize=6, linestyle='')
        a.plot([R2[(w, B)] - step0, R3[(w, B)] - step0], [i, i], color=GRID, linewidth=1, zorder=0)
        # (b) set-aside contrast
        con = lambda t: t[(w, (127, 12, 0.4))] - t[(w, (127, 60, 0.4))]
        b.plot([con(R2)], [i], marker='D', color=MUTED, markersize=6, linestyle='')
        b.plot([con(R3)], [i], marker='D', color=INK, markersize=6, linestyle='')
        b.plot([con(V3)], [i], marker='o', color=S1, markersize=6, linestyle='')
        b.plot([con(V3o)], [i], marker='o', color=S1, markerfacecolor=SURF, markersize=6, linestyle='')
    for ax in (a, b):
        ax.set_yticks(list(ys)); ax.set_yticklabels([short(w) for w in done]); ax.invert_yaxis()
        ax.grid(axis='x', color=GRID, linewidth=0.6); ax.set_axisbelow(True)
        for s in ('top', 'right', 'left'): ax.spines[s].set_visible(False)
        ax.tick_params(axis='y', length=0)
    a.axvline(0, color=INK2, linewidth=0.8)
    a.set_xlabel('기준선 DRAM - 논리 스텝 (MiB/스텝)')
    a.set_title('(a) 기준선: 가중치 evict-first 로 바꾸면', loc='left', fontsize=9.5)
    b.set_xlabel('DRAM(S 12) - DRAM(S 60)  (MiB/스텝, 창 127, r 0.4)')
    b.set_title('(b) set-aside 가 이득을 바꾸는가', loc='left', fontsize=9.5)
    hand = [Line2D([], [], marker='D', color=MUTED, linestyle='', label='개입 전 실측 (R2)'),
            Line2D([], [], marker='D', color=INK, linestyle='', label='개입 후 실측 (R3)'),
            Line2D([], [], marker='o', color=S1, linestyle='', label='v3 예측, 개입 후 (측정 전 고정)'),
            Line2D([], [], marker='o', color=S1, markerfacecolor=SURF, linestyle='', label='v3 예측, 개입 전')]
    fig.legend(handles=hand, loc='upper center', ncol=4, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 1.04))
    focus = 'SmolLM-135M/B2/c512'
    H = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0)
    if focus in done:
        for sa, ls in ((12, '-'), (60, (0, (4, 2)))):
            c.plot(H, [R2[(focus, (127, sa, r))] for r in H], color=MUTED, linestyle=ls, linewidth=1.6, marker='D', markersize=3.5)
            c.plot(H, [R3[(focus, (127, sa, r))] for r in H], color=INK, linestyle=ls, linewidth=2, marker='D', markersize=4)
            c.plot(H, [V3[(focus, (127, sa, r))] for r in H], color=S1, linestyle=ls, linewidth=1.6, marker='o', markersize=3.5)
        c.text(1.0, R2[(focus, (127, 12, 1.0))] + 2, '개입 전: S 12 와 S 60 이 갈린다', ha='right', va='bottom', fontsize=7.5, color=INK2)
        c.text(0.02, R3[(focus, (127, 12, 0.3))] - 14, '개입 후: 두 S 가 겹친다', ha='left', fontsize=7.5, color=INK)
        c.set_xlabel('hitRatio (창 127 MiB; 실선 S 12, 점선 S 60)'); c.set_ylabel('DRAM 읽기 (MiB/스텝)')
        c.set_title('(c) 135M 배치 2: hitRatio 반응', loc='left', fontsize=9.5)
        c.grid(color=GRID, linewidth=0.6); c.set_axisbelow(True)
        for s in ('top', 'right'): c.spines[s].set_visible(False)
    fig.text(0.06, -0.05, '개입 = 디코드 투영(q·k·v·o·gate·up·down·LM head)의 가중치를 ld.global.cs(SASS LDG.E.EF)로 읽는 커널로 바꾼 것. '
             '예측은 모두 측정 전에 고정(r3_predictions sha256 9635f151). KV 가 L2 보다 크면(360M B8) v3 는 변화 없음을 예측.',
             fontsize=7.8, color=INK2)
    os.makedirs('assets/figures', exist_ok=True)
    for ext in ('png', 'pdf'):
        fig.savefig(f'assets/figures/r3-intervention.{ext}', dpi=200, bbox_inches='tight', facecolor=SURF)
    print('wrote assets/figures/r3-intervention.{png,pdf}', 'workloads', done)
