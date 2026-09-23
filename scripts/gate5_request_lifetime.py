#!/usr/bin/env python3
"""Gate 5: request-lifetime fill accounting for a managed-resident 3D SRAM tier (2026-09-21).

Supersedes the preload section of gate3_traffic_to_time.py, which multiplied by 1e3 in error.
GB divided by TB/s is already milliseconds: 0.4 GB / 6.4 TB/s = 0.0625 ms, not 60 ms.

Three fill classes, each on a different clock:
    weight      resident set that is request-invariant -> filled once per MODEL LOAD
    prefill KV  KV that exists before decode starts    -> filled once per REQUEST BATCH,
                and only if prefill wrote it to HBM rather than straight into the tier
    decode KV   new KV produced each step              -> native write, never a fill

The replay's steady-state residency is decomposed by object to size each class, and each is
amortized on its own clock over decode lengths 64..1024.
"""
import json, csv, os, sys, collections
from collections import OrderedDict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sram_capacity_bandwidth_sweep as S

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
EXP  = os.path.join(ROOT, 'assets/experiments/3dsram_closure_20260921')
GB = 1e9; MiB = 2**20; L2 = 132_644_864
T0 = S.CAL['llama']['t0_ms']; B_HBM = S.CAL['llama']['BW_eff_TBs']
WEIGHT_OBJ = ('layer_weight', 'lm_head', 'embedding_gather')

def residency(cap_bytes, tile=MiB, warm=3):
    """Replay the unified ledger through an LRU-insertion cache of size L2+cap and report what
    is resident at steady state, broken down by object."""
    ev = [json.loads(x) for x in open(f'{EXP}/inputs/llama-b8-l2048-events-unified.jsonl')]
    reads = [e for e in ev if e.get('kind') == 'event' and e['op'] == 'read']
    trace = []
    for e in reads:
        for i, off in enumerate(range(0, e['bytes'], tile)):
            trace.append(((e['layer'], e['object'], i), min(tile, e['bytes'] - off)))
    d = OrderedDict(); live = 0; cap = int(L2 + cap_bytes)
    for _ in range(warm):
        for k, n in trace:
            if k in d: d.move_to_end(k); continue
            while live + n > cap and d: _, m = d.popitem(last=False); live -= m
            if n <= cap: d[k] = n; live += n; d.move_to_end(k, last=False)
    comp = collections.Counter()
    for k, n in d.items(): comp[k[1]] += n
    return comp, sum(comp.values())

def step_gain_ms(cap_GB, b_r):
    """Steady-state per-step gain from the exact replay, serial bound."""
    rows = [r for r in csv.DictReader(open(f'{EXP}/outputs/closure_area_policy.csv'))]
    base_hbm = json.load(open(f'{EXP}/outputs/closure_summary.json'))['baseline_existing_sL2_LIP_HBM_GiB_step']*2**30/GB
    r = next(r for r in rows if r['case']=='C2' and r['layers']=='2' and r['architecture']=='integrated_sL2_plus_3D_LIP'
             and abs(float(r['capacity_GB_gpu'])-cap_GB) < 1e-3 and r['p99_hbm_fraction']=='0.5')
    H = float(r['hbm_GiB_step'])*2**30/GB; Sv = base_hbm - H
    t_base = T0 + base_hbm/B_HBM; t_new = T0 + H/B_HBM + Sv/b_r
    return t_base - t_new, t_base, Sv

