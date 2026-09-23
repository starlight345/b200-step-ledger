#!/usr/bin/env python3
"""Two questions, answered without extrapolating the device team's BW(r) table (2026-09-20).

Q1  Does the "a demand-filled cache cannot work" conclusion survive if we refuse to
    guess BW(r) below r = 0.6, where the device team's table ends?
    Method: instead of plugging in an extrapolated bandwidth, solve for the bandwidth
    the cache WOULD need to break even, and compare it with the highest value the tier
    could conceivably deliver. Adding fills can only lower delivered bandwidth (that is
    the monotone content of the device team's three points), so BW(r=1.0) = 15 TB/s is a
    hard upper bound for any r, and the L2 link caps it again at 16.8-21 TB/s.

Q2  For a pinned store, can we know in advance what to pin?
    Method: decompose each step's traffic into what is statically known, what the serving
    engine already tracks exactly, and what depends on data-dependent routing.

PROVENANCE. Device team supplied: BW(r) at r = 1.0 / 0.8 / 0.6 -> 15 / 9.4 / 3.8 TB/s.
Everything below r = 0.6 is NOT theirs. The identity r = hit rate for a demand-filled
cache is our modeling choice, stated in Q1 and flagged wherever it is used.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import sram_capacity_bandwidth_sweep as S
import sram_area_scaling as A

GB = 1e9; MB = 1e6
BW_READ_ONLY = 15.0          # device team, r = 1.0
BW_L2_SM = 19.0              # Chips and Cheese B200 microbenchmark, nominal
POINTS = [('C3 1층', 1390), ('C2 1층', 2110), ('C3 2층', 2780), ('C1 1층', 2950), ('C2 2층', 4220)]

def breakeven_cache_bw(mk, B, N, C):
    """A demand-filled cache moves T bytes through the tier (h*T reads + (1-h)*T fills)
    while removing only h*T bytes from HBM. It breaks even when
        T / BW_cache  ==  h*T / BW_hbm      ->      BW_cache = BW_hbm / h
    independent of t0 and of the shape of BW(r)."""
    c = S.CAL[mk]; obj, ws, T = S.workload(mk, B, N)
    h = min(1.0, C/ws) if C > 0 else 0.0
    return (c['BW_eff_TBs']/h if h > 0 else float('inf')), h, ws, T, c['BW_eff_TBs']

def coverage_needed(mk, B, N, bw_cache):
    """Inverse: what hit rate would a cache need to break even at a given delivered bandwidth."""
    c = S.CAL[mk]; obj, ws, T = S.workload(mk, B, N)
    h = c['BW_eff_TBs']/bw_cache
    return h, h*ws/GB

def union_experts(m, B):
    base, E, k, per, layers = m['moe']
    return E*(1-(1-k/E)**B)

def decompose(mk, B, N):
    """Split step traffic by how knowable it is before the step runs."""
    m = S.MODELS[mk]; obj, ws, T_all = S.workload(mk, B, N)
    kv = obj['kv']['read'] + obj['kv']['write']; st = obj['state']['read'] + obj['state']['write']
    if m.get('wstep'):
        static, routed, uf = m['wstep'], 0.0, None
    else:
        base, E, k, per, layers = m['moe']
        u = union_experts(m, B)
        static, routed, uf = base*GB, per*layers*u*GB, u/E
    T = static + routed + kv + st
    return dict(static=static, routed=routed, kv=kv, state=st, T=T, union_frac=uf)

if __name__ == '__main__':
    mk, B, N = 'llama', 8, 2048
    print("=== Q1. 외삽 없이 판정: 캐시가 본전이 되려면 대역폭이 얼마여야 하는가 ===")
    print("    BW_필요 = HBM유효 / 적중률.  캐시는 적중률 h 만큼만 HBM을 덜어내면서 티어로는 트래픽 전체를 나른다.")
    print(f"    이 식에는 t0 도 BW(r) 의 모양도 들어가지 않는다. 비교 대상은 상한 두 개뿐이다:")
    print(f"      상한 1  BW(r=1.0) = {BW_READ_ONLY} TB/s  — 충전을 섞으면 이보다 낮아질 수만 있다 [소자팀 제공]")
    print(f"      상한 2  L2->SM    = {BW_L2_SM} TB/s     — L2 경유 시 [마이크로벤치]\n")
    print(f"    {'설계점':10s} {'용량':>8s} {'적중률 h':>9s} {'필요 BW':>10s} {'상한 15 대비':>12s} {'판정':>8s}")
    for lbl, C in POINTS:
        need, h, ws, T, bwh = breakeven_cache_bw(mk, B, N, C*MB)
        ratio = need/BW_READ_ONLY
        verdict = '불가' if need > BW_READ_ONLY else ('경계' if need > BW_READ_ONLY*0.8 else '가능')
        print(f"    {lbl:10s} {C/1000:7.2f}G {h*100:8.1f}% {need:9.1f}T {ratio:11.1f}배 {verdict:>8s}")
    print(f"\n    가장 큰 설계점에서도 필요 {breakeven_cache_bw(mk,B,N,4220*MB)[0]:.1f} TB/s 는")
    print(f"    소자팀이 준 최고값 {BW_READ_ONLY} TB/s 의 {breakeven_cache_bw(mk,B,N,4220*MB)[0]/BW_READ_ONLY:.1f} 배, L2 상한 {BW_L2_SM} 의 {breakeven_cache_bw(mk,B,N,4220*MB)[0]/BW_L2_SM:.1f} 배다.")
    print("    따라서 r < 0.6 구간을 몰라도 결론은 바뀌지 않는다. 외삽은 결론에 필요 없었다.\n")

    print("    역으로: 주어진 대역폭에서 캐시가 본전이 되려면 적중률과 용량이 얼마여야 하나")
    print(f"    {'가정 BW':>9s} {'필요 적중률':>11s} {'필요 용량':>11s} {'실현 4.22 GB 대비':>16s}")
    for bw in (9.4, 15.0, 19.0, 27.7, 40.0):
        h, cap = coverage_needed(mk, B, N, bw)
        print(f"    {bw:8.1f}T {h*100:10.1f}% {cap:10.1f} GB {cap/4.22:15.1f}배")
    print("    소자팀 최고값 15 TB/s 를 그대로 줘도 7.8 GB 가 필요하다. 실현 상한의 1.8 배다.\n")

    print("    민감도: BW(r=0.23) 이 실제로 얼마든 상관없는가")
    print(f"    {'가정 BW(0.23)':>13s} {'캐시 speedup':>13s}")
    c = S.CAL[mk]; obj, ws, T = S.workload(mk, B, N); h = min(1.0, 4220*MB/ws); served = h*T
    base = c['t0_ms'] + T/GB/c['BW_eff_TBs']
    for bw in (1.0, 3.8, 6.4, 9.4, 15.0, 19.0, 27.7):
        st = c['t0_ms'] + (T-served)/GB/c['BW_eff_TBs'] + T/GB/bw
        print(f"    {bw:12.1f}T {base/st:13.3f}")
    print("    소자팀이 준 값의 전 범위에서 캐시는 1 미만이다. 본전은 27.7 에서야 온다.\n")

    print("=== Q2. 고정 배치: 미리 무엇을 채울지 알 수 있는가 ===")
    print("    스텝 트래픽을 '스텝이 돌기 전에 얼마나 아는가'로 나눈다.")
    print("      정적    모델 적재 시점에 확정. 매 스텝 같은 바이트를 같은 순서로 읽는다. 예측 불필요")
    print("      엔진추적 서빙 엔진의 블록 테이블에 정확히 있다. 다음 스텝에 무엇을 읽을지 확정. 예측 불필요")
    print("      라우팅   현재 토큰의 데이터 의존 라우팅이 정한다. 예측 필요\n")
    print(f"    {'model':26s} {'B':>3s} {'정적':>9s} {'엔진추적':>10s} {'라우팅':>9s} {'예측 필요 비중':>13s}")
    for wk, b, n in A.WORKLOADS:
        d = decompose(wk, b, n)
        print(f"    {S.MODELS[wk]['name']:26s} {b:3d} {d['static']/GB:8.2f}G {(d['kv']+d['state'])/GB:9.2f}G {d['routed']/GB:8.2f}G {d['routed']/d['T']*100:12.1f}%")
    for wk in ('gptoss','deepseek'):
        for b, n in ((8,8192),(32,8192)):
            d = decompose(wk, b, n)
            print(f"    {S.MODELS[wk]['name']:26s} {b:3d} {d['static']/GB:8.2f}G {(d['kv']+d['state'])/GB:9.2f}G {d['routed']/GB:8.2f}G {d['routed']/d['T']*100:12.1f}%")
    print("\n    dense 와 하이브리드는 예측 필요 비중이 0 이다. 무엇을 고정할지는 계산이 아니라 장부 조회다.")
    print("    MoE 만 라우팅 의존이고, 그마저 배치가 커지면 활성 expert 합집합이 전체에 가까워져 예측 문제가 사라진다:\n")
    print(f"    {'MoE model':26s} " + ' '.join(f"{'B='+str(b):>8s}" for b in (1,2,4,8,16,32,64)))
    for wk in ('granite','gptoss','deepseek'):
        m = S.MODELS[wk]; E = m['moe'][1]
        cells = [f"{union_experts(m,b)/E*100:7.1f}%" for b in (1,2,4,8,16,32,64)]
        print(f"    {m['name']:26s} " + ' '.join(f"{c:>8s}" for c in cells))
    print("    (활성 expert 합집합 / 전체 expert. 균등 라우팅 가정이며 실제 라우팅 편향은 미반영.)")
