#!/usr/bin/env python3
"""Monochrome slide figures, in the reference deck's own drawing language.

The reference deck draws with unfilled rectangles (fill=BACKGROUND) and plain lines, and
its text is black. No colour fills, no accent palette. Emphasis comes from line weight,
hatching, a light grey wash, and bold text -- not from hue. These figures follow that.

Terms are defined on the figure where they first appear, rather than assumed.
"""
import os, sys, json
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
import ectc_thermal_model as M

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures')
K, GREY, LGREY = '#000000', '#666666', '#d9d9d9'
plt.rcParams.update({'font.family':'sans-serif',
                     'font.sans-serif':['Apple SD Gothic Neo','AppleGothic','Arial'],
                     'font.size':11, 'text.color':K,
                     'axes.edgecolor':K, 'axes.labelcolor':K,
                     'xtick.color':K, 'ytick.color':K, 'svg.fonttype':'none',
                     'axes.unicode_minus':False})

def box(ax, x, y, w, h, text='', fs=11.5, bold=False, lw=1.3, wash=False, ls='-'):
    ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=(LGREY if wash else 'none'),
                               edgecolor=K, lw=lw, linestyle=ls, zorder=3))
    if text:
        ax.text(x+w/2, y+h/2, text, ha='center', va='center', fontsize=fs,
                weight='bold' if bold else 'normal', zorder=5)

def arrow(ax, x1, y1, x2, y2, style='->', lw=1.2):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=K, lw=lw), zorder=4)

def canvas(w=12.0, h=4.6):
    fig = plt.figure(figsize=(w, h), facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, w); ax.set_ylim(0, h)
    ax.axis('off'); ax.set_facecolor('white')
    return fig, ax

T0, TSTEP = 1.852, 4.515
MEMT = TSTEP - T0
C = M.capacity_GB(800.0, 2); DUTY = M.duty(C); BURST = M.burst_s(C)*1e3

# ---------------------------------------------------------------- 1. setup
fig, ax = canvas(12.0, 4.4)
ax.text(0.30, 4.05, '한 스텝에서 읽는 바이트', fontsize=13, weight='bold')
ax.text(0.30, 3.70, f'weight {M.W_READ:.2f} GB  +  KV 2.15 GB  =  {M.D_STEP:.2f} GB', fontsize=12)
ax.text(0.30, 3.38, f'HBM 실질 {M.BW_HBM:.2f} TB/s 로 나누면  {MEMT:.2f} ms', fontsize=12)
X0, BW_, BY, BH = 0.30, 6.10, 2.15, 0.62
box(ax, X0, BY, BW_*T0/TSTEP, BH, f'{T0:.2f} ms', fs=12)
box(ax, X0+BW_*T0/TSTEP, BY, BW_*MEMT/TSTEP, BH, f'{MEMT:.2f} ms', fs=13, bold=True, wash=True)
ax.text(X0+BW_*T0/TSTEP/2, BY+BH+0.13, '연산·런치·지연', ha='center', fontsize=11, color=GREY)
ax.text(X0+BW_*(T0+MEMT/2)/TSTEP, BY+BH+0.13, '메모리 대기', ha='center', fontsize=12, weight='bold')
arrow(ax, X0, BY-0.28, X0+BW_, BY-0.28, '<->')
ax.text(X0+BW_/2, BY-0.62, f'decode 스텝  {TSTEP:.3f} ms   (실측 4.5556 ms)', ha='center', fontsize=12)
ax.text(X0+BW_+0.25, BY+BH/2, f'스텝의 {MEMT/TSTEP*100:.0f}% 가\n메모리 대기', va='center', fontsize=13, weight='bold')
ax.plot([8.45, 8.45], [0.35, 4.15], color=K, lw=0.8)
ax.text(8.75, 4.05, '관행 스크리닝의 판정', fontsize=13, weight='bold')
for i, (v, lab) in enumerate([(5.0, 'BW ≤ P / E\n(20 W ÷ 0.5 pJ/bit)'), (M.BW_HBM, 'HBM 실질')]):
    x = 9.05 + i*1.55; hgt = v/8.0*2.0
    box(ax, x, 1.55, 0.95, hgt, wash=(i == 1))
    ax.text(x+0.475, 1.55+hgt+0.14, f'{v:g}', ha='center', fontsize=20, weight='bold')
    ax.text(x+0.475, 1.38, lab, ha='center', va='top', fontsize=10.5)
ax.text(9.05, 0.68, '5.0 < 6.40  →  티어가 HBM 보다 느리다', fontsize=12.5, weight='bold')
ax.text(9.05, 0.32, '단위 [TB/s]', fontsize=10.5, color=GREY)
fig.savefig(os.path.join(FIG, 'bw-setup.png'), dpi=230, facecolor='white'); plt.close(fig)

