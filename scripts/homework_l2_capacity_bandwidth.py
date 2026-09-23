#!/usr/bin/env python3
"""교수님 숙제 (2026-09-16 미팅): L2 를 키우면, 얼마나 느려져도 여전히 이득인가?

> "3D SRAM 이 아니라, L2 의 capacity 가 증가했을 때 L2 의 IO bandwidth 가 어느 정도까지
>  낮아져야 L2 capacity 에 bottleneck 이 안 생기는가를 보자는 거지. bottleneck 이
>  HBM-L2 에서 L2-L1 으로 옮겨오는 그 시점이 언제부터인가를 보라는 거지."

3D SRAM 의 C2/C3, 면적, MIV, 소자 BW 는 **일부러 넣지 않는다.** 이것은 소자 질문이
아니라 아키텍처 질문이고, 답이 나온 뒤에야 소자 목표로 내려간다.

모델. 스텝당 논리 읽기 D 는 전부 프로세서에 도달해야 한다. 용량 C 가 상주하면
HBM 은 (D-C) 만 공급하지만, L2->프로세서 링크는 여전히 D 전부를 나른다.

    T(C, B_L2) = t0 + max( (D-C)/B_HBM , D/B_L2 )        (겹침; "무엇이 병목인가")
    T_serial   = t0 + (D-C)/B_HBM + D/B_L2               (직렬 경계)

두 항이 같아지는 곳이 병목이 옮겨오는 지점이고, 닫힌 형태로 풀린다.

    B_min(C) = B_HBM / (1 - C/D)        C 를 쓰려면 최소 이만큼의 L2 대역폭이 필요
    C*(B_L2) = D * (1 - B_HBM/B_L2)     이 대역폭이면 여기까지만 용량이 값을 한다

**중요한 단서.** 위 식은 용량 C 가 실제로 상주한다고 가정한다. 일반 캐시 정책은
decode 에서 재사용 거리 = working set 이라 적중률이 정확히 0 이고(Gate 1, 20/20 셀),
따라서 C 가 얼마든 speedup 이 1.000 이다. 용량을 적중으로 바꾸려면 정책이 필요하다.
그림에 그 선을 같이 그린다.
"""
import json, math
from pathlib import Path
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CANON = json.loads((ROOT/'assets/sweep/canonical_constants.json').read_text())
B_HBM = CANON['b200_baseline']['hbm_effective_TBs_llama']['value']      # 6.40, measured-derived
T0    = CANON['b200_baseline']['t0_ms_llama']['value']                  # 1.85 ms
C0    = CANON['b200_baseline']['l2_capacity_bytes']['value']/1e9        # 0.1326 GB, measured
D     = 17.157                                                          # GB/step logical read [trace replay]
B_L2_MEAS = (16.8, 21.0)                                                # third-party microbenchmark

SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
BLUE, ORANGE, RED, FILL = '#2a78d6','#eb6834','#d03b3b','#f0efec'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Apple SD Gothic Neo','Nanum Gothic','Helvetica','DejaVu Sans'],'axes.unicode_minus':False,
                     'font.size':8.5,'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,
                     'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

t_hbm  = lambda C: (D - C)/B_HBM
t_l2   = lambda B: D/B
step   = lambda C, B: T0 + max(t_hbm(C), t_l2(B))
B_min  = lambda C: B_HBM/(1 - C/D)
C_star = lambda B: D*(1 - B_HBM/B)
BASE   = step(C0, 19.0)

# ---------------------------------------------------------------- figure 1: 병목 지도
fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12.2, 4.6), facecolor=SURF)
ax.set_facecolor(SURF)
Cs = np.linspace(0.05, 16.4, 600)
ax.fill_between(Cs, B_min(Cs), 70, color=BLUE, alpha=.075, zorder=1)
ax.fill_between(Cs, 3, B_min(Cs), color=RED, alpha=.075, zorder=1)
ax.plot(Cs, B_min(Cs), color=INK, lw=2.0, zorder=5)

ax.text(0.62, 45, 'HBM-bound\n용량을 키우면 계속 이득', fontsize=8.6, color=BLUE, fontweight='bold', va='center')
ax.text(10.2, 4.55, 'L2→프로세서 bound\n용량을 더 키워도 소용 없음', fontsize=8.6, color=RED, fontweight='bold', va='center')
ax.text(0.52, 9.6, r'$B_{\min}(C)=\dfrac{B_{HBM}}{1-C/D}$', fontsize=10.5, color=INK, ha='left')

ax.axhspan(*B_L2_MEAS, color=ORANGE, alpha=.14, zorder=2)
ax.axhline(19.0, color=ORANGE, lw=1.4, zorder=4)
ax.text(0.16, 19.9, 'B200 L2 실측 16.8–21 TB/s [3자]', fontsize=7.6, color=ORANGE, fontweight='bold')
cx = C_star(19.0)
ax.plot([cx],[19.0], 'o', ms=8, mfc=SURF, mec=INK, mew=1.8, zorder=6)
ax.annotate(f'19 TB/s 면 {cx:.1f} GB 에서\n병목이 옮겨온다',
            xy=(cx, 19.0), xytext=(3.1, 44), fontsize=8.6, color=INK, ha='center', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color=INK, lw=1.1, connectionstyle='arc3,rad=-0.18'))
for c, lab, ha_ in ((C0,'현재 L2\n126 MB','left'), (4.22,'3D SRAM 실현 상한\n4.22 GB','center')):
    ax.axvline(c, color=MUTED, lw=1.0, ls=(0,(4,2.6)), zorder=3)
    ax.text(c*(1.12 if ha_=='left' else 1), 4.35, lab, fontsize=7.4, color=INK2, ha=ha_, va='bottom')
