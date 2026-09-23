#!/usr/bin/env python3
"""GB-scale re-run: capacity built from DIE AREA, not a fixed 320 mm² (2026-09-20).

The earlier sweep froze the tier at 320 mm²/die, which is the deck's 40% coverage
of an 800 mm² die. Area is an axis, not a constant. Capacity is rebuilt as

    C = density[case] x A_die x coverage x layers x dies

with usable densities from the device team's 2026-09-20 answer (MB per mm² of
tier footprint, ECC/tag 12% and redundancy/BIST 5% already removed):
    C3 (BEOL peri, 2.5x compensated) 278/320 = 0.869
    C2 (BEOL peri, no compensation)  422/320 = 1.319
    C1 (peri on lower Si)            590/320 = 1.844   + 128 mm² of logic Si per 320 mm²

Three tier semantics, because at GB scale the difference stops being cosmetic:
    G1  ideal-capacity, object-agnostic: fraction min(1, C/WS) of every byte is
        served. Upper bound for ANY replacement policy.
    G2  real LRU on the decode access pattern. Decode sweeps the whole working
        set once per step, so every byte's reuse distance is WS. Under LRU that
        means zero hits until C >= WS. This is the honest "generic cache".
    G3  object-aware ledger + admission (rank by traffic/resident byte, pin).
        Reaches G1 when it can pin; this is what policy buys.

Timing: per-model calibrated step = t0 + (T - served)/BW_eff + served/BW_tier,
fit on measured B200 decode medians. Model calculation, not a measurement.
"""
import csv, os, sys, math
sys.path.insert(0, os.path.dirname(__file__))
import sram_capacity_bandwidth_sweep as S

GB = 1e9; MB = 1e6
ROOT = os.path.join(os.path.dirname(__file__), '..')
DENSITY = {'C3': 278/320, 'C2': 422/320, 'C1': 590/320}     # MB per mm² of tier footprint
SI_COST = {'C3': 0.0, 'C2': 0.0, 'C1': 128/320}             # mm² of lower-Si logic per mm² of tier
A_DIE = [320, 400, 600, 800]
COVERAGE = [0.4, 0.6, 0.8, 1.0]
LAYERS = [1, 2]
DIES = 2                                                     # B200-class two-die package
BW = [5, 8, 10, 15, 20, 30, 60]
WORKLOADS = [('llama', 8, 2048), ('llama', 32, 8192), ('llama2', 8, 2048),
             ('granite', 32, 8192), ('granite', 8, 8192), ('qwen', 8, 2048), ('mistral', 8, 2048)]

def capacity_MB(case, a_die, coverage, layers, dies=DIES):
    return DENSITY[case] * a_die * coverage * layers * dies

def si_mm2(case, a_die, coverage, layers, dies=DIES):
    return SI_COST[case] * a_die * coverage * layers * dies

def served_bytes(mk, B, N, C, sem):
    obj, ws, T = S.workload(mk, B, N)
    if sem == 'G1':
        return (min(1.0, C/ws) if C > 0 else 0.0) * T, ws, T
    if sem == 'G2':
        return (T if (C > 0 and C >= ws) else 0.0), ws, T
    if C <= 0: return 0.0, ws, T
    S.d.place(obj, C)
    return sum(o['sr']+o['sw'] for o in obj.values()), ws, T

def step(mk, B, N, C, bw, sem, si_frac=0.0):
    """si_frac = fraction of the LOGIC die consumed by lower-Si periphery (C1 only).
    That silicon no longer computes, so the fixed term t0 is scaled by 1/(1-si_frac).
    Assumption: the fixed term is compute-proportional. Flagged, not measured."""
    c = S.CAL[mk]; served, ws, T = served_bytes(mk, B, N, C, sem)
    t0 = c['t0_ms'] / max(0.05, 1.0 - si_frac)
    base = c['t0_ms'] + T/GB/c['BW_eff_TBs']            # baseline GPU keeps all its logic
    st = t0 + (T-served)/GB/c['BW_eff_TBs'] + (served/GB/bw if served else 0.0)
    tier_ms = served/GB/bw if served else 0.0
    return dict(speedup=base/st, served_frac=served/T, ws_GB=ws/GB, traffic_GB=T/GB, base_ms=base, step_ms=st,
                hbm_bytes_GB=(T-served)/GB, hbm_cut_pct=served/T*100, tier_ms=tier_ms,
                duty=tier_ms/st if st else 0.0, t0_eff_ms=t0)

