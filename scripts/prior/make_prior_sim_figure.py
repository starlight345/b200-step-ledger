#!/usr/bin/env python3
"""Figure: policy-aware prior simulators vs our model on the held-out data.
  (a) H1c synthetic, (b) R1 real-LLM decode: DRAM-byte MAE per predictor (MiB per step), ours highlighted.
      Accel-Sim covers only R1's SmolLM-135M B1/B8 (360M B1 would take ~1 day), so in (b) it is a separate dashed
      row scored on those 94 settings, next to GPU-Tile-Sim on the same 94 — not ranked against the 141-setting bars.
  (c) R1 SmolLM-135M B1, window 127 MiB, set-aside 12 MiB: DRAM per step vs hitRatio — measured, ours v2,
      AutoScratch semantics, and the policy-blind tools (Accel-Sim, GPU-Tile-Sim, LLMCompass: one flat line each).
Reads prior_sim_summary.json (prior_sim_compare.py) and the joined rows. Accel-Sim appears once its runs exist.
Usage: python3 scripts/prior/make_prior_sim_figure.py
"""
import json, os, sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
import prior_sim_compare as PC

MiB = 1 << 20
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#fcfcfb'
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'           # validated categorical slots 1-3 (as make_r1_figure.py)
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Apple SD Gothic Neo', 'Helvetica', 'DejaVu Sans'],
                     'axes.unicode_minus': False, 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': MUTED, 'ytick.color': MUTED, 'text.color': INK})
OURS = {'v2', 'cuda_policy', 'ours_v1', 'ours_v2', 'v3'}
NAME = {'no_residency': 'LLMCompass 류 (상주 없음)', 'capacity_only': 'MemExplorer 류 (용량만)',
        'fixed_lru': 'GPU-Tile-Sim L2 (LRU)', 'cuda_policy': '우리 v1', 'v2': '우리 v2',
        'llmcompass': 'LLMCompass', 'genz': 'GenZ', 'memexplorer': 'MemExplorer 식 (4)', 'gtsim_l2': 'GPU-Tile-Sim L2',
        'ours_v1': '우리 v1', 'ours_v2': '우리 v2', 'accelsim': 'Accel-Sim 2.0', 'autoscratch': 'AutoScratch 의미론',
        'v3': '우리 v3 (명령어 클래스)'}

def bars(ax, S, title, posthoc=(), extra=None):
    """extra = (label, MAE, note): one predictor scored on a different subset, drawn as a dashed hollow bar
    below a divider so it is not read as part of the ranking."""
    ks = sorted(S['abs'], key=lambda k: S['abs'][k]['mae'], reverse=True)
    off = 1.5 if extra else 0
    y = [i + off for i in range(len(ks))]
    col = [S1 if k in OURS else (S2 if k == 'autoscratch' else MUTED) for k in ks]
    bs = ax.barh(y, [S['abs'][k]['mae'] for k in ks], color=col, height=0.62, edgecolor=SURF, linewidth=1)
    for b_, k in zip(bs, ks):
        if k in posthoc: b_.set_hatch('////'); b_.set_edgecolor(SURF); b_.set_facecolor(SURF); b_.set_edgecolor(S1); b_.set_linewidth(1.2)
    for i, k in zip(y, ks):
        ax.text(S['abs'][k]['mae'] + 0.6, i, f"{S['abs'][k]['mae']:.1f}", va='center', fontsize=8, color=INK2)
    labels = [NAME[k] + (' — 사후' if k in posthoc else '') for k in ks]
    if extra:
        lab, v, note = extra
        ax.barh([0], [v], height=0.62, facecolor='none', edgecolor=MUTED, linewidth=1.2, linestyle=(0, (3, 2)))
        ax.text(v + 0.6, 0, note, va='center', fontsize=8, color=INK2)
        ax.axhline(off - 0.75, color=GRID, linewidth=0.8)
        y, labels = [0] + y, [lab] + labels
    ax.set_yticks(y); ax.set_yticklabels(labels)
    ax.set_xlim(0, max(S['abs'][k]['mae'] for k in ks) * 1.16)       # value labels stay inside the panel
    ax.set_xlabel('DRAM 읽기 오차 MAE (MiB/스텝)')
    ax.set_title(title, loc='left', fontsize=9.5, color=INK)
    ax.grid(axis='x', color=GRID, linewidth=0.6); ax.set_axisbelow(True)
    for s in ('top', 'right', 'left'): ax.spines[s].set_visible(False)
    ax.tick_params(axis='y', length=0)