# ---------------------------------------------------------------- 2. duty (with the definition)
fig, ax = canvas(12.0, 4.8)
box(ax, 0.30, 3.62, 11.4, 0.85, '', lw=1.3)
ax.text(0.52, 4.22, '정의', fontsize=12, weight='bold', va='center')
ax.text(1.25, 4.22, '듀티 (duty)  =  한 스텝 동안 티어가 실제로 데이터를 내보내는 시간의 비율', fontsize=13, va='center')
ax.text(1.25, 3.88, '= 티어가 나르는 바이트 ÷ 전달 대역폭 ÷ 스텝 시간', fontsize=11.5, va='center', color=GREY)
SX, SW, SY, SH = 0.30, 11.4, 2.28, 0.58
bw = SW/3*BURST/TSTEP
# the burst label sits directly over the first sliver with a short tick, so no leader
# line has to cross the definition box above or the arithmetic below
ax.plot([SX+bw/2, SX+bw/2], [SY+SH, SY+SH+0.16], color=K, lw=1.0, zorder=5)
ax.text(SX+bw/2+0.10, SY+SH+0.20, f'티어가 일하는 구간  {BURST:.3f} ms', fontsize=12, weight='bold')
for k in range(3):
    x0 = SX + k*SW/3
    box(ax, x0, SY, SW/3, SH)
    ax.add_patch(plt.Rectangle((x0, SY), bw, SH, facecolor=K, edgecolor=K, lw=0, zorder=4))
    ax.text(x0+SW/6, SY-0.40, f'스텝 {k+1}', ha='center', fontsize=10.5, color=GREY)
arrow(ax, SX, SY-0.22, SX+SW/3, SY-0.22, '<->')
ax.text(SX+SW/6, SY-0.20, f'{TSTEP:.3f} ms', ha='center', va='bottom', fontsize=11.5)
ax.text(0.30, 1.40, f'티어가 나르는 양   {M.f_red(C)*M.D_STEP:.2f} GB', fontsize=12.5)
ax.text(0.30, 1.08, f'(한 스텝 수요 {M.D_STEP:.2f} GB 의 {M.f_red(C)*100:.0f}%)', fontsize=11, color=GREY)
ax.text(0.30, 0.72, f'÷ 전달 대역폭 {M.B_R:.0f} TB/s   =   {BURST:.3f} ms', fontsize=12.5)
ax.text(0.30, 0.34, f'÷ 스텝 {TSTEP:.3f} ms', fontsize=12.5)
box(ax, 6.40, 0.30, 5.30, 1.45, '', lw=1.6)
ax.text(9.05, 1.20, f'듀티 = {DUTY*100:.2f}%', ha='center', fontsize=23, weight='bold')
ax.text(9.05, 0.62, '티어는 한 스텝의 95%를 쉰다', ha='center', fontsize=12.5)
fig.savefig(os.path.join(FIG, 'bw-duty.png'), dpi=230, facecolor='white'); plt.close(fig)
print('wrote bw-setup, bw-duty')

def axbox(fig, rect):
    ax = fig.add_axes(rect); ax.set_facecolor('white')
    for sp in ax.spines.values(): sp.set_color(K); sp.set_linewidth(1.0)
    ax.grid(True, color='#e6e6e6', lw=0.7, zorder=0)
    return ax

# ---------------------------------------------------------------- 3. envelope
G5 = sorted(json.load(open(os.path.join(ROOT,'assets','sweep','g5_operating_points.json')))['rows'],
            key=lambda r: r['demand_GB'])
fig = plt.figure(figsize=(12.0, 4.4), facecolor='white')
ax = axbox(fig, [0.075, 0.20, 0.52, 0.70])
dem=[r['demand_GB'] for r in G5]; dty=[r['duty']*100 for r in G5]
ax.plot(dem, dty, color=K, lw=1.8, marker='o', ms=9, mfc='white', mec=K, mew=1.8, zorder=5)
for i,(x,y,r) in enumerate(zip(dem,dty,G5)):
    ax.annotate(f"B={r['batch']} N={r['context']}", (x,y), textcoords='offset points',
                xytext=(0, 16 if i%2==0 else -26), ha='center', fontsize=9.5, color=GREY)
ax.set_ylim(0,2.4); ax.set_xlim(14,35)
ax.set_xlabel('한 스텝의 메모리 수요  [GB]', fontsize=11.5)
ax.set_ylabel('듀티  [%]', fontsize=11.5)
ax.text(14.5, 2.15, f'듀티 {min(dty):.2f} ~ {max(dty):.2f}%', fontsize=12.5, weight='bold')
axt = fig.add_axes([0.63, 0.16, 0.35, 0.74]); axt.axis('off'); axt.set_xlim(0,1); axt.set_ylim(0,1)
axt.text(0, 0.97, '수요가 1.88배 늘어도\n듀티는 5.1%만 움직인다', fontsize=14, weight='bold', va='top')
axt.text(0, 0.66, 'burst = f · D / B_R', fontsize=12, va='top')
axt.text(0, 0.55, 'step  = t0 + D / B_eff', fontsize=12, va='top')
axt.text(0, 0.40, '둘 다 수요 D 에 비례하므로\n나눌 때 상쇄된다', fontsize=11.5, va='top', color=GREY)
axt.text(0, 0.18, 'B200 으로 옮기면 4.77%\n설계점 4.80% 와 같다', fontsize=12.5, weight='bold', va='top')
fig.savefig(os.path.join(FIG,'bw-envelope.png'), dpi=230, facecolor='white'); plt.close(fig)

