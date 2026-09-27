#!/usr/bin/env python3
"""Figure: how much L2 does LLM decode need? The answer depends on the predictor (capacity_projection.json).
  (a) SmolLM-360M c1536 B1 — weights read evict-first (cuBLAS gemvx).  (b) SmolLM-360M c512 B4 — weights read with
  normal loads (CUTLASS GEMM), plus R3's intervention (weights evict-first).
Curves: LRU (GPU-Tile-Sim; Accel-Sim gave the same bytes), capacity only (MemExplorer eq. 4), v3 without / with the
best persistence setting, and (b) v3 with the intervention. Markers at 96 MiB are measurements on the RTX PRO 5000:
baseline and the best of the measured settings (R2), and in (b) R3 when it exists. Beyond 96 MiB every curve is a
model projection (v3 was validated at 96 MiB only). The dotted line is a 20 % cut of the step's DRAM reads; the
capacity where each curve crosses it is written in the legend.
Usage: python3 scripts/make_capacity_figure.py
"""
import json, os
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

MiB = 1 << 20
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#fcfcfb'
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Apple SD Gothic Neo', 'Helvetica', 'DejaVu Sans'],
                     'axes.unicode_minus': False, 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': MUTED, 'ytick.color': MUTED, 'text.color': INK})
CURVES = [('lru', 'LRU (GPU-Tile-Sim·Accel-Sim)', MUTED, (0, (5, 2)), 1.4),
          ('capacity_only', '용량만 (MemExplorer 식 4)', MUTED, (0, (1, 1.5)), 1.6),
          ('v3_native', 'v3, 정책 설정 없음', S1, (0, (3, 1.5)), 1.4),
          ('v3_best', 'v3, 최적 정책 설정', S1, '-', 2.2),
          ('v3_native_ef', 'v3, 가중치 evict-first (R3), 설정 없음', S2, (0, (3, 1.5)), 1.4),
          ('v3_best_ef', 'v3, 가중치 evict-first (R3), 최적 설정', S2, '-', 2.2)]

def crossing(caps, ys, target):
    """Smallest capacity (log-interpolated) at which the curve drops to the target; None if it never does."""
    for i in range(1, len(caps)):
        if ys[i] <= target < ys[i - 1]:
            f = (ys[i - 1] - target) / (ys[i - 1] - ys[i])
            return float(np.exp(np.log(caps[i - 1]) + f * (np.log(caps[i]) - np.log(caps[i - 1]))))
        if ys[0] <= target: return caps[0]
    return None

def measured(path, w):
    if not os.path.exists(path): return None
    rows = [json.loads(l) for l in open(path)]
    rows = [r for r in rows if f"{r['run']['model']}/B{r['run']['batch']}/c{r['run']['context']}" == w and 'counters' in r]
    if not rows: return None
    base = [r for r in rows if r['run']['window'] == 0 and r['run']['setaside'] == 0][0]['counters']['dram_read_per_step']
    best = min(r['counters']['dram_read_per_step'] for r in rows)
    return base / MiB, best / MiB

def panel(ax, w, P, title):
    pts = P['workloads'][w]['points']; caps = [p['C_mib'] for p in pts]; step = pts[0]['step_mib']
    target = 0.8 * step
    hand = []
    for k, lab, col, ls, lw in CURVES:
        if k not in pts[0]: continue
        ys = [p[k] for p in pts]
        ax.plot(caps, ys, color=col, linestyle=ls, linewidth=lw)
        c = crossing(caps, ys, target)
        hand.append(Line2D([], [], color=col, linestyle=ls, linewidth=lw,
                           label=f"{lab}: {'> 1 GiB' if c is None else f'{c:.0f} MiB'}"))
    ax.axhline(target, color=INK2, linestyle=(0, (1, 3)), linewidth=1)
    ax.text(caps[0], target + step * 0.012, '20 % 절감', ha='left', va='bottom', fontsize=7.5, color=INK2)
    ax.axvline(96, color=GRID, linewidth=1)
    m = measured('assets/sweep/r2_measured_ampere.jsonl', w)
    if m:
        ax.plot([96], [m[0]], marker='D', color=INK, markerfacecolor=SURF, markersize=6, zorder=5)
        ax.plot([96], [m[1]], marker='D', color=INK, markersize=6, zorder=5)
        hand.append(Line2D([], [], marker='D', color=INK, markerfacecolor=SURF, linestyle='', label='실측 96 MiB: 기준선'))
        hand.append(Line2D([], [], marker='D', color=INK, linestyle='', label='실측 96 MiB: 잰 47 설정 중 최적'))
    r3 = measured('assets/sweep/r3_measured_ampere.jsonl', w)
    if r3:
        ax.plot([96], [r3[0]], marker='s', color=S2, markerfacecolor=SURF, markersize=6, zorder=5)
        ax.plot([96], [r3[1]], marker='s', color=S2, markersize=6, zorder=5)
        hand.append(Line2D([], [], marker='s', color=S2, markerfacecolor=SURF, linestyle='', label='R3 실측 96 MiB: 기준선'))
        hand.append(Line2D([], [], marker='s', color=S2, linestyle='', label='R3 실측 96 MiB: 최적'))
    ticks = [c for c in caps if c in (48, 64, 96, 128, 192, 256, 384, 512, 768, 1024)]
    ax.set_xscale('log', base=2); ax.set_xticks(ticks); ax.set_xticklabels([str(c) for c in ticks], fontsize=7.5)
    ax.minorticks_off()
    ax.set_xlabel('L2 용량 (MiB, 96 = 이 GPU; 그 위는 모델 투영)'); ax.set_ylabel('DRAM 읽기 (MiB/스텝)')
    ax.set_ylim(0, step * 1.06)
    ax.set_title(title, loc='left', fontsize=9.5, color=INK)
    ax.grid(color=GRID, linewidth=0.6); ax.set_axisbelow(True)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)
    ax.legend(handles=hand, loc='lower left', fontsize=7, frameon=False, title='범례: 20 % 절감에 필요한 L2', title_fontsize=7.5)

if __name__ == '__main__':
    P = json.load(open('assets/sweep/capacity_projection.json'))
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.4, 4.6), facecolor=SURF)
    for ax in (a, b): ax.set_facecolor(SURF)
    panel(a, 'SmolLM-360M/B1/c1536', P, '(a) 360M 배치 1: 가중치 evict-first (cuBLAS gemv)')
    panel(b, 'SmolLM-360M/B4/c512', P, '(b) 360M 배치 4: 가중치 일반 로드 (CUTLASS GEMM) + R3 개입')
    fig.text(0.06, -0.03, '96 MiB 의 점은 실측(RTX PRO 5000). 그보다 큰 용량은 v3(96 MiB 에서만 검증)의 투영이며, 창 최대 크기가 L2 의 4/3 으로 '
             '함께 커진다고 가정했다. set-aside ≤ L2 의 10/16.', fontsize=7.8, color=INK2)
    fig.tight_layout()
    os.makedirs('assets/figures', exist_ok=True)
    for ext in ('png', 'pdf'):
        fig.savefig(f'assets/figures/capacity-projection.{ext}', dpi=200, bbox_inches='tight', facecolor=SURF)
    print('wrote assets/figures/capacity-projection.{png,pdf}')