def power_W(mk, B, N, C, bw, e_bit_pJ, sem='G1'):
    """Returns (average power over the step, instantaneous power while the tier streams, duty cycle).
    Thermal limits average power; Minho's BW <= P/E is an instantaneous relation."""
    served, ws, T = served_bytes(mk, B, N, C, sem); r = step(mk, B, N, C, bw, sem)
    inst = bw*1e12*8*e_bit_pJ*1e-12
    avg = served*8*e_bit_pJ*1e-12 / (r['step_ms']*1e-3)
    return avg, inst, r['duty']

if __name__ == '__main__':
    print("=== 1. 면적에서 만든 용량 사다리 (2다이 패키지) + C1의 하부 Si 청구 ===")
    print(f"{'구성':30s} {'용량':>9s} {'하부 Si 총':>11s} {'로직 다이 중':>12s} {'실현':>5s}")
    for case in ('C3','C2','C1'):
        for a, cov in ((320, 0.4), (800, 1.0)):
            for L in LAYERS:
                C = capacity_MB(case, a, cov, L); si = si_mm2(case, a, cov, L); sf = (si/DIES)/a
                tag = f"{case} A={a} cov={cov:.1f} {L}층"
                print(f"{tag:30s} {C/1000:8.2f} GB {si:10.0f} mm² {sf*100:11.0f}% {'가능' if sf<0.5 else '불가':>5s}")
    print("\n  C3·C2는 하부 Si를 쓰지 않는다. C1은 티어 면적에 비례해 Si를 먹으므로,")
    print("  티어를 다이 전체로 키우면 로직 다이의 40%(1층)를 페리가 가져가고 2층은 80%라 성립하지 않는다.")

    caps = [556, 1112, 1390, 2110, 2224, 2780, 2950, 4220, 5900]
    print("\n=== 2. G1 이상 캐시: 용량별 speedup (BW 15 TB/s, Si 손실 미반영) ===")
    print(f"{'workload':30s} {'WS':>6s} " + ' '.join(f"{c/1000:>6.2f}G" for c in caps))
    for mk,B,N in WORKLOADS:
        r0 = step(mk,B,N,0,15,'G1')
        cells = [f"{step(mk,B,N,c*MB,15,'G1')['speedup']:6.3f}" for c in caps]
        print(f"{S.MODELS[mk]['name']+f' B={B} N={N//1024}k':30s} {r0['ws_GB']:5.1f}G " + ' '.join(f"{c:>7s}" for c in cells))

    print("\n=== 3. G1(이상) vs G2(실제 LRU) vs G3(ledger) — Llama-3.1-8B B=8 N=2048, BW 15 ===")
    print(f"{'용량':>9s} {'G1 이상':>9s} {'G2 LRU':>9s} {'G3 ledger':>10s} {'G1 커버':>8s}")
    for c in caps:
        g1 = step('llama',8,2048,c*MB,15,'G1'); g2 = step('llama',8,2048,c*MB,15,'G2'); g3 = step('llama',8,2048,c*MB,15,'G3')
        print(f"{c/1000:8.2f}G {g1['speedup']:9.3f} {g2['speedup']:9.3f} {g3['speedup']:10.3f} {g1['served_frac']*100:7.1f}%")
    print("  G2가 전부 1.000인 이유: decode는 스텝마다 working set 전체를 한 번씩 훑는다.")
    print("  모든 바이트의 재사용 거리가 WS이므로 LRU는 C >= WS 전까지 적중이 0이다.")

    print("\n=== 4. C1의 Si 손실을 반영하면 (t0가 1/(1-si_frac) 배라는 가정) ===")
    print(f"{'구성':30s} {'용량':>8s} {'Si 손실':>8s} {'Si 무시':>8s} {'Si 반영':>8s}")
    for case in ('C3','C2','C1'):
        for a, cov, L in ((320,0.4,1),(800,1.0,1),(800,1.0,2)):
            C = capacity_MB(case,a,cov,L); si = si_mm2(case,a,cov,L); sf = (si/DIES)/a
            if sf >= 0.5: continue
            naive = step('llama',8,2048,C*MB,15,'G1')['speedup']
            real  = step('llama',8,2048,C*MB,15,'G1',si_frac=sf)['speedup']
            print(f"{case+f' A={a} cov={cov:.1f} {L}층':30s} {C/1000:7.2f}G {sf*100:7.0f}% {naive:8.3f} {real:8.3f}")

    print("\n=== 5. GB급에서 대역폭이 다시 중요해지는가 (G1, Llama-3.1-8B B=8 N=2048) ===")
    print(f"{'용량':>9s} " + ' '.join(f"{b:>6d}" for b in BW) + "   8->60 폭")
    for c in (556, 1390, 2950, 5900):
        vals = [step('llama',8,2048,c*MB,b,'G1')['speedup'] for b in BW]
        spread = vals[BW.index(60)] - vals[BW.index(8)]
        print(f"{c/1000:8.2f}G " + ' '.join(f"{v:6.3f}" for v in vals) + f"   {spread*100:+5.1f}%p")

    print("\n=== 6. 전력: 평균 대 순간, duty cycle (G1, Llama-3.1-8B B=8 N=2048) ===")
    print(f"{'용량':>9s} {'BW':>5s} {'duty':>6s} " + ' '.join(f"{'E='+str(e)+'pJ 평균/순간':>20s}" for e in (0.1,0.5)))
    for c in (1390, 2950, 5900):
        for b in (15, 30):
            cells = []
            for e in (0.1, 0.5):
                avg, inst, duty = power_W('llama',8,2048,c*MB,b,e); cells.append(f"{avg:5.1f}W / {inst:5.0f}W")
            _,_,duty = power_W('llama',8,2048,c*MB,b,0.1)
            print(f"{c/1000:8.2f}G {b:4d}T {duty*100:5.1f}% " + ' '.join(f"{x:>20s}" for x in cells))
    print("  열은 평균 전력이 정한다. duty cycle이 낮아 평균은 한 자리 W다.")
    print("  민호 님의 BW <= P/E 는 순간 관계이므로, 예산 P가 지속 전력인지 순간 전력인지 확인이 필요하다.")

    rows = []
    for case in ('C3','C2','C1'):
        for a in A_DIE:
            for cov in COVERAGE:
                for L in LAYERS:
                    C = capacity_MB(case, a, cov, L)*MB
                    si_tot = si_mm2(case, a, cov, L); sf = (si_tot/DIES)/a
                    for mk,B,N in WORKLOADS:
                        for b in BW:
                            for sem in ('G1','G2','G3'):
                                r = step(mk,B,N,C,b,sem,si_frac=min(0.95,sf))
                                rows.append(dict(case=case, A_die_mm2=a, tier_coverage=cov, layers=L, dies=DIES,
                                                 capacity_MB=C/MB, lower_si_mm2=si_tot, si_frac_of_logic_die=sf,
                                                 feasible=(sf < 0.5), model=S.MODELS[mk]['name'], B=B, N=N,
                                                 semantics=sem, BW_TBs=b, **r))
    p = os.path.join(ROOT, 'assets/sweep/sram_area_scaling.csv')
    with open(p,'w',newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\nwrote {len(rows)} rows -> assets/sweep/sram_area_scaling.csv")