# ---------------------------------------------------------------- 4. bracket
fig = plt.figure(figsize=(12.0, 4.4), facecolor='white')
ax = axbox(fig, [0.075, 0.22, 0.56, 0.68]); ax.set_yscale('log')
ax.grid(True, which='both', color='#e6e6e6', lw=0.7, zorder=0)
for i,(lab,v,note_,wash) in enumerate([('정상상태 관계식\n(관행 스크리닝)',5.0,'3.7배 낮다',False),
                                       ('검증값\n1D 솔버 = MAPDL',18.6,'',True),
                                       ('단일 노드 럼프드\n(듀티만 보정)',77.3,'4.16배 높다',False)]):
    ax.bar([i],[v],width=0.5,facecolor=(LGREY if wash else 'white'),edgecolor=K,lw=1.6,zorder=5)
    ax.text(i, v*1.12, f'{v:.1f}', ha='center', fontsize=21, weight='bold', zorder=6)
    ax.text(i, 0.72, lab, ha='center', va='top', fontsize=11, zorder=6)
    if note_: ax.text(i, v*0.45, note_, ha='center', fontsize=11.5, zorder=7)
ax.plot([-0.5,2.42],[M.BW_HBM]*2,color=K,lw=1.4,zorder=4)
ax.text(2.50, M.BW_HBM, f' HBM 실질 {M.BW_HBM:.2f}', va='center', fontsize=11)
ax.plot([-0.5,2.42],[M.B_R]*2,color=K,lw=1.2,ls=(0,(5,3)),zorder=4)
ax.text(2.50, M.B_R, f' 패브릭 상한 {M.B_R:.0f}', va='center', fontsize=11)
ax.set_xlim(-0.55,3.6); ax.set_ylim(0.7,260); ax.set_xticks([])
ax.set_ylabel('전달 가능한 읽기 대역폭  [TB/s]', fontsize=11.5)
axt = fig.add_axes([0.66, 0.18, 0.32, 0.72]); axt.axis('off'); axt.set_xlim(0,1); axt.set_ylim(0,1)
axt.text(0, 0.96, '같은 소자, 같은 20 W,\n같은 0.5 pJ/bit', fontsize=13, weight='bold', va='top')
axt.text(0, 0.68, '관행 두 가지가\n서로 다른 답을 준다', fontsize=14, weight='bold', va='top')
axt.text(0, 0.42, '얇고 열전도가 낮은 티어가\n두꺼운 실리콘 위에 앉으면\n열 노드 하나로 볼 수 없다', fontsize=11.5, va='top')
axt.text(0, 0.16, '스택 시정수 6.8 ms\n티어는 4.5 ms 주기 안에서\n국소적으로 데워진다', fontsize=11.5, va='top', color=GREY)
fig.savefig(os.path.join(FIG,'bw-bracket.png'), dpi=230, facecolor='white'); plt.close(fig)

# ---------------------------------------------------------------- 5. verification
fig, ax = canvas(12.0, 4.4)
ax.text(0.30, 4.05, '같은 스택을 네 가지 경로로 확인했다', fontsize=13, weight='bold')
rows = [('해석해 1', '직렬 열저항', '0.07%'),
        ('해석해 2', '반무한 슬래브 스텝 응답', '2.30%'),
        ('Ansys MAPDL 26.1 · 1D', 'peak fraction 0.2693 대 0.2693', '0.02%'),
        ('Ansys MAPDL 26.1 · 3D', '균일 전력 0.848 K 대 0.836 K', '1.3%')]
y = 3.25
for a_, b_, c_ in rows:
    box(ax, 0.30, y, 3.3, 0.62, a_, fs=11.5)
    box(ax, 3.60, y, 5.6, 0.62, b_, fs=11.5)
    box(ax, 9.20, y, 2.5, 0.62, c_, fs=14, bold=True)
    y -= 0.72
ax.text(0.30, 0.22, '계수 자체도 따로 실측했다  —  문맥 손잡이 1.211 TB/s, 배치 손잡이 1.110 TB/s.', fontsize=12)
ax.text(0.30, -0.12, '같은 GPU 의 대역폭 프로브가 read 1.211 / copy 1.105 이므로 0.00% 와 0.42% 로 맞는다.', fontsize=12)
ax.set_ylim(-0.35, 4.4)
fig.savefig(os.path.join(FIG,'bw-verify.png'), dpi=230, facecolor='white'); plt.close(fig)
print('wrote bw-envelope, bw-bracket, bw-verify')

# ---------------------------------------------------------------- 6. sensitivity + mitigation
import csv
S1_ = list(csv.DictReader(open(os.path.join(ROOT,'assets','sweep','thermal_sensitivity.csv'))))
MT = list(csv.DictReader(open(os.path.join(ROOT,'assets','sweep','thermal_mitigation.csv'))))
NAME = {'a-IGZO k [W/m/K]':'소자(a-IGZO) 열전도도','BEOL effective k [W/m/K]':'BEOL 유효 열전도도',
        'inter-tier ILD [um]':'티어 간 절연막 두께','BEOL above tier [um]':'티어 위 BEOL 두께',
        'Si substrate [um]':'실리콘 기판 두께','tier count':'층수'}
rows=[r for r in S1_ if 'E/bit' not in r['parameter']]
rows.sort(key=lambda r: float(r['swing_frac']))
fig = plt.figure(figsize=(12.0, 4.6), facecolor='white')
ax = axbox(fig, [0.24, 0.20, 0.40, 0.68]); ax.grid(True, axis='x', color='#e6e6e6', lw=0.7, zorder=0)
BASE=18.57
for i,r in enumerate(rows):
    lo,hi=float(r['cap_low_TBs']),float(r['cap_high_TBs']); x0,x1=min(lo,hi),max(lo,hi)
    strong=(x1-x0)/BASE>0.25
    ax.barh(i, x1-x0, left=x0, height=0.52, facecolor=(LGREY if strong else 'white'),
            edgecolor=K, lw=1.3, zorder=4)
    ax.text(x1+0.6, i, f'{(x1-x0)/BASE*100:.0f}%', va='center', fontsize=11,
            weight='bold' if strong else 'normal')
