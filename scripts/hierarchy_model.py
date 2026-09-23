#!/usr/bin/env python3
"""Memory-hierarchy model for a 3D SRAM tier on a B200-class GPU (2026-09-20).

Replaces the single vague "fabric 20 TB/s" with three named links, each with a
stated provenance:

    L1  HBM -> L2      peak 8.0 TB/s   [NVIDIA B200 spec]
                       eff  6.40 TB/s  [our fit to measured B200 decode medians;
                                        the replay regression in memory.html
                                        independently gives 6.51 TB/s]
    L2  L2 -> SM       17-21 TB/s      [Chips and Cheese B200 microbenchmark:
                                        ~21 local partition, ~16.8 cross-partition.
                                        NVIDIA publishes no single figure.]
    L3  3D SRAM -> SM  5 / 9.4 / 15    [device team 2026-09-20: BW(r) for read
                                        share 0.6 / 0.8 / 1.0; 5 = thermal cap at
                                        0.5 pJ/bit and 20 W]

L2 capacity is 126 MB [NVIDIA Blackwell tuning guide].

The point of this file is the ABSTRACTION LADDER. Each rung adds one physical
effect and we report what it does to the answer, so the paper can state how much
modeling fidelity the question actually requires.

    M0  capacity only, pure roofline        speedup = 1/(1-coverage)
    M1  + fixed non-traffic time and tier bandwidth
    M2  + the L2->SM link ceiling (a tier routed through L2 cannot beat it)
    M3  + access-mix bandwidth BW(r): for a demand-filled CACHE, r equals the
          hit rate, because every miss is a fill
    M4  + replacement reality: LRU on a cyclic decode sweep gets zero hits
    M5  + physical feasibility: C1's lower-Si periphery scales with tier area

All model calculation. Only the fixed term and HBM effective bandwidth come from
measurement.
"""
import os, sys, csv, math
sys.path.insert(0, os.path.dirname(__file__))
import sram_capacity_bandwidth_sweep as S
import sram_area_scaling as A

GB = 1e9; MB = 1e6
ROOT = os.path.join(os.path.dirname(__file__), '..')
BW_HBM_PEAK = 8.0
BW_L2_SM = {'cross-partition': 16.8, 'nominal': 19.0, 'local': 21.0}
BW_3D = {'thermal-capped (0.5 pJ/b, 20 W)': 5.0, 'read 80% / fill 20%': 9.4, 'read-only': 15.0}
DEVICE_POINTS = [('C3 1층', 1390, 0.0), ('C2 1층', 2110, 0.0), ('C3 2층', 2780, 0.0),
                 ('C1 1층', 2950, 0.40), ('C2 2층', 4220, 0.0)]
REF = ('llama', 8, 2048)

def eta_mix(r):
    """Access-mix efficiency RELATIVE to read-only, from the device team's BW(r) table.
    Their three points are the delivered bandwidth at read share 1.0 / 0.8 / 0.6, so
    eta(r) = BW(r)/BW(1.0). Applying the ratio rather than the absolute value lets the
    nominal (read-only) bandwidth stay an independent axis and avoids double-counting
    the H100-anchored derate that is already inside their 15 TB/s.
    The table covers r in [0.6, 1.0]. Below 0.6 it has no answer; we clamp to the
    floor 3.8/15, which is optimistic, since linear extrapolation goes negative at r = 0.46."""
    tab = [(1.0, 15.0), (0.8, 9.4), (0.6, 3.8)]
    if r >= 1.0: return 1.0, False
    for (r1, b1), (r0, b0) in zip(tab, tab[1:]):
        if r0 <= r <= r1: return (b0 + (b1-b0)*(r-r0)/(r1-r0))/15.0, False
    return 3.8/15.0, True

