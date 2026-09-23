#!/usr/bin/env python3
"""정책 축 스윕 그림 — 이득은 즉시 포화하고 비용만 선형으로 는다."""
import csv
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
BLUE, ORANGE, TEAL = '#2a78d6','#eb6834','#1b9e77'
RAMP = ['#cfe0f7','#a9c9f0','#7db0e8','#2a78d6','#17518f']
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Apple SD Gothic Neo','Helvetica','DejaVu Sans'],
                     'font.size':9,'svg.fonttype':'none','axes.unicode_minus':False,'axes.edgecolor':AXIS,
                     'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

rows = [r for r in csv.DictReader(open(ROOT/'assets/sweep/policy_device_sweep.csv'))]
for r in rows:
    for k in r:
        if k != 'insert': r[k] = float(r[k])
sel = lambda **kw: [r for r in rows if all(r[k] == v for k, v in kw.items())]
Ps = sorted({r['p'] for r in rows})

fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12.4, 4.7), facecolor=SURF)

# ---------- A: 같은 단위로 — p=1 대비 비율
ax.set_facecolor(SURF)
get = lambda pp, key: sel(area_mm2=600., insert='LIP', p=pp, q=0., B_R=19., beta=.28)[0][key]
red_max, fill_max = get(1.0,'hbm_reduction_pct'), get(1.0,'tier_fill_GB')
red  = [100*get(pp,'hbm_reduction_pct')/red_max for pp in Ps]
fill = [100*get(pp,'tier_fill_GB')/fill_max for pp in Ps]
ax.plot(Ps, red,  color=BLUE,   lw=2.8, marker='o', ms=7,   zorder=5)
ax.plot(Ps, fill, color=ORANGE, lw=2.8, marker='s', ms=6.5, zorder=5)
ax.text(0.42, 104.5, '이득  —  HBM 감소', fontsize=10.5, color=BLUE, fontweight='bold', ha='center')
ax.text(0.80, 60, '비용  —  티어 충전', fontsize=10.5, color=ORANGE, fontweight='bold', ha='center')
ax.fill_between(Ps, red, fill, color=TEAL, alpha=.09, zorder=1)
ax.annotate(f'p = 0.02 에서 이미 이득 {red[1]:.0f} %,\n그때 비용은 {fill[1]:.0f} % 뿐',
            xy=(0.03, 99), xytext=(0.33, 24), fontsize=9.6, color=INK, fontweight='bold', ha='center',
            arrowprops=dict(arrowstyle='->', color=INK, lw=1.1, connectionstyle='arc3,rad=-0.25'))
ax.text(0.33, 12, '두 선 사이가 버려지는 대역폭', fontsize=9.2, color=TEAL, fontweight='bold', ha='center')
ax.set_xlim(-0.03, 1.42); ax.set_ylim(-8, 112)
ax.set_xticks([0,.2,.4,.6,.8,1.0])
ax.set_xlabel('admission 확률  p   (미스 시 티어에 할당할 확률)')
ax.set_ylabel('항상 충전(p = 1) 대비  [%]')
ax.set_title('이득은 즉시 포화하고 비용만 선형으로 는다', fontsize=11, color=INK, pad=9, loc='left')
ax.grid(True, color=GRID, lw=.6); ax.set_axisbelow(True)

# ---------- B: speedup vs p, β 별 + 전량 고정 최적선
ax2.set_facecolor(SURF)
for beta, col in zip((0.05, 0.10, 0.28, 0.50, 1.00), RAMP):
    ys = [sel(area_mm2=600., insert='LIP', p=p, q=0., B_R=19., beta=beta)[0]['speedup_serial'] for p in Ps]
    ax2.plot(Ps, ys, color=col, lw=2.3, marker='o', ms=5.5, zorder=4)
    ax2.text(1.03, max(ys[-1], 0.33), f' β={beta:.2f}', fontsize=8.8, color=col, va='center', fontweight='bold')
opt = sel(area_mm2=600., insert='LIP', p=0., q=1., B_R=19., beta=.28)[0]['speedup_serial']
ax2.axhline(opt, color=INK, lw=2.4, ls=(0,(5,2.4)), zorder=6)
ax2.text(0.02, opt+0.018, f'전량 고정 (q=1) — {opt:.3f}, 충전 0, β 무관',
         fontsize=9.6, color=INK, fontweight='bold', va='bottom')
ax2.axhline(1.0, color=MUTED, lw=1.1, zorder=3)
ax2.text(1.0, 1.006, '티어 없음', fontsize=8.4, color=MUTED, ha='right', va='bottom')
ax2.set_xlim(-0.03, 1.42); ax2.set_ylim(0.3, 1.16)
ax2.set_xticks([0,.2,.4,.6,.8,1.0])
ax2.set_xlabel('admission 확률  p')
ax2.set_ylabel('speedup  (직렬 경계, B_R = 19 TB/s)')
ax2.set_title('최적점은 소자 파라미터 β 와 무관하게 한 점이다', fontsize=11, color=INK, pad=9, loc='left')
ax2.grid(True, color=GRID, lw=.6); ax2.set_axisbelow(True)

fig.text(.008, .012, '600 mm², C2 2층, 티어 3.297 GB · 32스텝 정상 상태, 시드 3개 평균 · LIP 삽입 · '
         't0 = 1.85 ms, B_HBM = 6.40 TB/s · β = B_W/B_R', fontsize=7.2, color=MUTED)
fig.tight_layout(rect=[0,.03,1,1])
for e in ('png','svg'): fig.savefig(ROOT/f'assets/figures/policy-device-sweep.{e}', dpi=200, facecolor=SURF)
print('assets/figures/policy-device-sweep.png')