ax.axvline(BASE, color=K, lw=1.4, zorder=5)
ax.set_yticks(range(len(rows))); ax.set_yticklabels([NAME.get(r['parameter'],r['parameter']) for r in rows], fontsize=11)
ax.set_xlim(7,33); ax.set_xlabel('전달 가능한 읽기 대역폭  [TB/s]', fontsize=11)
ax.text(BASE+0.5, len(rows)-0.4, f'기준 {BASE:.1f}', fontsize=10.5)
MN={'baseline, 4 tiers':'기준 (4층)','thinner inter-tier ILD, 300 -> 150 nm':'티어 간 절연막 300→150 nm',
    'higher-k ILD (2.5 -> 5.0 W/m/K)':'절연막 전도도 2.5→5.0','tier closer to Si: BEOL 8 -> 4 um':'티어를 Si 에 붙임 8→4 um',
    'thinned substrate 500 -> 200 um':'기판 박막화 500→200 um','higher-k ILD + BEOL 4 um combined':'위 두 가지 동시'}
ax2 = axbox(fig, [0.735, 0.20, 0.245, 0.68]); ax2.grid(True, axis='x', color='#e6e6e6', lw=0.7, zorder=0)
mt=MT[::-1]
for i,m in enumerate(mt):
    v=float(m['vs_base'])
    ax2.barh(i, v, height=0.54, facecolor=(LGREY if v>=1.35 else 'white'), edgecolor=K, lw=1.3, zorder=4)
    ax2.text(v+0.02, i, f'{v:.2f}배', va='center', fontsize=10.5, weight='bold' if v>=1.35 else 'normal')
ax2.axvline(1.0, color=K, lw=1.2, zorder=5)
ax2.set_yticks(range(len(mt))); ax2.set_yticklabels([MN.get(m['change'],m['change']) for m in mt], fontsize=9.5)
ax2.set_xlim(0.9,2.15); ax2.set_xlabel('완화 후 / 기준', fontsize=10.5)
fig.text(0.015, 0.95, '측정되지 않은 값을 각자 범위 전체로 흔들었을 때', fontsize=12, weight='bold')
fig.text(0.735, 0.95, '무엇으로 되찾을 수 있는가', fontsize=12, weight='bold')
import ebit_budget as B
_lo, _hi = B.budget(0)['total'], B.budget(1)['total']
fig.text(0.015, 0.045, f'* E/bit 는 축 밖이다: {_lo:.3f}~{_hi:.3f} pJ/bit 가 '
                       f'{M.bw_cap_TBs(20.0, _hi, 0.2693):.1f}~{M.bw_cap_TBs(20.0, _lo, 0.2693):.0f} TB/s 에 대응하므로 여전히 물어야 할 값이다.', fontsize=9.5, color=GREY)
fig.savefig(os.path.join(FIG,'bw-sensitivity.png'), dpi=230, facecolor='white'); plt.close(fig)

# ---------------------------------------------------------------- 7. E/bit budget
# Two bars, because the paper's point is which one is right: the steady-state rule's 0.391
# and the verified transient model's 1.434 (same 20 W, same HBM 6.40 TB/s). The pessimistic
# end is the macro-level 7 nm anchor at our 1 Mb macro size (ebit_budget.py, 2026-09-24).
import ebit_budget as B
lo_,hi_=B.budget(0)['total'],B.budget(1)['total']
bar=B.requirement(20,M.BW_HBM,1.0); bar_v=B.requirement(20,M.BW_HBM,0.2724)
fig, ax = canvas(12.0, 4.2)
ax.text(0.30, 3.85, '한 비트를 옮기는 데 쓸 수 있는 에너지  [pJ/bit]', fontsize=13, weight='bold')
L,R,Y,H2 = 0.60, 11.2, 1.85, 0.70
def px(v): return L + (np.log10(v)-np.log10(0.008))/(np.log10(2.5)-np.log10(0.008))*(R-L)
ax.plot([L,R],[Y,Y], color=K, lw=1.2)
for t in (0.01,0.03,0.1,0.3,1.0):
    ax.plot([px(t)]*2,[Y-0.10,Y],color=K,lw=1.0); ax.text(px(t),Y-0.30,f'{t:g}',ha='center',fontsize=10.5)
ax.add_patch(plt.Rectangle((px(lo_),Y+0.12),px(hi_)-px(lo_),H2,facecolor=LGREY,edgecolor=K,lw=1.4,zorder=4))
ax.text((px(lo_)+px(hi_))/2, Y+0.12+H2+0.16, f'만들 수 있는 범위  {lo_:.3f} ~ {hi_:.3f}',
        ha='center', fontsize=12.5, weight='bold')
ax.plot([px(bar)]*2,[Y+0.02,Y+1.55],color=K,lw=1.4,ls=(0,(4,2)),zorder=6)
ax.text(px(bar)-0.10, Y+1.58, f'정상상태 식 기준  {bar:.3f}', fontsize=11.5, va='bottom', ha='right')
ax.plot([px(bar_v)]*2,[Y+0.02,Y+1.55],color=K,lw=2.2,zorder=6)
ax.text(px(bar_v)-0.10, Y+1.58, f'검증 모델 기준  {bar_v:.3f}', fontsize=12.5, weight='bold', va='bottom', ha='right')
ax.text(px(bar)-0.10, Y+1.30, '(둘 다 20 W 에서 HBM 6.40 TB/s 를 내려면)', fontsize=10, va='bottom', ha='right', color=GREY)
ax.text(0.30, 0.95, f'=> 비관 코너 {hi_:.3f} 도 정상상태 기준 {bar:.3f} 아래다. 검증 모델 기준으로는 {bar_v/hi_:.1f}배 여유.',
        fontsize=13, weight='bold')
