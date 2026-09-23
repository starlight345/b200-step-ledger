#!/usr/bin/env python3
"""Mixed read/write service model for a 3D SRAM tier, parameterized by write capability (2026-09-21).

Three layers, kept apart on purpose:
  Layer 1  DEVICE SOURCE (v2.0 deck): array peak 59.7 TB/s; read-oriented projection B_R = 17.7 TB/s
           (= 59.7 / 3.37, derate calibrated on H100 L2). Nothing about write or mixed traffic.
  Layer 2  ARCHITECTURE ASSUMPTIONS (ours, swept):
           beta = B_W / B_R        write (fill) capability relative to read
           organization            tag-first: hit -> read, miss -> fill        R = h*D, W = (1-h)*D
                                   parallel : every access reads data array   R = D,   W = (1-h)*D
           timing bound            serial (tier time adds) / overlapped (tier time hides under HBM)
           shared-port service     T_3D = R/B_R + W/B_W   ->  B_mix = D / T_3D
  Layer 3  WORKLOAD (our traces / structural constants): h = incremental hit rate = C / WS for decode.

The device team's Slack table (r = 1.0/0.8/0.6 -> 15/9.4/3.8) is NOT an input here. It is
re-expressed as the beta it implies, so it can be compared with the break-even beta.
Same model is applied to B200 L2 to show the criterion is not tier-specific.
"""
import os, sys, csv, math
sys.path.insert(0, os.path.dirname(__file__))
import sram_capacity_bandwidth_sweep as S
GB = 1e9; MB = 1e6
ROOT = os.path.join(os.path.dirname(__file__), '..')
B_R_DECK = 17.7            # canon: design_point_axes.read_delivery_cap_TBs (deck_320 scenario); see read_projection_TBs for the fabric cap
B_R_SLACK = 15.0           # deck x eta_sched 0.85 from the Slack reply (kept only for the implied-beta check)
B_L2 = 19.0                # Chips and Cheese, nominal
POINTS = [('C3 1층', 1390), ('C2 1층', 2110), ('C3 2층', 2780), ('C2 2층', 4220)]

def tier_traffic(h, org):
    return (h, 1.0-h) if org == 'tag-first' else (1.0, 1.0-h)      # (reads, writes) per logical byte

def b_mix(h, beta, B_R, org):
    R, W = tier_traffic(h, org)
    return 1.0/(R/B_R + W/(beta*B_R))

def step(mk, B, N, C, beta, B_R, org, bound, mode='cache'):
    c = S.CAL[mk]; obj, ws, T = S.workload(mk, B, N)
    t0, bh = c['t0_ms'], c['BW_eff_TBs']; h = min(1.0, C/ws) if C > 0 else 0.0
    base = t0 + T/GB/bh
    hbm = (1.0-h)*T/GB/bh
    if mode == 'pinned':
        tier = h*T/GB/B_R                     # reads only, r ~ 1
    else:
        R, W = tier_traffic(h, org); tier = (R*T/GB)/B_R + (W*T/GB)/(beta*B_R)
    st = t0 + (hbm + tier if bound == 'serial' else max(hbm, tier, T/GB/B_L2))
    return base/st, h

def breakeven_beta(mk, B, N, C, B_R, org, bound):
    """Smallest beta at which the cache stops losing to the no-tier baseline."""
    lo, hi = 0.01, 50.0
    if step(mk, B, N, C, hi, B_R, org, bound)[0] < 1.0: return float('inf')
    for _ in range(80):
        m = math.sqrt(lo*hi)
        if step(mk, B, N, C, m, B_R, org, bound)[0] >= 1.0: hi = m
        else: lo = m
    return hi

def implied_beta_from_slack():
    """If the Slack table were a shared-port model with B_R = 15, what beta would each row imply?"""
    out = {}
    for r, bw in ((0.8, 9.4), (0.6, 3.8)):
        inv_bw_w = (1.0/bw - r/B_R_SLACK)/(1.0-r)          # 1/B_W
        out[r] = (1.0/inv_bw_w)/B_R_SLACK
    return out


