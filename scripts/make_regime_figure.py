#!/usr/bin/env python3
"""Figure: where does policy-aware modeling matter? Every measured real-decode workload (R1, R2, R3, N1) against its
working-set / L2 ratio (logical step bytes = weights + KV read, over the 96 MiB L2).
  (a) What the policy knobs can do, measured: best saving over the no-policy baseline (filled) and the full spread over the
      grid (hollow; a bad setting can also add traffic), both as % of the logical step. Line: persisting cap 60 MiB / step.
  (b) Prediction error of each frozen predictor, MAE as % of the step (log scale). v3 only where it was frozen before
      measuring (R2, R3, N1); R1's v3 was post hoc and is left out.
Reads assets/sweep/{r1,r2,r3,n1}_{predictions,measured}_ampere.*; writes assets/figures/regime.{png,pdf}.
"""
import json, statistics as st
from pathlib import Path
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

MiB, L2_MIB, CAP_MIB = 1 << 20, 96, 60
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#fcfcfb'
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'        # validated slots 1-3; same entity colors as the R2/R3 figures
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Apple SD Gothic Neo', 'Helvetica', 'DejaVu Sans'],
                     'axes.unicode_minus': False, 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': MUTED, 'ytick.color': MUTED, 'text.color': INK})
SETS = (('R1', 'r1', 'o'), ('R2', 'r2', 's'), ('R3', 'r3', 'D'), ('N1', 'n1', '^'))
EXP = {'R1': 'R1 실제 디코드', 'R2': 'R2 처음 보는 디코드', 'R3': 'R3 로드 방식 개입', 'N1': 'N1 음성 대조 (1.7B)'}
PRED = (('v3', '우리 v3 (사전 고정)', S1), ('autoscratch', 'AutoScratch 의미론', S2),
        ('gtsim_l2', 'GPU-Tile-Sim L2 (LRU)', INK2), ('memexplorer', 'MemExplorer 식 (4)', MUTED))

def key(q): return json.dumps(q, sort_keys=True)

def workloads():
    out = []
    for tag, f, mk in SETS:
        P = {key(r['run']): r for r in json.load(open(f'assets/sweep/{f}_predictions_ampere.json'))['runs']}
        W = {}
        for l in open(f'assets/sweep/{f}_measured_ampere.jsonl'):
            m = json.loads(l); p = P.get(key(m['run']))
            if p is None or 'counters' not in m: continue
            q = m['run']; W.setdefault((q['model'], q['batch'], q.get('context', 512)), []).append(
                (q, p, m['counters']['dram_read_per_step'] / MiB))
        for w, rs in W.items():
            step = (rs[0][1]['bytes']['weights'] + rs[0][1]['bytes']['kv_read']) / MiB
            vals = [x[2] for x in rs]
            base = [x[2] for x in rs if x[0]['window'] == 0 and x[0]['setaside'] == 0][0]
            mae = {k: 100 * st.mean(abs(x[1]['dram_read_bytes'][k] / MiB - x[2]) for x in rs) / step
                   for k, _, _ in PRED if k in rs[0][1]['dram_read_bytes'] and not (k == 'v3' and tag == 'R1')}
            out.append(dict(exp=tag, marker=mk, wl=w, n=len(rs), step=step, x=step / L2_MIB,
                            save=100 * (base - min(vals)) / step, spread=100 * (max(vals) - min(vals)) / step, mae=mae))
    return out

def style(ax):
    ax.set_facecolor(SURF); ax.grid(color=GRID, linewidth=0.6, which='major'); ax.set_axisbelow(True)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)
    ax.set_xscale('log'); ax.set_xlim(2.2, 50)
    ax.set_xticks([2.5, 5, 10, 20, 40]); ax.set_xticklabels(['2.5', '5', '10', '20', '40'])
    ax.minorticks_off()
    ax.set_xlabel('작업집합 / L2  (배, 로그)')

if __name__ == '__main__':
    D = workloads()
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.2, 4.0), facecolor=SURF)

    # (a) measured effect of the policy knobs
    style(a)
    xs = [2.2 * 1.02 ** i for i in range(200) if 2.2 * 1.02 ** i <= 50]
    a.plot(xs, [100 * CAP_MIB / (x * L2_MIB) for x in xs], color=MUTED, lw=1.2, ls=(0, (4, 3)), zorder=1)
    a.text(12.5, 100 * CAP_MIB / (12.5 * L2_MIB) + 1.2, 'persisting 상한 60 MiB ÷ 작업집합', fontsize=8, color=INK2)
    for d in D:
        a.scatter(d['x'], d['spread'], s=34, marker=d['marker'], facecolor=SURF, edgecolor=MUTED, lw=1.1, zorder=3)
        a.scatter(d['x'], d['save'], s=38, marker=d['marker'], color=INK, lw=0, zorder=4)
    a.axvspan(2.2, 10, color=S1, alpha=0.05, lw=0, zorder=0)
    a.text(2.35, 0.2, '정책이 결정을 바꾸는 영역\n(작업집합 < 10 x L2)', fontsize=8.5, color=S1, va='bottom')
    a.set_ylim(-1, 34); a.set_ylabel('실측 DRAM 변화  (스텝 대비 %)')
    a.set_title('(a) 정책 손잡이가 실제로 움직이는 트래픽', loc='left', fontsize=9.5)
    h = [Line2D([], [], marker='o', color=INK, lw=0, ms=6, label='최대 절감 (기준선 - 최선)'),
         Line2D([], [], marker='o', color=MUTED, markerfacecolor=SURF, lw=0, ms=6, label='전체 폭 (나쁜 설정 포함)')]
    h += [Line2D([], [], marker=mk, color=INK2, lw=0, ms=5.5, label=EXP[t]) for t, _, mk in SETS]
    a.legend(handles=h, frameon=False, fontsize=7.8, loc='upper right')

    # (b) prediction error per predictor
    style(b)
    for k, name, c in PRED:
        for d in D:
            if k in d['mae']:
                b.scatter(d['x'], d['mae'][k], s=30, marker=d['marker'], color=c, lw=0, alpha=0.9,
                          zorder=5 if k == 'v3' else 3)
    b.set_yscale('log'); b.set_ylim(0.25, 45)
    b.set_yticks([0.3, 1, 3, 10, 30]); b.set_yticklabels(['0.3', '1', '3', '10', '30'])
    b.set_ylabel('예측 오차 MAE  (스텝 대비 %, 로그)')
    b.set_title('(b) 예측기 사이의 차이는 작업집합이 L2 에 가까울 때만 크다', loc='left', fontsize=9.5)
    b.legend(handles=[Line2D([], [], marker='o', color=c, lw=0, ms=6, label=n) for _, n, c in PRED],
             frameon=False, fontsize=7.8, loc='upper right')
    fig.tight_layout(w_pad=2.5)
    out = Path('assets/figures'); out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / 'regime.png', dpi=200, facecolor=SURF); fig.savefig(out / 'regime.pdf', facecolor=SURF)
    for d in sorted(D, key=lambda d: d['x']):
        print(f"{d['exp']} {d['wl'][0]:<16} B{d['wl'][1]} c{d['wl'][2]:<5} WS/L2 {d['x']:5.2f}  save {d['save']:5.2f}%  "
              f"spread {d['spread']:5.2f}%  " + ' '.join(f"{k} {v:.2f}" for k, v in d['mae'].items()))
    print('wrote assets/figures/regime.png, regime.pdf')