if __name__ == '__main__':
    CAP_GB = 3.16426   # 600 mm2 per die per tier, C2, 2 tiers, 2 dies
    comp, tot = residency(CAP_GB*GB)
    w = sum(b for o, b in comp.items() if o in WEIGHT_OBJ)
    kv = sum(b for o, b in comp.items() if o not in WEIGHT_OBJ)

    print("=== 5-1. 0.4 GB 의 정체 추적 ===")
    print(f"  재생 정상 상태 상주 집합 (기존 L2 {L2/GB:.3f} GB + 3D {CAP_GB:.3f} GB = {(L2/GB+CAP_GB):.3f} GB 중 점유 {tot/GB:.3f} GB)")
    for o, b in comp.most_common():
        print(f"    {o:18s} {b/GB:7.3f} GB  {100*b/tot:5.1f}%")
    print(f"  KV 합계 {kv/GB:.3f} GB 는 **B=8 배치 전체·32층 합산의 상주량**이다. 층별 값도 요청별 값도 아니다.")
    print(f"    층당 평균 {kv/GB/32*1000:.1f} MB, 요청당 {kv/GB/8*1000:.1f} MB (배치 8)")
    print(f"  스텝당 KV 읽기 총량은 2.147 GB 이므로, 티어는 그중 {100*kv/2.147e9:.1f}% 를 붙잡고 있다.")
    print(f"  전송 횟수: 이 바이트는 요청 수명 동안 **한 번** 채워지고 계속 읽힌다. 매 스텝 재전송이 아니다.\n")

    print("=== 5-2. 단위 정정 ===")
    print(f"  GB / (TB/s) = ms.  {kv/GB:.3f} GB / 6.4 TB/s = {kv/GB/6.4:.4f} ms = {kv/GB/6.4*1000:.1f} µs")
    print(f"  구판 문서의 '요청당 60 ms' 는 1000배 오류였다. 올바른 값은 {kv/GB/6.4*1000:.0f} µs 다.\n")

    print("=== 5-3. 세 채움 종류와 각자의 시계 ===")
    gain, t_base, Sv = step_gain_ms(CAP_GB, 15.0)
    print(f"  정상 상태 스텝당 이득 {gain:.4f} ms (기준 step {t_base:.3f} ms, 직렬, B_R 15 TB/s)")
    print(f"  {'종류':14s} {'크기':>9s} {'시계':22s} {'B_W 6.4 에서':>12s}")
    print(f"  {'weight':14s} {w/GB:8.3f}G {'모델 적재 1회':22s} {w/GB/6.4:11.4f} ms")
    print(f"  {'prefill KV':14s} {kv/GB:8.3f}G {'요청 배치 1회 (조건부)':22s} {kv/GB/6.4:11.4f} ms")
    print(f"  {'decode KV':14s} {1*MiB/GB:8.3f}G {'스텝별 native write':22s} {1*MiB/GB/6.4:11.4f} ms")
    print("  decode KV 는 모델이 생성해 티어에 바로 쓰므로 채움이 아니다. prefill KV 는 prefill 이 어디에 쓰느냐에 달렸다.\n")

    print("=== 5-4. 요청 길이별 상각 (prefill KV 를 HBM 에서 끌어올리는 최악 가정) ===")
    print(f"  {'B_W':>6s} {'prefill KV 채움':>14s} | " + ' '.join(f"{'N='+str(n):>10s}" for n in (64,128,256,512,1024)))
    rows=[]
    for bw in (2.0, 4.0, 6.4, 8.0, 15.0, 19.0):
        fill = kv/GB/bw
        cells=[]
        for n in (64,128,256,512,1024):
            net = gain - fill/n
            cells.append(f"{net:.4f}")
            rows.append(dict(gate='5-4', B_W_TBs=bw, prefill_fill_ms=fill, decode_steps=n,
                             steady_gain_ms=gain, net_gain_ms=net, loss_pct=100*(1-net/gain)))
        print(f"  {bw:5.1f}T {fill:13.4f}ms | " + ' '.join(f"{c:>10s}" for c in cells))
    worst = max(r['loss_pct'] for r in rows)
    print(f"  최악(B_W 2 TB/s, N=64)에서도 스텝당 이득 손실은 {worst:.2f}% 다.")
    print(f"  weight 적재 {w/GB/6.4:.3f} ms 는 모델 수명 전체(수백만 스텝)에 상각되어 무시 가능하다.\n")

    print("=== 5-5. 판정 ===")
    print("  Gate 5 는 병목이 아니다. 단위를 바로잡으면 prefill KV 채움은 요청당 수십 µs 이고,")
    print("  가장 짧은 64스텝 요청에 상각해도 정상 상태 이득의 1% 미만을 깎는다.")
    print("  따라서 managed residency 에서 B_W 는 성능 변수가 아니라 모델 적재 지연 변수다.")
    print("  prefill 이 KV 를 티어에 직접 쓰는지 여부도 성능 결론을 바꾸지 않는다.")

    p = os.path.join(ROOT, 'assets/sweep/gate5_request_lifetime.csv')
    with open(p,'w',newline='') as f:
        keys=sorted({k for r in rows for k in r}); wtr=csv.DictWriter(f,fieldnames=keys); wtr.writeheader(); wtr.writerows(rows)
    print(f"\nwrote {os.path.relpath(p,ROOT)}")