if __name__ == '__main__':
    summ = json.load(open('assets/sweep/prior_sim_summary.json'))
    for k in ('abs',):                                   # v3 == v2 on H1c (plain loads): show one bar
        summ['h1c'][k].pop('v3', None)
    fig = plt.figure(figsize=(11.2, 3.9), facecolor=SURF)
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.15], wspace=0.72)
    a, b, c = fig.add_subplot(gs[0]), fig.add_subplot(gs[1]), fig.add_subplot(gs[2])
    for ax in (a, b, c): ax.set_facecolor(SURF)
    bars(a, summ['h1c'], f"(a) 합성, 보류 {summ['h1c']['n']} 설정 (H1c)")
    sub = summ['r1_accelsim']                           # the R1 settings Accel-Sim covers (135M B1 + B8)
    bars(b, summ['r1'], f"(b) 실제 LLM 디코드 {summ['r1']['n']} 설정 (R1)", posthoc=('v3',),
         extra=(f"Accel-Sim 2.0 ({sub['n']} 설정만)", sub['abs']['accelsim']['mae'],
                f"{sub['abs']['accelsim']['mae']:.1f}  (같은 설정의 GPU-Tile-Sim {sub['abs']['gtsim_l2']['mae']:.1f})"))

    rows, preds = PC.load('r1', need='accelsim')        # (c) is 135M B1, which Accel-Sim covers
    sel = sorted((r for r in rows if r['wl'] == 'SmolLM-135M/B1' and r['run']['window'] == 127
                  and r['run']['setaside'] == 12), key=lambda r: r['run']['hitratio'])
    x = [r['run']['hitratio'] for r in sel]
    base = [r for r in rows if r['wl'] == 'SmolLM-135M/B1' and PC.is_base(r['run'])][0]
    flat = [k for k in ('gtsim_l2', 'llmcompass', 'accelsim') if k in preds]
    for k in flat:
        c.plot(x, [r['pred'][k] / MiB for r in sel], color=MUTED, linewidth=1.2, linestyle='--')
    top = max(r['pred'][k] for r in sel for k in flat) / MiB
    c.text(0.0, top + 1.6, f'정책을 못 보는 도구 {len(flat)}개 (평평, 점선)', ha='left', va='bottom', fontsize=7.5, color=INK2)
    c.plot(x, [r['pred']['autoscratch'] / MiB for r in sel], color=S2, linewidth=2, marker='s', markersize=4)
    c.plot(x, [r['pred']['ours_v2'] / MiB for r in sel], color=S1, linewidth=2, marker='o', markersize=4)
    if 'v3' in preds:
        c.plot(x, [r['pred']['v3'] / MiB for r in sel], color=S1, linewidth=1.6, linestyle=(0, (4, 2)), marker='o',
               markersize=3.5, markerfacecolor=SURF)
        lo = min(range(len(sel)), key=lambda i: sel[i]['pred']['v3'])
        c.text(x[lo] + 0.03, sel[lo]['pred']['v3'] / MiB, '우리 v3 (사후)', color=S1, fontsize=8.5, va='center')
    c.plot(x, [r['meas'] / MiB for r in sel], color=INK, linewidth=2, marker='D', markersize=4.5)
    c.axhline(base['meas'] / MiB, color=GRID, linewidth=1)
    c.text(0.13, base['meas'] / MiB + 0.6, '실측 기준선 (정책 없음)', ha='left', va='bottom', fontsize=7.5, color=MUTED)
    c.text(x[4] - 0.04, sel[4]['meas'] / MiB - 4.5, '실측', color=INK, fontsize=8.5, ha='right')
    c.text(0.52, sel[5]['pred']['ours_v2'] / MiB - 1.5, '우리 v2', color=S1, fontsize=8.5, va='top')
    c.text(0.15, sel[5]['pred']['autoscratch'] / MiB - 2.2, 'AutoScratch 의미론', color=S2, fontsize=8.5, va='top')
    c.set_ylim(top=top + 6)
    c.set_xlabel('hitRatio (창 127 MiB, set-aside 12 MiB)'); c.set_ylabel('DRAM 읽기 (MiB/스텝)')
    c.set_title('(c) SmolLM-135M B1: 실측은 set-aside 와 무관', loc='left', fontsize=9.5, color=INK)
    c.grid(color=GRID, linewidth=0.6); c.set_axisbelow(True)
    for s in ('top', 'right'): c.spines[s].set_visible(False)
    fig.text(0.07, -0.17, '막대 색: 파랑 = 우리 모델, 주황 = 정책형 선행(AutoScratch, 코드 비공개라 논문의 의미론을 재구현), '
             '회색 = 정책을 표현하지 못하는 도구(실제 코드 실행 또는 논문 식). 사전 고정 예측과 하드웨어 카운터(ncu) 비교.\n'
             'v3 = v2 + 로드 명령의 evict-first 클래스(적합 0; 합성에서는 v2 와 같다). R1 의 v3 는 R1·D3 를 본 뒤 SASS 로 클래스를 정한 사후 분석(빗금).\n'
             f"(b) 의 Accel-Sim 은 360M B1 을 비용(트레이스 수 시간 + 시뮬레이션 약 1일) 때문에 돌리지 않아 135M B1·B8 {sub['n']} 설정만 채점했다(점선 막대, 순위 밖). "
             f"같은 설정에서 우리 v2 {sub['abs']['ours_v2']['mae']:.1f}, v3 {sub['abs']['v3']['mae']:.1f}(사후).\n"
             "(c) 점선 = " + '·'.join(NAME[k] for k in flat) + ' 의 예측(정책 설정과 무관하게 워크로드마다 한 값).',
             fontsize=7.8, color=INK2)
    os.makedirs('assets/figures', exist_ok=True)
    for ext in ('png', 'pdf'):
        fig.savefig(f'assets/figures/prior-sim-comparison.{ext}', dpi=200, bbox_inches='tight', facecolor=SURF)
    print('wrote assets/figures/prior-sim-comparison.{png,pdf}')