ax.text(0.30, 0.55, '   비관 끝 = 7 nm 1 Mb 매크로 읽기(주변회로 포함) × BEOL 6T 페널티 2배 + 수직 링크.  낙관 끝 = 5 nm HP 어레이 × 0.82.',
        fontsize=11)
ax.set_xlim(0,12); ax.set_ylim(0.2,4.2)
fig.savefig(os.path.join(FIG,'bw-ebit.png'), dpi=230, facecolor='white'); plt.close(fig)
print('wrote bw-sensitivity, bw-ebit')

# ---------------------------------------------------------------- 8. layers
import thermal_sensitivity as SENS
N = np.arange(1, 13)
Cs = np.array([M.capacity_GB(800.0, int(n), 2, 'C2') for n in N])
FR = np.array([M.f_red(c)*100 for c in Cs])
knee = next(int(n) for n, c in zip(N, Cs) if M.f_red(c) >= M.F_MAX-1e-9)
dT = [SENS.variant(n_tiers=int(n), beol_k=1.0)[1]*M.p_burst_W(0.5)/2.0 for n in N]
fig = plt.figure(figsize=(12.0, 4.3), facecolor='white')
ax = axbox(fig, [0.075, 0.20, 0.40, 0.68])
ax.plot(N, FR, color=K, lw=1.8, marker='o', ms=7, mfc='white', mec=K, mew=1.6, zorder=5)
ax.axhline(M.F_MAX*100, color=K, lw=1.1, ls=(0,(4,2)), zorder=4)
ax.axvline(knee, color=K, lw=1.4, zorder=4)
ax.text(knee+0.25, 20, f'{knee}층에서 포화', fontsize=11.5, weight='bold')
ax.text(1.2, M.F_MAX*100+2.5, f'{M.F_MAX*100:.1f}%  (weight 스트림을 다 덮음)', fontsize=10.5)
ax.set_xlim(0.5,12.5); ax.set_ylim(0,100)
ax.set_xlabel('쌓은 층수', fontsize=11.5); ax.set_ylabel('HBM 트래픽 감소  [%]', fontsize=11.5)
ax2 = axbox(fig, [0.575, 0.20, 0.40, 0.68])
ax2.plot(N, dT, color=K, lw=1.8, marker='s', ms=6, mfc='white', mec=K, mew=1.6, zorder=5)
ax2.axhline(10.0, color=K, lw=1.1, ls=(0,(4,2)), zorder=4)
ax2.text(1.2, 10.35, '예시 여유 10 K', fontsize=10.5)
ax2.axvline(knee, color=K, lw=1.4, zorder=4)
ax2.set_ylim(0, 12.5); ax2.set_xlim(0.5,12.5)
ax2.set_xlabel('쌓은 층수', fontsize=11.5); ax2.set_ylabel('티어 자체 온도 상승  [K]', fontsize=11.5)
ax2.text(6.8, 1.35, '최악 조건에서도 0.43 K', fontsize=11.5, weight='bold', ha='center')
fig.text(0.075, 0.945, '이득은 층수에 따라 늘다가 멈춘다', fontsize=12, weight='bold')
fig.text(0.575, 0.945, '그런데 열은 층수와 거의 무관하다', fontsize=12, weight='bold')
fig.savefig(os.path.join(FIG,'bw-layers.png'), dpi=230, facecolor='white'); plt.close(fig)

# ---------------------------------------------------------------- 9. hotspot
MAPDL=[(4000.0,0.8476753),(1000.0,6.220460),(500.0,18.02689),(200.0,96.93106),(100.0,425.4633)]
frac=np.array([ (l/4000.0)**2*100 for l,_ in MAPDL]); Tp=np.array([t for _,t in MAPDL])
fig = plt.figure(figsize=(12.0, 4.3), facecolor='white')
ax = axbox(fig, [0.075, 0.20, 0.50, 0.68]); ax.set_xscale('log'); ax.set_yscale('log')
ax.grid(True, which='both', color='#e6e6e6', lw=0.7, zorder=0)
ax.plot(frac, Tp, color=K, lw=1.8, marker='o', ms=8, mfc='white', mec=K, mew=1.7, zorder=5)
ax.plot([100],[0.8363], marker='s', ms=10, mfc=K, mec=K, zorder=7)
ax.axhline(10.0, color=K, lw=1.1, ls=(0,(4,2)), zorder=4)
ax.text(0.048, 11.8, '예시 여유 10 K', fontsize=10.5)
for f_,t_,l_,dx,dy in [(frac[4],Tp[4],100.0,14,-2),(frac[1],Tp[1],1000.0,14,6)]:
    ax.annotate(f'한 변 {l_/1000:g} mm 만 켠 경우', (f_,t_), textcoords='offset points',
                xytext=(dx,dy), fontsize=10.5)
