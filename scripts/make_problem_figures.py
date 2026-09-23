#!/usr/bin/env python3
"""Problem 섹션 그림 3장. 제목이 주장하는 것을 그대로 보인다.
   "Capacity of SRAM is not an exact (HBM) traffic reduction."

  A  용량을 키워도 일반 캐시는 0 이다          (Gate 1, 20/20 셀)
  B  장부가 한쪽만 셌다 — 경계별 트래픽         (Gate 3b)  ★ 핵심
  C  그래서 요구 쓰기 대역폭이 폭발한다         (Gate 3b)  ★ 핵심
"""
import math
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT/'assets/figures'
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
BLUE, ORANGE, TEAL, RED = '#2a78d6','#eb6834','#1b9e77','#d03b3b'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Apple SD Gothic Neo','Helvetica','DejaVu Sans'],
                     'font.size':9,'svg.fonttype':'none','axes.unicode_minus':False,'axes.edgecolor':AXIS,
                     'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})
def save(fig, name):
    for e in ('png','svg'): fig.savefig(FIG/f'{name}.{e}', dpi=200, facecolor=SURF, bbox_inches='tight')
    print(f'  {name}.png')

# ========================================================== A. 용량만으론 0
areas = [400,500,600,700,800]
mgd = {'C2 2층':[12.00,15.00,18.00,21.00,24.00], 'C2 1층':[6.00,7.50,9.00,10.50,12.00],
       'C3 2층':[7.92,9.90,11.88,13.86,15.84], 'C3 1층':[3.96,4.95,5.94,6.93,7.92]}
fig, ax = plt.subplots(figsize=(7.4,4.5), facecolor=SURF); ax.set_facecolor(SURF)
for (lab, ys), col, lw in zip(mgd.items(), (BLUE,'#7fb0e6','#a9c9f0','#cfe0f7'), (2.4,2.0,2.0,2.0)):
    ax.plot(areas, ys, color=col, lw=lw, marker='o', ms=6, zorder=4)
    ax.text(812, ys[-1], f' {lab}', fontsize=8.4, color=col, va='center', fontweight='bold')
ax.axhline(-0.7455, color=INK, lw=2.6, ls=(0,(5,2.4)), zorder=5)
ax.text(404, 1.6, '일반 캐시 (LRU) — 전 20개 설계 셀에서 -0.75%, 분산 0.0000%p',
        fontsize=9.2, color=INK, fontweight='bold', va='bottom')
ax.text(404, -1.9, '면적을 400 -> 800 mm² 로 두 배 늘려도 한 자리도 안 변한다',
        fontsize=8.4, color=INK2, va='center')
ax.fill_between([390,880], -3, 0, color=INK, alpha=.045, zorder=1)
ax.set_xlim(390,880); ax.set_ylim(-3,26); ax.set_xticks(areas)
ax.set_xlabel('순배치 면적  [mm² / die / layer]'); ax.set_ylabel('HBM 논리 트래픽 감소  [%]')
ax.set_title('같은 용량, 다른 정책 — 용량은 스스로 이득이 되지 않는다', fontsize=11, color=INK, pad=10, loc='left')
ax.grid(True, color=GRID, lw=.6); ax.set_axisbelow(True)
save(fig, 'problem-a-capacity-alone')

# ========================================================== B. 경계별 트래픽 ★
pol = ['일반 캐시\n(LRU)','수요 충전\n(LIP)','미스에 비할당\n+ 즉시 반환','관리 상주\n(상한)']
hbm  = [17.158, 13.862, 13.861, 13.861]     # GB/step, 정상 상태
trd  = [0.000, 3.296, 3.297, 3.297]
twr  = [17.157, 13.862, 0.000, 0.000]
y = np.arange(len(pol))[::-1]; h = 0.24
fig, ax = plt.subplots(figsize=(9.6,4.6), facecolor=SURF); ax.set_facecolor(SURF)
for off, vals, col, lab in ((h, hbm, BLUE, 'HBM 읽기 (줄이려는 것)'),
                            (0, trd, TEAL, '티어 읽기 (실제 이득)'),
                            (-h, twr, ORANGE, '티어 쓰기 = 충전 (숨어 있던 것)')):
    ax.barh(y+off, vals, height=h*0.92, color=col, label=lab, zorder=4)
    for yy, v in zip(y+off, vals):
        ax.text(v+0.22, yy, f'{v:.2f}', fontsize=8.2, color=col if v else MUTED, va='center', fontweight='bold')