def ladder(mk, B, N, C, bw3d_nominal, bw_l2=19.0, sem='pinned', si_frac=0.0):
    """Every rung of the ladder for one design point."""
    c = S.CAL[mk]; obj, ws, T = S.workload(mk, B, N)
    cov = min(1.0, C/ws) if C > 0 else 0.0
    t0, bw_hbm = c['t0_ms'], c['BW_eff_TBs']
    base = t0 + T/GB/bw_hbm
    out = {'coverage': cov, 'WS_GB': ws/GB, 'traffic_GB': T/GB, 'base_ms': base, 't0_ms': t0, 'bw_hbm_eff': bw_hbm}

    # M0: capacity only, pure roofline, no fixed term, tier assumed free
    out['M0'] = 1.0/(1.0-cov) if cov < 1 else float('inf')

    # M1: fixed term + tier bandwidth, tier carries only what it serves (pinned store)
    served = cov*T
    m1 = t0 + (T-served)/GB/bw_hbm + served/GB/bw3d_nominal
    out['M1'] = base/m1

    # M2: + L2->SM ceiling. A tier routed through L2 cannot deliver faster than the L2 link,
    # and the L2 link must carry every byte the SM consumes.
    eff3d = min(bw3d_nominal, bw_l2)
    mem = (T-served)/GB/bw_hbm + served/GB/eff3d
    m2 = t0 + max(mem, T/GB/bw_l2)
    out['M2'] = base/m2; out['bw3d_after_L2_cap'] = eff3d

    # M3: + access-mix bandwidth. Two tier semantics:
    #   pinned store  -> tier carries only the served reads, r ~ 1 (writes are the model's own)
    #   demand cache  -> tier carries ALL traffic (hit reads + miss fills), r = hit rate
    r_pin = sum(o['sr'] for o in obj.values())/max(1e-9, sum(o['sr']+o['sw'] for o in obj.values())) if False else None
    # object-agnostic pinned: served bytes inherit the workload's own read share
    reads = sum(o['read'] for o in obj.values()); writes = sum(o['write'] for o in obj.values())
    r_pinned = reads/(reads+writes)
    eta_p, off_p = eta_mix(r_pinned); bw_pin = min(bw3d_nominal*eta_p, bw_l2)
    m3_pin = t0 + max((T-served)/GB/bw_hbm + served/GB/bw_pin, T/GB/bw_l2)
    out['M3_pinned'] = base/m3_pin; out['r_pinned'] = r_pinned; out['bw_pinned'] = bw_pin

    # demand-filled cache: hit -> read the tier, miss -> fill the tier. Tier carries ALL of T
    # and its read share equals the hit rate.
    h = cov
    eta_c, off_c = eta_mix(h); bw_cache = min(bw3d_nominal*eta_c, bw_l2)
    m3_cache = t0 + max((T-served)/GB/bw_hbm + T/GB/bw_cache, T/GB/bw_l2)
    out['M3_cache'] = base/m3_cache; out['r_cache'] = h; out['bw_cache'] = bw_cache; out['cache_off_table'] = off_c

    # M4: + replacement reality. Decode sweeps the whole working set once per step, so every
    # byte's reuse distance is WS: LRU gets zero hits until C >= WS. A zero-hit demand cache
    # still fills on every access, so the tier carries T bytes of pure write traffic.
    if C >= ws:
        out['M4_LRU'] = out['M3_cache']
    else:
        eta0, _ = eta_mix(0.0); bw0 = min(bw3d_nominal*eta0, bw_l2)
        out['M4_LRU'] = base/(t0 + T/GB/bw_hbm + T/GB/bw0)          # fill on the critical path
        out['M4_LRU_fill_hidden'] = base/(t0 + T/GB/bw_hbm)         # fill fully overlapped: merely useless

    # M5: + physical feasibility (C1 lower-Si periphery removes logic area)
    m5 = t0/max(0.05, 1-si_frac) + max((T-served)/GB/bw_hbm + served/GB/bw_pin, T/GB/bw_l2)
    out['M5_pinned_with_si'] = base/m5
    return out