ax.set_xticks([0.0625,0.25,1.5625,6.25,100.0])
ax.set_xticklabels(['0.06','0.25','1.6','6.3','100'])
ax.set_xlim(0.04,200); ax.set_ylim(0.4,900)
ax.set_xlabel('버스트 동안 실제로 켜지는 티어 면적의 비율  [%]', fontsize=11)
ax.set_ylabel('티어 최고 온도 상승  [K]', fontsize=11.5)
axt = fig.add_axes([0.62, 0.18, 0.36, 0.72]); axt.axis('off'); axt.set_xlim(0,1); axt.set_ylim(0,1)
axt.text(0, 0.96, '전력 총량은 같게 두고\n켜지는 면적만 줄였다', fontsize=13, weight='bold', va='top')
axt.text(0, 0.70, '전면(100%)  0.848 K\n1D 솔버와 1.3% 로 같다', fontsize=12, va='top')
axt.text(0, 0.46, '한 변 0.1 mm 만 켜면  425 K\n502배', fontsize=12.5, weight='bold', va='top')
axt.text(0, 0.24, 'decode 는 상주 weight 를\n전 매크로에서 읽으므로\n전면 쪽이 실제 동작점이다', fontsize=11.5, va='top')
fig.savefig(os.path.join(FIG,'bw-hotspot.png'), dpi=230, facecolor='white'); plt.close(fig)

# ---------------------------------------------------------------- 10. T-3 (closed)
import csv as _csv
SM=list(_csv.DictReader(open(os.path.join(ROOT,'assets','sweep','t3_sigma_margin.csv'))))
fig = plt.figure(figsize=(12.0, 4.3), facecolor='white')
ax = axbox(fig, [0.135, 0.22, 0.44, 0.60])
ax.axvspan(0.3, 1.0, facecolor=LGREY, edgecolor='none', zorder=1)
ax.text(0.65, -0.95, '실제 6T 셀이 사는 구간  0.3 ~ 1.0', ha='center', fontsize=11, weight='bold')
ys=range(len(SM))
for y,r in zip(ys,SM):
    v=float(r['S_max'])
    ax.barh(y, v, height=0.52, facecolor='none', edgecolor=K, lw=1.5, zorder=5)
    ax.text(v+0.02, y, f"{v:.2f}", va='center', fontsize=10.5, zorder=6)
ax.set_yticks(list(ys))
ax.set_yticklabels([f"σ={float(r['sigma_mV']):.0f} mV,  k={r['k']}" for r in SM], fontsize=10.5)
ax.invert_yaxis(); ax.set_xlim(0, 1.25); ax.set_ylim(len(SM)-0.45, -1.35)
ax.set_xlabel('셀이 감당할 수 있는 최대 S', fontsize=11.5)
fig.text(0.135, 0.945, '공개된 σ 로 다시 풀면', fontsize=12, weight='bold')
axt = fig.add_axes([0.62, 0.14, 0.36, 0.78]); axt.axis('off'); axt.set_xlim(0,1); axt.set_ylim(0,1)
axt.text(0, 0.99, '물어야 한다던 그 값이\n이미 공개돼 있었다', fontsize=13, weight='bold', va='top')
axt.text(0, 0.79, 'σ(V_TH-ON) = 20 ~ 40 mV\n300 mm 라인, >100 소자 무고장\nL_CH 120 nm 까지', fontsize=11.5, va='top')
axt.text(0, 0.56, '웨이퍼 스케일 측정이라\n국소 편차의 상한이다 — 보수적이다.', fontsize=11, va='top')
axt.text(0, 0.40, '4.22 GB 어레이는 7.20 σ 가 필요하다.', fontsize=11, va='top')
axt.text(0, 0.27, '경계가 실제 6T 구간 안으로 들어왔다.', fontsize=12, weight='bold', va='top')
axt.text(0, 0.145, '=> 열린 전제가 아니라 두 숫자의 문제다.\n     이 셀의 S, 그리고 σ 가 온도로\n     얼마나 커지는가.', fontsize=11.5, weight='bold', va='top')
fig.savefig(os.path.join(FIG,'bw-t3.png'), dpi=230, facecolor='white'); plt.close(fig)

# ---------------------------------------------------------------- 11. model order
MO=list(_csv.DictReader(open(os.path.join(ROOT,'assets','sweep','model_order.csv'))))
lump=[r for r in MO if r['nodes'].startswith('lumped')]; body=[r for r in MO if not r['nodes'].startswith('lumped')]
N=[int(r['N']) for r in body]; E=[float(r['rel_error'])*100 for r in body]
fig = plt.figure(figsize=(12.0, 4.3), facecolor='white')
ax = axbox(fig, [0.075, 0.20, 0.50, 0.66]); ax.set_xscale('log'); ax.set_yscale('log')
ax.grid(True, which='both', color='#ededed', lw=0.7, zorder=0)
ax.plot(N, E, color=K, lw=1.8, marker='o', ms=7, mfc='white', mec=K, mew=1.6, zorder=5)
for r in lump:
    ax.plot([1],[float(r['rel_error'])*100], marker='s', ms=10, mfc=K, mec=K, zorder=7)
ax.annotate('1노드 럼프드\n(4.2 ~ 4.8배 낙관)', xy=(1, 78), xytext=(1.25, 200),
            fontsize=11, weight='bold', arrowprops=dict(arrowstyle='-', color=K, lw=1.1))
