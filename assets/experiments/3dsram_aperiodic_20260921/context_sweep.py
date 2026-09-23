#!/usr/bin/env python3
"""Does the rung-4 admission delta grow with context, and does the dominance condition survive?

Two things move with context and they pull opposite ways (peer session's point [D]):
  + KV share of the stream rises, so more of a first-fill tier is KV that can die -> delta grows
  - the tier stops being small relative to the contested working set -> the lifetime-dominance
    lemma ('a weight byte weakly dominates a KV byte') needs tier capacity < weight WS
Plot both. A crossing is the paper's applicability boundary.
"""
import csv, os, sys
import replay_policies as R
GB = 1e9
HERE = os.path.dirname(os.path.abspath(__file__))
CAP3D = R.cap_bytes('C2', 600); CAP = R.C0 + CAP3D
CTX = [512, 1024, 2048, 4096, 8192]

def one(ctx, mean_len=30, steps=64):
    p = f'{HERE}/inputs/aperiodic-b8-s{steps}-L{mean_len}-N{ctx}.jsonl'
    stl, wr = R.tiles(p); lt = R.lifetimes(p)
    base = R.run(stl, wr, 0, 'LIP'); bh = base['hbm_ss']
    red = lambda r: 100*(1 - r['hbm_ss']/bh)
    byp = R.run(stl, wr, CAP3D, 'LIP-bypass'); man = R.run(stl, wr, CAP3D, 'managed')
    orc = max(red(R.run(stl, wr, CAP3D, 'managed+oracleKV', lifetime=lt, min_life=m)) for m in (0, 8, 32, 128))
    # resident composition of the frozen (bypass) tier
    t = R.Tier(CAP, 'LIP-bypass')
    for _ in range(2):
        for i, st in enumerate(stl):
            t.step = i
            for k, b, obj in st: t.access(k, b, obj)
    w = sum(n for k, n in t.d.items() if k[1] in R.WEIGHT_OBJ)
    kv = sum(n for k, n in t.d.items() if k[1] not in R.WEIGHT_OBJ)
    # stream composition at steady state
    last = stl[-1]
    sw = sum(b for k, b, o in last if o in R.WEIGHT_OBJ); skv = sum(b for k, b, o in last if o not in R.WEIGHT_OBJ)
    return dict(ctx=ctx, base_hbm_GB=bh/GB, D_GB=(sw+skv+wr[-1])/GB,
                stream_kv_frac=skv/(sw+skv), resident_kv_frac=kv/(w+kv),
                bypass_pct=red(byp), managed_pct=red(man), oracle_best_pct=orc,
                delta_pp=red(man)-red(byp), oracle_minus_managed_pp=orc-red(man),
                weight_WS_GB=sw/GB, tier_over_weightWS=CAP3D/sw)

if __name__ == '__main__':
    rows = [one(c) for c in CTX]
    with open(f'{HERE}/outputs/context_sweep.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"티어 3D {CAP3D/GB:.3f} GB, 기존 L2 포함 {CAP/GB:.3f} GB. 회전 mean_len 30, 64스텝, 배치 8.\n")
    print(f"{'문맥':>6s} {'스트림 KV':>9s} {'상주 KV':>8s} {'bypass':>8s} {'managed':>8s} {'델타':>8s} {'오라클-man':>10s} {'weight WS':>10s} {'티어/WS':>8s}")
    for r in rows:
        print(f"{r['ctx']:6d} {100*r['stream_kv_frac']:8.2f}% {100*r['resident_kv_frac']:7.2f}% "
              f"{r['bypass_pct']:7.3f}% {r['managed_pct']:7.3f}% {r['delta_pp']:+7.3f}p "
              f"{r['oracle_minus_managed_pp']:+9.3f}p {r['weight_WS_GB']:9.3f}G {r['tier_over_weightWS']:7.3f}")
    print("\n  '오라클-managed' 가 0 이면 수명 지배가 성립(= KV 를 넣지 않는 것이 최적).")
    print("  '티어/WS' 가 1 을 넘으면 티어가 weight 를 다 담고 남아 지배 조건이 깨진다.")