# ---------------------------------------------------------------------------
# Two timing bounds for the tier term (added 2026-09-20 after the "L2 is a counterexample" critique).
#   serial     step = t0 + (T-S)/BW_HBM + S_tier/BW_3D            (pessimistic: tier time adds)
#   overlapped step = t0 + max((T-S)/BW_HBM, S_tier/BW_3D, T/BW_L2) (optimistic: tier time hides under HBM)
# A well-provisioned cache like B200's L2 lives in the overlapped regime: fills are overlapped with
# delivery and L2 bandwidth exceeds HBM's, so it never becomes the bottleneck. The serial form is
# therefore an upper bound on harm, not a description of any real cache. Under the overlapped bound
# a demand-filled tier is harmful iff its mixed-traffic bandwidth BW(r = hit rate) < BW_HBM_eff.
# ---------------------------------------------------------------------------
def ladder_bounds(mk, B, N, C, bw3d_nominal, bw_l2=19.0, bw_floor_ratio=3.8/15.0):
    c = S.CAL[mk]; obj, ws, T = S.workload(mk, B, N)
    t0, bh = c['t0_ms'], c['BW_eff_TBs']; cov = min(1.0, C/ws) if C > 0 else 0.0
    base = t0 + T/GB/bh
    def both(hbm_bytes, tier_bytes, bw3):
        ser = t0 + hbm_bytes/GB/bh + (tier_bytes/GB/bw3 if tier_bytes else 0.0)
        ovl = t0 + max(hbm_bytes/GB/bh, tier_bytes/GB/bw3 if tier_bytes else 0.0, T/GB/bw_l2)
        return base/ser, base/ovl
    out = {'coverage': cov, 'M0': (1.0/(1.0-cov) if cov < 1 else float('inf'))}
    served = cov*T
    bw_pin = min(bw3d_nominal, bw_l2)
    out['M1'] = both(T-served, served, bw_pin)
    out['M2'] = out['M1']                       # L2 cap is already inside both(); does not bind below 19
    out['M3_pinned'] = out['M1']
    # demand-filled cache: tier carries all T; its read share is the hit rate; BW(h) <= BW(0.6) = table floor
    # for any h < 0.6 by monotonicity. We evaluate at the floor (an UPPER bound on the cache's bandwidth).
    bw_cache = min(bw3d_nominal*bw_floor_ratio, bw_l2)
    out['M3_cache_floor'] = both(T-served, T, bw_cache)
    out['M4_LRU_floor'] = both(T, T, bw_cache)  # zero hits: HBM carries all T and the tier is pure fill
    out['break_even_serial_TBs'] = bh/cov if cov else float('inf')      # B3 > BH/h
    out['break_even_overlap_TBs'] = bh                                    # BW(h) > BH
    return out

