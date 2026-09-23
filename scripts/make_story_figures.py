#!/usr/bin/env python3
"""Composed slide-dominant figures for the storyline deck.

The lab's decks put ONE purpose-built figure on a slide and let short prose sit beside it,
with the quantities drawn on the figure itself rather than listed in cards. These are the
two beats that had no figure: the setup (where the decode step actually goes, and what the
screening rule concludes) and the duty cycle itself.
"""
import os, sys, math
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
sys.path.insert(0, os.path.dirname(__file__))
import ectc_thermal_model as M

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures')
BG, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'
plt.rcParams.update({'font.family':'sans-serif',
                     'font.sans-serif':['Apple SD Gothic Neo','AppleGothic','NanumGothic','Arial'],
                     'font.size':10,'svg.fonttype':'none','axes.edgecolor':AXIS,
                     'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

T0, TSTEP = 1.852, 4.515
MEMT = TSTEP - T0

# ------------------------------------------------------------------ setup + verdict
fig = plt.figure(figsize=(12.0, 4.3), facecolor=BG)
gs = fig.add_gridspec(1, 2, width_ratios=[1.35, 1.0], left=0.045, right=0.975,
                      top=0.92, bottom=0.13, wspace=0.22)

ax = fig.add_subplot(gs[0]); ax.set_facecolor(BG)
ax.text(0, 1.34, '토큰 하나마다 모델 전체를 읽는다', fontsize=14, color=INK, weight='bold')
ax.text(0, 1.14, f'weight {M.W_READ:.2f} GB  +  KV 2.15 GB  =  {M.D_STEP:.2f} GB / step',
        fontsize=11.5, color=INK2)
ax.text(0, 1.00, f'HBM 실질 {M.BW_HBM:.2f} TB/s 로 나누면  {MEMT:.2f} ms', fontsize=11.5, color=INK2)
ax.barh([0], [T0], color=MUTED, height=0.40, zorder=3)
ax.barh([0], [MEMT], left=T0, color=S2, height=0.40, zorder=3)
ax.text(T0/2, 0, f'{T0:.2f} ms', ha='center', va='center', color='white', fontsize=11.5, weight='bold', zorder=5)
ax.text(T0+MEMT/2, 0, f'{MEMT:.2f} ms', ha='center', va='center', color='white', fontsize=14, weight='bold', zorder=5)
ax.text(T0/2, 0.30, '연산 · 런치 · 지연', ha='center', fontsize=10.5, color=MUTED)
ax.text(T0+MEMT/2, 0.30, '메모리 대기', ha='center', fontsize=12.5, color=S2, weight='bold')
ax.text(T0+MEMT/2, 0.60, f'스텝의 {MEMT/TSTEP*100:.0f}%', ha='center', fontsize=24, color=S2, weight='bold')
ax.annotate('', xy=(0, -0.42), xytext=(TSTEP, -0.42),
            arrowprops=dict(arrowstyle='<->', color=INK2, lw=1.2))
ax.text(TSTEP/2, -0.56, f'decode 스텝 {TSTEP:.3f} ms   (실측 4.5556 ms)', ha='center',
        va='top', fontsize=11.5, color=INK)
ax.set_xlim(-0.05, TSTEP*1.02); ax.set_ylim(-0.95, 1.50); ax.axis('off')

ax2 = fig.add_subplot(gs[1]); ax2.set_facecolor(BG)
ax2.text(0.5, 9.5, '그런데 관행 스크리닝의 판정은', fontsize=13.5, color=INK, weight='bold', ha='center')
ax2.bar([0], [5.0], width=0.46, color=RED, zorder=4)
ax2.bar([1], [M.BW_HBM], width=0.46, color=MUTED, zorder=4)
ax2.text(0, 5.0+0.25, '5.0', ha='center', fontsize=26, color=RED, weight='bold')
ax2.text(1, M.BW_HBM+0.25, f'{M.BW_HBM:.2f}', ha='center', fontsize=26, color=INK, weight='bold')
ax2.text(0, -0.45, 'BW ≤ P / E 가 주는\n티어 대역폭\n(20 W ÷ 0.5 pJ/bit)', ha='center', va='top',
         fontsize=11, color=INK2)
ax2.text(1, -0.45, 'HBM 실질 대역폭\n\n[TB/s]', ha='center', va='top', fontsize=11, color=INK2)
ax2.annotate('', xy=(0.30, 5.6), xytext=(0.70, 6.9),
             arrowprops=dict(arrowstyle='<|-|>', color=RED, lw=1.6))
ax2.text(0.5, 7.4, '더 느리다', ha='center', fontsize=13, color=RED, weight='bold')
ax2.text(0.5, 8.6, '"지을 이유가 없다"', ha='center', fontsize=15, color=RED, weight='bold')
ax2.set_xlim(-0.65, 1.65); ax2.set_ylim(-3.6, 10.2); ax2.axis('off')

for ext in ('png','pdf'):
    fig.savefig(os.path.join(FIG, f'story-setup.{ext}'), dpi=230, facecolor=BG)
plt.close(fig)

# ------------------------------------------------------------------ duty timeline
C = M.capacity_GB(800.0, 2); d = M.duty(C); burst = M.burst_s(C)*1e3
fig = plt.figure(figsize=(12.0, 4.5), facecolor=BG)
ax = fig.add_axes([0.045, 0.58, 0.93, 0.36]); ax.set_facecolor(BG)
for k in range(3):
    x0 = k*TSTEP
    ax.add_patch(plt.Rectangle((x0, 0), TSTEP, 1, facecolor='#eeeeea', edgecolor=AXIS, lw=0.8, zorder=2))
    ax.add_patch(plt.Rectangle((x0, 0), burst, 1, facecolor=S2, edgecolor='none', zorder=3))
    ax.text(x0+TSTEP/2, -0.28, f'스텝 {k+1}', ha='center', fontsize=9.5, color=MUTED)
ax.annotate('', xy=(0, 1.35), xytext=(TSTEP, 1.35),
            arrowprops=dict(arrowstyle='<->', color=INK2, lw=1.1))
ax.text(TSTEP/2, 1.45, f'{TSTEP:.3f} ms', ha='center', fontsize=10.5, color=INK)
ax.annotate(f'티어가 일하는 구간  {burst:.3f} ms', xy=(burst/2, 1.02), xytext=(1.15, 2.05),
            fontsize=12.5, color=S2, weight='bold',
            arrowprops=dict(arrowstyle='-', color=S2, lw=1.2))
ax.set_xlim(-0.1, 3*TSTEP+0.1); ax.set_ylim(-0.45, 2.5); ax.axis('off')

axz = fig.add_axes([0.045, 0.14, 0.42, 0.28]); axz.set_facecolor(BG)
axz.add_patch(plt.Rectangle((0, 0), burst, 1, facecolor=S2, edgecolor='none'))
axz.add_patch(plt.Rectangle((burst, 0), TSTEP-burst, 1, facecolor='#eeeeea', edgecolor=AXIS, lw=0.8))
axz.text(burst/2, 1.25, f'{burst:.3f} ms', ha='center', fontsize=11, color=S2, weight='bold')
axz.text(burst + (TSTEP-burst)/2, 0.5, '쉰다', ha='center', va='center', fontsize=12, color=MUTED)
axz.text(0, -0.40, f'티어가 나르는 양  {M.f_red(C)*M.D_STEP:.2f} GB   (스텝 수요 {M.D_STEP:.2f} GB 의 {M.f_red(C)*100:.0f}%)',
         fontsize=11, color=INK, va='top')
axz.text(0, -0.72, f'÷ 전달 대역폭 {M.B_R:.0f} TB/s   =   {burst:.3f} ms',
         fontsize=11, color=INK2, va='top')
axz.set_xlim(-0.05, TSTEP*1.02); axz.set_ylim(-1.35, 1.6); axz.axis('off')

axr = fig.add_axes([0.55, 0.14, 0.42, 0.30]); axr.set_facecolor(BG); axr.axis('off')
axr.text(0, 1.02, f'{d*100:.2f}%', fontsize=50, color=S2, weight='bold', va='top')
axr.text(0.50, 0.96, '티어 듀티 사이클', fontsize=13.5, color=INK, weight='bold', va='top')
axr.text(0.50, 0.78, '정상 부하가 아니라\n스텝마다 한 번 터지는 버스트', fontsize=11.5, color=INK2, va='top')
axr.set_xlim(0, 1); axr.set_ylim(0, 1.08)

for ext in ('png','pdf'):
    fig.savefig(os.path.join(FIG, f'story-duty.{ext}'), dpi=230, facecolor=BG)
plt.close(fig)
print(f'duty {d*100:.2f}%  burst {burst*1000:.0f} us  step {TSTEP} ms  mem frac {MEMT/TSTEP*100:.0f}%')
print('wrote story-setup, story-duty')

# ------------------------------------------------------------------ duty envelope
import json
G5 = json.load(open(os.path.join(ROOT, 'assets', 'sweep', 'g5_operating_points.json')))['rows']
fig = plt.figure(figsize=(12.0, 4.6), facecolor=BG)
ax = fig.add_axes([0.075, 0.20, 0.52, 0.66]); ax.set_facecolor(BG)
G5 = sorted(G5, key=lambda r: r['demand_GB'])
dem = [r['demand_GB'] for r in G5]; dty = [r['duty']*100 for r in G5]
lab = [f"B={r['batch']} N={r['context']}" for r in G5]
ax.plot(dem, dty, color=S3, lw=2.4, marker='o', ms=9, mfc='white', mec=S3, mew=2.2, zorder=5)
for i, (x, y, l) in enumerate(zip(dem, dty, lab)):
    dy = 16 if i % 2 == 0 else -26      # alternate so neighbouring labels cannot collide
    ax.annotate(l, (x, y), textcoords='offset points', xytext=(0, dy),
                ha='center', fontsize=9.5, color=MUTED)
ax.set_ylim(0, 2.4); ax.set_xlim(14, 35)
ax.set_xlabel('스텝당 메모리 수요  [GB]', fontsize=11.5)
ax.set_ylabel('티어 듀티  [%]', fontsize=11.5)
ax.grid(True, color=GRID, lw=0.6, zorder=0)
ax.axhspan(min(dty), max(dty), color=S3, alpha=0.12, zorder=1)
ax.text(14.4, 1.95, f'듀티 {min(dty):.2f} ~ {max(dty):.2f}%', ha='left',
        va='center', fontsize=13, color=S3, weight='bold')
axt = fig.add_axes([0.63, 0.13, 0.35, 0.74]); axt.axis('off'); axt.set_xlim(0,1); axt.set_ylim(0,1)
axt.text(0, 0.98, '수요가 1.88배 늘어도', fontsize=14, color=INK, weight='bold', va='top')
axt.text(0, 0.86, '듀티는 5.1%만 움직인다', fontsize=14, color=S3, weight='bold', va='top')
axt.text(0, 0.46, 'burst = f · D / B_R', fontsize=12, color=INK, va='top')
axt.text(0, 0.36, 'step  ~ t0 + D / B_eff', fontsize=12, color=INK, va='top')
axt.text(0, 0.18, '같은 구조를 B200으로 옮기면 4.77%\n— 설계점 4.80%와 일치한다.',
         fontsize=12, color=S1, weight='bold', va='top')
for ext in ('png','pdf'):
    fig.savefig(os.path.join(FIG, f'story-envelope.{ext}'), dpi=230, facecolor=BG)
plt.close(fig)

# ------------------------------------------------------------------ T-3 margin
SNM, DV_SPAN = 155.0, 865.0
S_ax = np.linspace(0.04, 1.05, 300)
tol = SNM/S_ax
fig = plt.figure(figsize=(12.0, 4.8), facecolor=BG)
ax = fig.add_axes([0.075, 0.20, 0.50, 0.68]); ax.set_facecolor(BG)
ax.set_yscale('log')
# One message: the curve is what the cell can tolerate, the dashed line is what it gets,
# and the band where real 6T cells live sits entirely on the failing side of the crossing.
ax.axvspan(0.3, 1.0, color=RED, alpha=0.10, zorder=1)
ax.plot(S_ax, tol, color=INK, lw=2.6, zorder=5)
ax.axhline(DV_SPAN, color=RED, lw=2.2, ls=(0,(5,3)), zorder=6)
Sb = SNM/DV_SPAN
ax.plot([Sb], [DV_SPAN], marker='o', ms=12, mfc='white', mec=RED, mew=2.6, zorder=8)
ax.annotate(f'break-even  S = {Sb:.3f}', xy=(Sb, DV_SPAN), xytext=(0.52, 1800),
            fontsize=12.5, color=RED, weight='bold', ha='center',
            arrowprops=dict(arrowstyle='-', color=RED, lw=1.3))
ax.text(1.02, 960, '문헌이 주는 이동  865 mV', fontsize=11.5, color=RED, weight='bold',
        ha='right', va='top')
ax.text(0.052, 2700, '셀이 견딜 수 있는 한계', fontsize=11.5, color=INK, weight='bold')
ax.text(0.65, 62, '실제 6T 셀이 사는 구간\nS = 0.3 ~ 1.0', ha='center', fontsize=12,
        color=RED, weight='bold')
ax.set_xlim(0.04, 1.05); ax.set_ylim(50, 3600)
ax.set_xlabel('S  =  Vth 가 1 mV 움직일 때 잃는 읽기 마진 [mV]', fontsize=11.5)
ax.set_ylabel('견딜 수 있는 |dVth|  [mV]', fontsize=11.5)
ax.grid(True, which='both', color=GRID, lw=0.5, zorder=0)
axt = fig.add_axes([0.63, 0.13, 0.35, 0.76]); axt.axis('off'); axt.set_xlim(0,1); axt.set_ylim(0,1)
axt.text(0, 0.99, '덱의 read SNM은 155 mV', fontsize=13.5, color=INK, weight='bold', va='top')
axt.text(0, 0.87, '문헌의 온도 구동 Vth 이동은 865 mV', fontsize=13.5, color=INK, weight='bold', va='top')
axt.text(0, 0.72, '둘 사이를 잇는 값 S 를 아무도 주지 않았다.\n그래서 S 를 축으로 놓고 풀었다.',
         fontsize=11.5, color=INK2, va='top')
axt.text(0, 0.47, 'break-even S = 0.179', fontsize=14, color=RED, weight='bold', va='top')
axt.text(0, 0.37, '6T mismatch 전형값은 0.3 ~ 1.0 —\n한 자릿수 위다.', fontsize=12, color=RED, va='top')
for ext in ('png','pdf'):
    fig.savefig(os.path.join(FIG, f'story-t3.{ext}'), dpi=230, facecolor=BG)
plt.close(fig)
print('wrote story-envelope, story-t3')

# ------------------------------------------------------------------ the bracket
fig = plt.figure(figsize=(12.0, 4.4), facecolor=BG)
ax = fig.add_axes([0.055, 0.20, 0.60, 0.72]); ax.set_facecolor(BG)
ax.set_yscale('log')
vals = [('정상상태 관계식\n(관행 스크리닝)', 5.0, RED, '3.7배 과소'),
        ('검증값\n1D 솔버 = MAPDL', 18.6, S3, ''),
        ('단일 노드 럼프드\n(뻔한 보정)', 77.3, RED, '4.16배 과대')]
for i, (lab, v, col, tag) in enumerate(vals):
    ax.bar([i], [v], width=0.52, color=col, zorder=5)
    ax.text(i, v*1.10, f'{v:.1f}', ha='center', fontsize=25, color=col, weight='bold', zorder=6)
    ax.text(i, 0.62, lab, ha='center', va='top', fontsize=11.5, color=INK2, zorder=6)
    if tag:
        ax.text(i, v*0.55, tag, ha='center', fontsize=12.5, color='white', weight='bold', zorder=7)
ax.plot([-0.5, 2.40], [M.BW_HBM]*2, color=INK, lw=1.8, zorder=4)
ax.text(2.48, M.BW_HBM, f'  HBM 실질 {M.BW_HBM:.2f}', va='center', fontsize=11.5, color=INK)
ax.plot([-0.5, 2.40], [M.B_R]*2, color=S1, lw=1.6, ls=(0,(5,3)), zorder=4)
ax.text(2.48, M.B_R, f'  패브릭 상한 {M.B_R:.0f}', va='center', fontsize=11.5, color=S1)
ax.set_xlim(-0.55, 3.55); ax.set_ylim(0.6, 260)
ax.set_ylabel('전달 가능한 읽기 대역폭  [TB/s]', fontsize=11.5)
ax.set_xticks([]); ax.grid(True, axis='y', which='major', color=GRID, lw=0.6, zorder=0)
for sp in ('top','right','bottom'): ax.spines[sp].set_visible(False)

axt = fig.add_axes([0.685, 0.16, 0.30, 0.74]); axt.axis('off'); axt.set_xlim(0,1); axt.set_ylim(0,1)
axt.text(0, 0.98, '같은 소자, 같은 20 W,\n같은 0.5 pJ/bit', fontsize=13, color=INK, weight='bold', va='top')
axt.text(0, 0.76, '관행 두 가지가\n서로 다른 답을 준다', fontsize=15, color=INK, weight='bold', va='top')
axt.text(0, 0.24, '스택 시정수 6.8 ms\n티어는 4.5 ms 주기 안에서\n국소적으로 데워진다', fontsize=11.5, color=S2, weight='bold', va='top')
for ext in ('png','pdf'):
    fig.savefig(os.path.join(FIG, f'story-bracket.{ext}'), dpi=230, facecolor=BG)
plt.close(fig)
print('wrote story-bracket')