# ---------------------------------------------------------------------------
# Design-point-consistent read projection (added 2026-09-21).
# The deck's 17.7 TB/s is the 320 mm² array (2,664 macros x 22.4 GB/s = 59.7) after the H100-anchored
# 3.37x derate. Our capacity design point is C2, 800 mm² x 2 layers x 2 dies, which holds far more
# macros; there the array is not the limit, the fabric is. So
#     B_R(point) = min( array_peak(point) / derate , B_L2_SM )
# and at the GB-scale point this saturates at the L2->SM measurement (19 TB/s) when routed through L2.
# ---------------------------------------------------------------------------
MACRO_MM2 = {'C3': 0.120048, 'C2': 0.079254, 'C1': 0.056658}   # canon: device_3dsram.macro_area_mm2
MACRO_GBs = 128*1.4/8            # 22.4 GB/s per 1 Mb macro (deck)
DERATE = 59.7/17.7               # 3.37, H100-anchored (deck)

def array_peak_TBs(case, a_die_mm2, layers, dies):
    return a_die_mm2*layers*dies/MACRO_MM2[case]*MACRO_GBs/1000.0

def read_projection_TBs(case, a_die_mm2, layers, dies, bw_fabric=B_L2):
    peak = array_peak_TBs(case, a_die_mm2, layers, dies)
    return min(peak/DERATE, bw_fabric), peak

def beta_ceiling(h, B_R, org, bh):
    """beta at which the tier's time equals the HBM time in the overlapped bound; above it the cache
    is no longer the bottleneck and equals the pinned ceiling. Closed form from T_3D = (1-h)D/bh."""
    R, W = tier_traffic(h, org)
    rhs = B_R*(1.0-h)/bh - R          # (W/beta) must equal this
    return W/rhs if rhs > 0 else float('inf')