ax.axhline(5.0, color=K, lw=1.2, ls=(0,(4,2)), zorder=4)
ax.text(1.1, 6.0, '5%', fontsize=11)
ax.annotate('10노드에서 5% 아래', xy=(10, 3.82), xytext=(22, 12.0), fontsize=11.5, weight='bold',
            arrowprops=dict(arrowstyle='-', color=K, lw=1.1))
ax.set_xlim(0.8, 200); ax.set_ylim(0.005, 600)
ax.set_xticks([1,10,100]); ax.set_xticklabels(['1','10','100'])
ax.set_yticks([0.01,0.1,1,10,100]); ax.set_yticklabels(['0.01','0.1','1','10','100'])
ax.minorticks_off()
ax.set_xlabel('모델 차수  —  노드 개수', fontsize=11.5)
ax.set_ylabel('검증 해 대비 오차  [%]', fontsize=11.5)
axt = fig.add_axes([0.62, 0.16, 0.36, 0.74]); axt.axis('off'); axt.set_xlim(0,1); axt.set_ylim(0,1)
axt.text(0, 0.99, '솔버는 그대로 두고\n메시 차수만 바꿨다', fontsize=13, weight='bold', va='top')
axt.text(0, 0.79, '1노드는 τ 를 정답으로 받아도\n4.16배 낙관한다.\n기하에서 쌓으면 4.83배.', fontsize=11.5, va='top')
axt.text(0, 0.55, '그런데 고치는 길은 해상도가 아니다.', fontsize=11.5, weight='bold', va='top')
axt.text(0, 0.44, '물리 층 8개를 8노드로만 둬도 25%,\n10노드면 3.8% 다.', fontsize=11.5, va='top')
axt.text(0, 0.24, '1노드가 틀리는 이유는 위상이다 —\n50 nm 티어를 500 um 실리콘과\n한 덩어리로 묶었다.', fontsize=11, va='top')
axt.text(0, 0.055, '=> 축약 모델은 10노드면 된다.\n     조건은 티어와 기판의 분리.', fontsize=12, weight='bold', va='top')
fig.savefig(os.path.join(FIG,'bw-order.png'), dpi=230, facecolor='white'); plt.close(fig)

# ---------------------------------------------------------------- 12. corners
CO=list(_csv.DictReader(open(os.path.join(ROOT,'assets','sweep','uncertainty_corners.csv'))))
caps=sorted(float(r['cap_TBs']) for r in CO)
fig = plt.figure(figsize=(12.0, 4.3), facecolor='white')
ax = axbox(fig, [0.075, 0.20, 0.50, 0.66])
ax.bar(range(len(caps)), caps, width=0.78, facecolor='none', edgecolor=K, lw=1.0, zorder=5)
ax.axhline(M.BW_HBM, color=K, lw=1.9, zorder=6)
ax.text(len(caps)-0.5, M.BW_HBM-1.9, f'HBM 실질 {M.BW_HBM:.2f} — 이 아래면 지을 이유가 없다',
        ha='right', va='top', fontsize=11, weight='bold')
ax.axhline(18.57, color=K, lw=1.1, ls=(0,(4,2)), zorder=6)
ax.text(0.3, 19.6, '공칭 18.57', fontsize=10.5)
ax.annotate(f'최악 {caps[0]:.2f}', xy=(0, caps[0]), xytext=(2.6, 12.5), fontsize=11.5,
            weight='bold', arrowprops=dict(arrowstyle='-', color=K, lw=1.1))
ax.set_xlim(-1, len(caps)); ax.set_ylim(0, 42)
ax.set_xlabel('32개 코너  —  미측정량 다섯 개를 양 끝으로 조합', fontsize=11.5)
ax.set_ylabel('허용 대역폭  [TB/s]', fontsize=11.5)
axt = fig.add_axes([0.62, 0.16, 0.36, 0.74]); axt.axis('off'); axt.set_xlim(0,1); axt.set_ylim(0,1)
axt.text(0, 0.99, '스택을 우리가 잰 게 아니라면,\n전부 틀렸다고 해보자', fontsize=13, weight='bold', va='top')
axt.text(0, 0.76, 'IGZO k, BEOL k, ILD 두께,\nBEOL 두께, 기판 두께 —\n선언된 범위의 양 끝만 조합', fontsize=11.5, va='top')
axt.text(0, 0.52, '32 / 32 가 바닥을 넘는다.', fontsize=13, weight='bold', va='top')
axt.text(0, 0.40, '최악에서도 1.17배 여유 —\n얇지만 E/bit 0.5 라는 보수적 값에서다.', fontsize=11, va='top')
axt.text(0, 0.20, '=> 물성이 정하는 것은 여유의 크기이지\n     여유의 유무가 아니다.\n     그래서 점이 아니라 구간을 보고한다.', fontsize=11.5, weight='bold', va='top')
fig.savefig(os.path.join(FIG,'bw-corners.png'), dpi=230, facecolor='white'); plt.close(fig)
print('wrote bw-t3 (closed), bw-order, bw-corners')

# ---------------------------------------------------------------- 13. MAPDL evidence
from PIL import Image, ImageChops
import numpy as _np
MP = os.path.join(ROOT, 'assets', 'mapdl', 'png')