ax.set_yticks(y); ax.set_yticklabels(pol, fontsize=9.2)
ax.set_xlim(0, 20.6); ax.set_xlabel('정상 상태 트래픽  [GB / decode step]')
ax.set_title('HBM 만 세면 LIP 가 좋아 보인다. 티어 쓰기를 세면 뒤집힌다',
             fontsize=11, color=INK, pad=10, loc='left')
ax.legend(frameon=False, fontsize=8.6, loc='lower right', ncol=1, bbox_to_anchor=(1.0, -0.02))
ax.text(6.2, y[3]+h*1.7, '충전 막대가 아예 없다', fontsize=9.4, color=TEAL, fontweight='bold')
ax.annotate('쓰고 나서\n한 번도 안 읽는다', xy=(13.862, y[1]-h), xytext=(17.4, y[1]-h-0.30),
            fontsize=8.6, color=ORANGE, fontweight='bold', ha='center',
            arrowprops=dict(arrowstyle='->', color=ORANGE, lw=1.2))
ax.grid(True, axis='x', color=GRID, lw=.6); ax.set_axisbelow(True)
for s in ('top','right','left'): ax.spines[s].set_visible(False)
save(fig, 'problem-b-boundary-traffic')

# ========================================================== C. 요구 쓰기 대역폭 ★
labs = ['수요 충전 (LIP)\n직렬 경계','수요 충전 (LIP)\n겹침 경계','미스에 비할당\n+ 즉시 반환']
vals = [43.18, 5.57, 0.0]
fig, ax = plt.subplots(figsize=(8.2,4.4), facecolor=SURF); ax.set_facecolor(SURF)
cols = [RED, ORANGE, TEAL]
bars = ax.bar(range(3), [v if v else 0.55 for v in vals], width=.5, color=cols, zorder=4)
for i,(b,v) in enumerate(zip(bars, vals)):
    ax.text(b.get_x()+b.get_width()/2, (v if v else .55)+1.1,
            f'{v:.2f} TB/s' if v else '요구 없음', fontsize=11 if not v else 10.5,
            color=cols[i], ha='center', fontweight='bold')
ax.fill_between([-.5,2.5], 19, 48, color=RED, alpha=.06, zorder=1)
for yv, lab, col, xx, ha_, dy in ((17.7,'소자팀 덱 17.7',MUTED,-0.44,'left',-1.9),
                                  (19.0,'패브릭 상한 19',INK,2.44,'right',0.9)):
    ax.axhline(yv, color=col, lw=1.3, ls=(0,(4,2.6)), zorder=5)
    ax.text(xx, yv+dy, lab, fontsize=8.6, color=col, ha=ha_, fontweight='bold')
ax.text(1.72, 35, '존재하지 않는 영역', fontsize=11, color=RED, fontweight='bold', ha='center')
ax.text(1.72, 31.6, '덱에도 패브릭에도 이런 숫자는 없다', fontsize=8.8, color=RED, ha='center')
ax.set_xticks(range(3)); ax.set_xticklabels(labs, fontsize=9.2)
ax.set_ylim(0,48); ax.set_xlim(-.5,2.5); ax.set_ylabel('본전에 필요한 쓰기 대역폭  [TB/s]')
ax.set_title('충전을 세면 소자 요구가 폭발한다  (600 mm², B_R = 19 TB/s)',
             fontsize=11, color=INK, pad=10, loc='left')
ax.grid(True, axis='y', color=GRID, lw=.6); ax.set_axisbelow(True)
for s in ('top','right'): ax.spines[s].set_visible(False)
save(fig, 'problem-c-required-write-bw')
print('\n완료.')