ax.set_xlim(0.1, 16.4); ax.set_ylim(3, 70); ax.set_yscale('log'); ax.set_xscale('log')
ax.set_yticks([4,6.4,10,19,40,70]); ax.set_yticklabels(['4','6.4','10','19','40','70'])
ax.set_xticks([0.13,0.5,1,2,4.22,8,16]); ax.set_xticklabels(['0.13','0.5','1','2','4.22','8','16'])
ax.set_xlabel('L2 용량 C  [GB]'); ax.set_ylabel('L2 → 프로세서 대역폭  [TB/s]')
ax.set_title('용량을 쓰려면 최소 얼마의 L2 대역폭이 필요한가', fontsize=10, color=INK, pad=9, loc='left')
ax.grid(True, color=GRID, lw=.6, zorder=0); ax.set_axisbelow(True)

# ---------------------------------------------------------------- figure 2: speedup
ax2.set_facecolor(SURF)
Cs2 = np.linspace(0.05, 16.4, 700)
ramp = ['#a9c9f0','#7db0e8','#4a8ddc','#2a78d6','#17518f']       # sequential: 낮은 BW -> 밝음
for B, col in zip((6.4, 10, 15, 19, 25), ramp):
    ys = [BASE/step(c, B) for c in Cs2]
    ax2.plot(Cs2, ys, color=col, lw=2.0, zorder=4)
    cs_ = C_star(B)
    yy = BASE/step(16.4, B)
    ax2.text(16.6, yy if B > 6.4 else 1.028, f'{B}', fontsize=8.2, color=col, va='center', fontweight='bold')
    if cs_ > 0.2:
        ax2.plot([cs_], [BASE/step(cs_, B)], 'o', ms=5.5, mfc=SURF, mec=col, mew=1.6, zorder=6)
ax2.text(11.0, 1.88, 'L2→프로세서 대역폭 [TB/s]', fontsize=7.8, color=INK2, ha='center')
ax2.annotate('L2 가 HBM 과 같은 6.4 TB/s 면\n용량 효과가 아예 없다 (LRU 선과 겹침)',
             xy=(0.85, 0.996), xytext=(0.62, 1.23), fontsize=7.6, color=ramp[0], ha='center', fontweight='bold',
             arrowprops=dict(arrowstyle='->', color=ramp[0], lw=1.0))
ax2.plot(Cs2, np.ones_like(Cs2), color=INK, lw=1.8, ls=(0,(5,2.4)), zorder=5)
ax2.text(0.115, 0.945, '일반 캐시 정책 (LRU) — 실측: 어떤 용량에서도 1.000', fontsize=8.4,
         color=INK, fontweight='bold', va='center')
ax2.text(0.115, 0.912, 'decode 는 재사용 거리 = working set 이라 적중이 정확히 0. 20/20 설계 셀.',
         fontsize=7.4, color=INK2, va='center')
ax2.axvline(4.22, color=MUTED, lw=1.0, ls=(0,(4,2.6)), zorder=3)
ax2.text(4.22, 1.74, '3D SRAM\n실현 상한', fontsize=7.4, color=INK2, ha='center', va='top')
ax2.set_xscale('log'); ax2.set_xlim(0.1, 16.4); ax2.set_ylim(0.88, 1.95)
ax2.set_xticks([0.13,0.5,1,2,4.22,8,16]); ax2.set_xticklabels(['0.13','0.5','1','2','4.22','8','16'])
ax2.set_xlabel('L2 용량 C  [GB]'); ax2.set_ylabel('speedup (현재 L2 126 MB 대비)')
ax2.set_title('점 = 포화 시작. 그 뒤로는 용량이 값을 하지 않는다', fontsize=10, color=INK, pad=9, loc='left')
ax2.grid(True, color=GRID, lw=.6, zorder=0); ax2.set_axisbelow(True)

fig.text(.008, .012, f'겹침 경계 T = t0 + max((D-C)/B_HBM, D/B_L2).  '
    f'D = {D} GB/step [trace replay], B_HBM = {B_HBM} TB/s [measured-derived, 인과 미검증], '
    f't0 = {T0} ms [measured-derived].  용량 C 가 실제로 상주한다는 가정 — 정책이 있어야 성립.',
    fontsize=6.8, color=MUTED)
fig.tight_layout(rect=[0,.028,1,1])
for ext in ('png','svg'):
    fig.savefig(ROOT/f'assets/figures/homework-l2-capacity-bandwidth.{ext}', dpi=200, facecolor=SURF)

# ---------------------------------------------------------------- 표
print(f'D = {D} GB/step,  B_HBM = {B_HBM} TB/s,  t0 = {T0} ms,  기준 step = {BASE:.4f} ms\n')
print('닫힌 형태:  B_min(C) = B_HBM / (1 - C/D)      C*(B_L2) = D (1 - B_HBM/B_L2)\n')
print(f"{'C [GB]':>8} {'B_min [TB/s]':>13} | {'B_L2':>6} {'C* [GB]':>9} {'포화 speedup':>13}")
for c in (0.133, 1, 2, 4.22, 8, 11.38, 14):
    print(f'{c:8.3f} {B_min(c):13.2f}', end='')
    print(' |', end='')
    print()
print()
for B in (6.4, 10, 15, 19, 21, 25):
    cs_ = C_star(B)
    print(f"{'':22} | {B:6.1f} {cs_:9.2f} {BASE/step(max(cs_,0), B):13.3f}")