def _model_crop(name, pad=14):
    """Crop to the rendered MODEL only.

    An autocrop of the raw PNG keeps MAPDL's header text and the colour bar, which span
    nearly the full canvas and leave the geometry a few percent of the frame. The model
    is the only strongly-chromatic region, so select saturated pixels and drop the bottom
    band where the colour bar lives."""
    im = Image.open(os.path.join(MP, name)).convert('RGB')
    a = _np.asarray(im).astype(int)
    sat = a.max(2) - a.min(2)
    mask = sat > 45
    mask[int(mask.shape[0]*0.80):, :] = False        # colour bar band
    ys, xs = _np.where(mask)
    y0, y1 = max(ys.min()-pad, 0), min(ys.max()+pad, a.shape[0])
    x0, x1 = max(xs.min()-pad, 0), min(xs.max()+pad, a.shape[1])
    return im.crop((x0, y0, x1, y1))

panels = [('plot_full002.png',  1.0, 'a.  세운 모델',
           'SOLID70 육면체 54,400개\n두께의 89%가 Si 500 um 라 BEOL 은 맨 위 몇 픽셀이다'),
          ('rep_kxy10001.png',  0.34, 'b.  349 W 로직 위에 얹으면',
           '싱크쪽 93.6 → 티어 100.01 °C\n티어 자기발열은 7.5 mK'),
          ('plot_100um004.png', 1.0, 'c.  한 변 0.1 mm 로 모으면',
           '옆으로 못 퍼진다\n같은 전력에 피크 425 K')]
FW, FH = 13.0, 4.8
fig = plt.figure(figsize=(FW, FH), facecolor='white')
# Panels a and c are portrait, so headings placed ABOVE the row cost more height than the
# pictures can spare in a 2.6:1 band. Captions go underneath instead and the band takes
# the rest, which roughly doubles the rendered size of each panel.
BOT, BANDH = 0.235, 0.715
ims = []
for fn, xf, _, _ in panels:
    im = _model_crop(fn)
    if xf < 1.0: im = im.crop((0, 0, int(im.width*xf), im.height))   # laterally uniform
    ims.append(im)
AVAIL, GAPMIN = 0.90, 0.055
wfr = [BANDH*(FH/FW)*(im.width/im.height) for im in ims]
if sum(wfr) + GAPMIN*(len(ims)-1) > AVAIL:
    BANDH *= (AVAIL - GAPMIN*(len(ims)-1))/sum(wfr)
    wfr = [BANDH*(FH/FW)*(im.width/im.height) for im in ims]
gap = max(GAPMIN, (AVAIL - sum(wfr))/(len(ims)-1))
x = (1.0 - (sum(wfr) + gap*(len(ims)-1)))/2.0
for im, w, (fn, xf, head, sub) in zip(ims, wfr, panels):
    ax = fig.add_axes([x, BOT, w, BANDH])
    ax.imshow(im); ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values(): sp.set_edgecolor(K); sp.set_linewidth(1.3)
    fig.text(x, 0.195, head, fontsize=12.5, weight='bold', va='top')
    fig.text(x, 0.128, sub, fontsize=10, va='top', linespacing=1.5)
    x += w + gap
fig.text(0.012, 0.018, 'Ansys Mechanical APDL 26.1  ·  정상상태 전도  ·  쿼터 대칭, 측면 단열  ·  '
                       '싱크는 h = 8187 W/m²K 대류(접합 100 °C 동작점에 캘리브레이션)',
         fontsize=9, color=GREY)
fig.savefig(os.path.join(FIG,'bw-mapdl.png'), dpi=230, facecolor='white'); plt.close(fig)
print('wrote bw-mapdl')

# ---------------------------------------------------------------- 14. AEDT cross-check evidence
# Ansys Electronics Desktop 2026 R1, Icepak FEA, run on the lab PC over Chrome Remote Desktop
# (scripts/aedt/). AEDT's graphics area does not paint in that session -- neither the remote
# viewer nor a capture taken on the Windows side shows it -- so the contour pictures are AEDT's
# own offscreen renders (ExportModelImageToFile), and the full-window capture shows what does
# paint: the project tree, the mesh statistics and the result messages. Crops only.
AE = os.path.join(ROOT, 'assets', 'aedt')
gui = Image.open(os.path.join(AE, 'aedtgui.png')).convert('RGB')
gui.crop((0, 0, gui.width, 1032)).save(os.path.join(FIG, 'aedt-gui.png'))   # drop the taskbar
panels = [('aedtsurfiso.png', 1130, 'a.  스택 전체', '싱크 93.6 → 티어 100.03 °C'),
          ('aedttiertop.png', 1170, 'b.  티어 평면', 'L자 주변회로 100.000 → 100.031 °C')]
ims = [Image.open(os.path.join(AE, f)).convert('RGB').crop((0, 0, w, 1000)) for f, w, _, _ in panels]
FW, FH = 8.6, 4.3
fig = plt.figure(figsize=(FW, FH), facecolor='white')
BOT, BANDH, GAP = 0.20, 0.78, 0.03
wfr = [BANDH*(FH/FW)*(im.width/im.height) for im in ims]
x = (1.0 - (sum(wfr) + GAP))/2.0
for im, w, (_, _, head, sub) in zip(ims, wfr, panels):
    ax = fig.add_axes([x, BOT, w, BANDH]); ax.imshow(im); ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values(): sp.set_edgecolor(K); sp.set_linewidth(1.2)
    fig.text(x, 0.155, head, fontsize=12, weight='bold', va='top')
    fig.text(x, 0.075, sub, fontsize=10.5, va='top')
    x += w + GAP
fig.savefig(os.path.join(FIG, 'aedt-field.png'), dpi=230, facecolor='white'); plt.close(fig)
print('wrote aedt-gui, aedt-field')