if __name__ == '__main__':
    mk, B, N = REF; name = S.MODELS[mk]['name']
    print("=== 0. 링크 정의와 출처 ===")
    print(f"  HBM -> L2      peak {BW_HBM_PEAK} TB/s [NVIDIA B200 사양]")
    print(f"                 eff  {S.CAL[mk]['BW_eff_TBs']:.2f} TB/s [실측 decode 앵커 회귀; memory.html 재생 회귀는 6.51]")
    print(f"                 = peak의 {S.CAL[mk]['BW_eff_TBs']/BW_HBM_PEAK*100:.0f}%")
    print(f"  L2  -> SM      {BW_L2_SM['cross-partition']}~{BW_L2_SM['local']} TB/s [Chips and Cheese B200 마이크로벤치; NVIDIA 공식 수치 없음]")
    print(f"  3D  -> SM      {list(BW_3D.values())} TB/s [소자팀 BW(r), r = 0.6 / 0.8 / 1.0 및 열 상한]")
    print(f"  L2 용량 126 MB [NVIDIA Blackwell 튜닝 가이드]  /  3D 티어 용량 1.39~4.22 GB [소자팀 밀도 × 면적]")

    print(f"\n=== 1. 추상화 사다리: {name} B={B} N={N}, C = 4.22 GB (C2 2층), 3D 15 TB/s, L2->SM 19 ===")
    L = ladder(mk, B, N, 4220*MB, 15.0)
    print(f"  working set {L['WS_GB']:.1f} GB / 스텝 트래픽 {L['traffic_GB']:.1f} GB / 커버리지 {L['coverage']*100:.1f}%")
    print(f"  기준 step {L['base_ms']:.3f} ms = 고정 {L['t0_ms']:.2f} ms + 트래픽/{L['bw_hbm_eff']:.2f} TB/s\n")
    rungs = [('M0 용량만 (순수 roofline)', L['M0'], '트래픽 감소분이 곧 시간 감소라고 가정'),
             ('M1 + 고정항·티어 BW', L['M1'], f"고정 {L['t0_ms']:.2f} ms는 티어가 못 줄인다"),
             ('M2 + L2->SM 상한', L['M2'], f"티어 실효 {L['bw3d_after_L2_cap']:.1f} TB/s (L2 경유 시)"),
             ('M3 고정 배치 (pinned)', L['M3_pinned'], f"r = {L['r_pinned']:.3f} -> {L['bw_pinned']:.1f} TB/s"),
             ('M3 수요 충전 캐시', L['M3_cache'], f"r = 적중률 {L['r_cache']:.3f} -> {L['bw_cache']:.1f} TB/s" + (' (표 밖)' if L['cache_off_table'] else '')),
             ('M4 캐시 + 실제 LRU', L['M4_LRU'], f"적중 0, 충전만 남음 (충전 숨기면 {L.get('M4_LRU_fill_hidden', 1.0):.3f})")]
    for lbl, v, note in rungs:
        print(f"  {lbl:28s} {v:7.3f}x   {note}")
    print(f"\n  사다리는 M3 에서 갈라진다. 고정 배치는 {L['M3_pinned']:.3f}x 로 살아남고,")
    print(f"  수요 충전 캐시는 {L['M3_cache']:.3f}x, 거기에 실제 LRU 를 넣으면 {L['M4_LRU']:.3f}x 다.")
    print(f"  단일 최대 하락은 M0 -> M1 ({L['M0']:.3f} -> {L['M1']:.3f}, {(L['M0']-L['M1'])*100:.0f}%p): 고정항 {L['t0_ms']:.2f} ms 를 티어가 못 줄인다.")
    print(f"  그다음이 M2 -> M3 캐시 분기 ({L['M2']:.3f} -> {L['M3_cache']:.3f}): 충전 트래픽이 티어 대역폭을 무너뜨린다.")

    print("\n=== 2. 왜 수요 충전 캐시가 구조적으로 불가능한가 ===")
    print("  캐시에서는 적중이면 티어를 읽고 미스면 티어를 채운다. 그래서 티어가 나르는 바이트는 트래픽 전체이고,")
    print("  읽기 비중 r 은 정확히 적중률과 같다. 소자팀 BW(r) 표는 r >= 0.6 만 덮는다.")
    print(f"  {'용량':>8s} {'적중률=r':>9s} {'BW(r)':>10s} {'티어가 나르는 양':>14s} {'캐시':>8s} {'고정배치':>9s}")
    for lbl, C, si in DEVICE_POINTS:
        L2_ = ladder(mk, B, N, C*MB, 15.0)
        flag = ' (표밖)' if L2_['cache_off_table'] else ''
        print(f"  {C/1000:7.2f}G {L2_['r_cache']:9.3f} {L2_['bw_cache']:7.1f}{flag:7s} {L2_['traffic_GB']:11.1f} GB {L2_['M3_cache']:8.3f} {L2_['M3_pinned']:9.3f}")
    print("  적중률이 0.75 를 넘어야 티어가 HBM보다 빨라지는데, 그러려면 용량이 working set의 75%,")
    print(f"  즉 {0.75*L['WS_GB']:.1f} GB 가 필요하다. 실현 상한 4.22 GB 의 {0.75*L['WS_GB']/4.22:.1f} 배다.")
    print("  결론: 수요 충전 캐시는 실현 가능한 용량에서 성립하지 않는다. 티어는 미리 채워 붙잡아 두는 저장소여야 한다.")

    print("\n=== 3. L2->SM 상한이 언제 무는가 (고정 배치, C = 4.22 GB) ===")
    print(f"  {'3D 공칭 BW':>11s} " + ' '.join(f"{'L2 '+str(v):>12s}" for v in BW_L2_SM.values()) + f"{'L2 우회':>12s}")
    for b in (9.4, 15, 20, 30, 60):
        cells = [f"{ladder(mk,B,N,4220*MB,b,bw_l2=v)['M3_pinned']:12.3f}" for v in BW_L2_SM.values()]
        byp = ladder(mk,B,N,4220*MB,b,bw_l2=1e6)['M3_pinned']
        print(f"  {b:10.1f}T " + ' '.join(cells) + f"{byp:12.3f}")
    print("  L2 를 경유하면 티어 대역폭이 L2 링크를 넘는 순간부터 소용이 없다.")
    print("  즉 소자팀에 17~21 TB/s 이상을 요구할 이유는, L2 를 우회해 SM 에 직결할 때뿐이다.")

    print("\n=== 4. 실현 가능 설계점 최종표 (고정 배치, L2->SM 19 TB/s) ===")
    print(f"  {'설계점':10s} {'용량':>8s} {'커버':>7s} " + ' '.join(f"{k:>22s}" for k in BW_3D) + f" {'실현':>6s}")
    for lbl, C, si in DEVICE_POINTS:
        cells = []
        for k, b in BW_3D.items():
            v = ladder(mk, B, N, C*MB, b, si_frac=si)
            cells.append(f"{v['M3_pinned']:.3f} / {v['M5_pinned_with_si']:.3f}")
        Lp = ladder(mk, B, N, C*MB, 15.0, si_frac=si)
        feas = '가능' if si == 0 else ('조건부' if si < 0.5 else '불가')
        print(f"  {lbl:10s} {C/1000:7.2f}G {Lp['coverage']*100:6.1f}% " + ' '.join(f"{c:>22s}" for c in cells) + f" {feas:>6s}")
    print("  각 칸은 'Si 손실 무시 / Si 손실 반영'. C3·C2 는 Si 를 쓰지 않아 두 값이 같다.")

    print("\n=== 5. 모델별로 8개 workload (고정 배치, C = 4.22 GB, 3D 15, L2 19) ===")
    print(f"  {'workload':30s} {'WS':>6s} {'커버':>7s} {'M0':>7s} {'M1':>7s} {'M2':>7s} {'M3':>7s} {'M4':>7s}")
    for wk, b, n in A.WORKLOADS:
        v = ladder(wk, b, n, 4220*MB, 15.0)
        print(f"  {S.MODELS[wk]['name']+f' B={b} N={n//1024}k':30s} {v['WS_GB']:5.1f}G {v['coverage']*100:6.1f}% "
              f"{v['M0']:7.3f} {v['M1']:7.3f} {v['M2']:7.3f} {v['M3_pinned']:7.3f} {v['M4_LRU']:7.3f}")

    rows = []
    for wk, b, n in A.WORKLOADS:
        for lbl, C, si in DEVICE_POINTS:
            for k3, b3 in BW_3D.items():
                for k2, b2 in BW_L2_SM.items():
                    v = ladder(wk, b, n, C*MB, b3, bw_l2=b2, si_frac=si)
                    rows.append(dict(model=S.MODELS[wk]['name'], B=b, N=n, design_point=lbl, capacity_MB=C,
                                     bw_3d_label=k3, bw_3d=b3, bw_l2_label=k2, bw_l2=b2, si_frac=si, **v))
    p = os.path.join(ROOT, 'assets/sweep/hierarchy_ladder.csv')
    with open(p, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\nwrote {len(rows)} rows -> assets/sweep/hierarchy_ladder.csv")