if __name__ == '__main__':
    mk, B, N = 'llama', 8, 2048
    c = S.CAL[mk]; bh = c['BW_eff_TBs']
    print("=== Layer 1 (덱): B_R = 17.7 TB/s 읽기 지향 투영. 쓰기·혼합은 없음. ===")
    print(f"=== 기준 HBM 유효 대역폭 (실측 회귀): {bh:.2f} TB/s ===\n")

    print("=== 설계점에 맞는 읽기 투영 B_R ===")
    for lbl, (case, a, L, d) in (('덱 320 mm² 1층 1다이', ('C3', 320, 1, 1)), ('C2 800 mm² 2층 2다이 (우리 용량 설계점)', ('C2', 800, 2, 2))):
        br, peak = read_projection_TBs(case, a, L, d)
        print(f"  {lbl:36s} 어레이 피크 {peak:7.1f} TB/s -> /3.37 = {peak/DERATE:6.1f} -> min(패브릭 19) = B_R {br:5.1f} TB/s  {'(어레이 한계)' if br < B_L2-1e-9 else '(패브릭 한계)'}")
    print("  GB급 설계점에서는 어레이가 아니라 L2->SM 패브릭이 읽기 전달의 상한이다. 17.7 은 320 mm² 어레이 숫자였다.\n")
    B_R_POINT, _ = read_projection_TBs('C2', 800, 2, 2)

    print("=== 본전 β (speedup = 1) 와 천장 β (고정 배치와 같아짐), 겹침 경계, C2 2층 4.22 GB ===")
    h = min(1.0, 4220*MB/S.workload(mk,B,N)[1])
    print(f"  {'B_R 기준':22s} {'구조':10s} {'본전 β':>7s} {'B_W':>7s} {'천장 β':>7s} {'B_W':>7s}")
    for br_lbl, br in (('17.7 (덱 320 mm²)', B_R_DECK), (f'{B_R_POINT:.1f} (패브릭, C2 설계점)', B_R_POINT)):
        for org in ('tag-first', 'parallel'):
            be = breakeven_beta(mk, B, N, 4220*MB, br, org, 'overlapped'); bc = beta_ceiling(h, br, org, bh)
            print(f"  {br_lbl:22s} {org:10s} {be:7.2f} {be*br:6.1f}T {bc:7.2f} {bc*br:6.1f}T")
    print("  본전은 손해를 멈추는 지점이고, 천장은 티어가 병목에서 벗어나 고정 배치 성능에 닿는 지점이다. 둘은 다르다.\n")

    print("=== 본전 β = B_W/B_R (이 값 이상이면 수요 충전 캐시가 티어 없는 기준선보다 느려지지 않는다) — 이하 표는 덱 17.7 기준 ===")
    print(f"{'설계점':8s} {'h':>6s} | {'겹침·tag-first':>14s} {'겹침·parallel':>13s} | {'직렬·tag-first':>14s} {'직렬·parallel':>13s}")
    for lbl, C in POINTS:
        row = [breakeven_beta(mk, B, N, C*MB, B_R_DECK, org, bd) for bd in ('overlapped', 'serial') for org in ('tag-first', 'parallel')]
        h = step(mk, B, N, C*MB, 1.0, B_R_DECK, 'tag-first', 'overlapped')[1]
        f = lambda v: ('불가' if v == float('inf') or v > 1.0 else f'{v:.2f}')
        print(f"{lbl:8s} {h*100:5.1f}% | {f(row[0]):>14s} {f(row[1]):>13s} | {f(row[2]):>14s} {f(row[3]):>13s}")
    print("  '불가' = β ≤ 1 (쓰기가 읽기보다 빠를 수 없다고 볼 때) 로는 본전 불가.")
    print("  겹침 경계에서 C2 2층 tag-first 는 β ≈ 0.30 이면 캐시가 HBM 을 따라간다. 이것이 소자팀에 물어야 할 스펙이다.\n")

    print("=== B_mix 와 speedup 을 β 로 스윕 (C2 2층 4.22 GB, 겹침 경계, tag-first) ===")
    print(f"{'β':>5s} {'B_W':>6s} {'B_mix':>7s} {'캐시 speedup':>12s} {'고정 배치':>9s}")
    pin = step(mk, B, N, 4220*MB, 1.0, B_R_DECK, 'tag-first', 'overlapped', mode='pinned')[0]
    for beta in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00):
        bm = b_mix(0.231, beta, B_R_DECK, 'tag-first'); sp = step(mk, B, N, 4220*MB, beta, B_R_DECK, 'tag-first', 'overlapped')[0]
        print(f"{beta:5.2f} {beta*B_R_DECK:6.2f} {bm:7.2f} {sp:12.3f} {pin:9.3f}")
    print("  β 가 문턱을 넘으면 캐시 speedup 이 고정 배치와 같아진다. 캐시가 나쁜 것이 아니라 β 가 낮을 때 나쁜 것이다.\n")

    ib = implied_beta_from_slack()
    print("=== 슬랙 표를 같은 모델로 읽으면 어떤 β 를 주장하는 셈인가 (B_R = 15) ===")
    for r, beta in ib.items():
        print(f"  r = {r}: BW = {dict(((0.8,9.4),(0.6,3.8)))[r]} TB/s  ->  implied β = {beta:.2f}  (B_W ≈ {beta*B_R_SLACK:.1f} TB/s)")
    print("  슬랙 표는 β ≈ 0.12~0.25 를 함의하고, 쓰기가 늘수록 더 떨어진다(뱅크 충돌 비선형). 본전 0.30 아래다.")
    print("  즉 소자팀 질문은 '3.8 이 맞나' 가 아니라 '쓰기/충전 능력이 읽기의 30% 를 넘는가' 로 바뀐다.\n")

    print("=== 같은 모델을 L2 에 적용 ('왜 L2 에는 관대한가' 의 답) ===")
    print(f"  decode 스트리밍 트래픽에서 L2 적중 ≈ 0 이므로 L2 는 순수 충전 경로다: B_mix,L2 = B_W,L2.")
    print(f"  실측 회귀가 {bh:.2f} TB/s 를 달성했으므로 L2 의 충전 능력은 최소 {bh:.2f} TB/s, 즉 β_L2 ≥ {bh/B_L2:.2f} (B_R,L2 = 19 기준).")
    print(f"  L2 는 같은 기준을 '측정으로' 통과한다. 3D 는 같은 기준을 β 로 물어야 한다.")

    rows = []
    for lbl, C in POINTS:
        for org in ('tag-first', 'parallel'):
            for bd in ('serial', 'overlapped'):
                for beta in [x/100 for x in range(5, 101, 5)]:
                    sp, h = step(mk, B, N, C*MB, beta, B_R_DECK, org, bd)
                    rows.append(dict(design_point=lbl, capacity_MB=C, hit_rate=h, organization=org, bound=bd, beta=beta,
                                     B_W_TBs=beta*B_R_DECK, B_mix_TBs=b_mix(h, beta, B_R_DECK, org), cache_speedup=sp,
                                     pinned_speedup=step(mk, B, N, C*MB, 1.0, B_R_DECK, org, bd, mode='pinned')[0]))
    p = os.path.join(ROOT, 'assets/sweep/cache_write_capability.csv')
    with open(p, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\nwrote {len(rows)} rows -> assets/sweep/cache_write_capability.csv")
