#!/usr/bin/env python3
"""정책 축 × 소자 축 스윕 — "어떤 정책이 좋은가"의 답이 소자의 함수로 나온다.

지금까지는 정책 네 개를 점으로 비교했다. 그 넷을 두 축으로 파라미터화하면 앵커가
평면 위의 좌표가 되고, 최적점이 소자 파라미터의 함수로 떨어진다. 그 역함수가 소자 스펙이다.

  p  admission 확률   미스 시 티어에 할당할 확률. BEAR 의 Probabilistic Bypass 와 같은 축
  q  protected 비율   용량 중 고정해 절대 축출하지 않는 몫
  삽입 위치          LIP(LRU 끝) / LRU(MRU 끝) — retention 의 두 번째 노브
  β = B_W / B_R      소자 축. 재생과 무관하므로 사후에 적용한다

앵커: LRU(p=1,q=0,MRU) · LIP(p=1,q=0,LIP) · bypass(p=0,q=1) · managed(p=0,q=1, 의미론 고정)
주기 장부에서 prefix 고정 == weight 고정이므로 q=1 이 bypass 와 managed 를 겸한다.

재현: python3 scripts/policy_device_sweep.py
출력: assets/sweep/policy_device_sweep.csv
"""
import json, math, random, csv, time
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT/'assets/experiments/3dsram_closure_20260921'
MiB = 2**20; TILE = MiB; C0 = 132_644_864; STEPS = 32
USABLE = (1-.12)*(1-.05); BPM = 1_000_000/8*USABLE
MACRO_C2 = 0.079254
T0_MS, B_HBM = 1.85, 6.40                      # canon: t0_ms_llama, hbm_effective_TBs_llama

ev = [json.loads(x) for x in (EXP/'inputs/llama-b8-l2048-events-unified.jsonl').read_text().splitlines()]
ev = [e for e in ev if e.get('kind') == 'event' and e.get('model_tag') == 'llama'
      and e.get('batch') == 8 and e.get('context') == 2048]
W_NATIVE = sum(e['bytes'] for e in ev if e['op'] == 'write')
TRACE = []
for e in (x for x in ev if x['op'] == 'read'):
    for i, off in enumerate(range(0, e['bytes'], TILE)):
        TRACE.append(((e['layer'], e['object'], i), min(TILE, e['bytes']-off)))
F = sum(n for _, n in TRACE)
WEIGHT_OBJ = ('layer_weight', 'lm_head', 'embedding_gather')

def capacity(area_mm2, layers=2, dies=2):
    return math.floor(area_mm2/MACRO_C2)*BPM*layers*dies + C0

def replay(cap, p, q, insert='LIP', semantic=False, seed=7):
    """정상 상태(마지막 스텝)의 경계별 바이트를 돌려준다."""
    rng = random.Random(seed)
    pinned, live = set(), 0
    if q > 0:
        budget = cap*q
        for k, n in TRACE:
            if semantic and k[1] not in WEIGHT_OBJ: continue
            if live + n > budget: break
            pinned.add(k); live += n
    dyn_cap = cap - live
    d = OrderedDict(); dyn = 0
    for s in range(STEPS):
        hbm = fill = hit = 0
        for k, n in TRACE:
            if k in pinned: hit += n; continue
            if k in d:
                hit += n
                if insert == 'LRU': d.move_to_end(k)
                continue
            hbm += n
            if p <= 0 or n > dyn_cap or rng.random() >= p: continue
            while dyn + n > dyn_cap:
                if not d: break
                _, x = d.popitem(last=False); dyn -= x
            d[k] = n; dyn += n; fill += n
            if insert == 'LIP': d.move_to_end(k, last=False)
    return dict(hbm=hbm + W_NATIVE, tier_read=hit, tier_fill=fill, pinned_GB=live/1e9)

def base_hbm(cap_unused):
    """기준선: 기존 L2 만, LIP. closure 재생과 같은 규약."""
    return replay(C0, 1.0, 0.0, 'LIP')['hbm']

def step_ms(r, B_R, B_W, mode):
    th = r['hbm']/1e9/B_HBM
    tt = r['tier_read']/1e9/B_R + (r['tier_fill']/1e9/B_W if r['tier_fill'] else 0.0)
    return T0_MS + (th + tt if mode == 'serial' else max(th, tt))

if __name__ == '__main__':
    P  = [0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 1.0]
    Q  = [0.0, 0.25, 0.50, 0.75, 1.0]
    SEEDS = (7, 20260923, 31337)
    INS = ('LIP', 'LRU')
    AREAS = (600, 800)
    BETAS = (0.05, 0.10, 0.20, 0.28, 0.50, 0.75, 1.00)
    B_R_LIST = (15.0, 17.7, 19.0)

    BASE = base_hbm(None)
    BASE_T = T0_MS + BASE/1e9/B_HBM
    print(f'기준 HBM {BASE/1e9:.4f} GB/step, 기준 step {BASE_T:.4f} ms')
    print(f'재생 {len(P)*len(Q)*len(SEEDS)*len(INS)*len(AREAS)} 회 × {STEPS} 스텝\n')

    rows = []; t_start = time.time(); done = 0
    for area in AREAS:
        cap = capacity(area)
        for ins in INS:
            for q in Q:
                for p in P:
                    accum = []
                    for sd in SEEDS:
                        accum.append(replay(cap, p, q, ins, seed=sd))
                        done += 1
                    r = {k: sum(a[k] for a in accum)/len(accum) for k in accum[0]}
                    red = 100*(1 - r['hbm']/BASE)
                    base_row = dict(area_mm2=area, cap_GB=cap/1e9, insert=ins, p=p, q=q,
                                    hbm_GB=r['hbm']/1e9, tier_read_GB=r['tier_read']/1e9,
                                    tier_fill_GB=r['tier_fill']/1e9, pinned_GB=r['pinned_GB'],
                                    hbm_reduction_pct=red, seeds=len(SEEDS))
                    for B_R in B_R_LIST:
                        for beta in BETAS:
                            rows.append({**base_row, 'B_R': B_R, 'beta': beta, 'B_W': B_R*beta,
                                         'speedup_serial': BASE_T/step_ms(r, B_R, B_R*beta, 'serial'),
                                         'speedup_overlap': BASE_T/step_ms(r, B_R, B_R*beta, 'overlap')})
                    if done % 60 == 0:
                        print(f'  {done} 회  ({time.time()-t_start:.0f}s)')
    out = ROOT/'assets/sweep/policy_device_sweep.csv'
    with out.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f'\n{len(rows)} 행 -> {out}  ({time.time()-t_start:.0f}s)')

    # ---- 즉시 판독: p*(β) at 600 mm², LIP, q=0
    print('\n최적 p (600 mm², LIP 삽입, q=0, B_R=19)')
    print(f"{'β':>6} {'B_W':>6} {'p*':>6} {'speedup':>9}   |  겹침 p*  speedup")
    for beta in BETAS:
        cand = [r for r in rows if r['area_mm2']==600 and r['insert']=='LIP' and r['q']==0.0
                and r['B_R']==19.0 and abs(r['beta']-beta)<1e-9]
        bs = max(cand, key=lambda r: r['speedup_serial'])
        bo = max(cand, key=lambda r: r['speedup_overlap'])
        print(f"{beta:>6.2f} {19*beta:>6.1f} {bs['p']:>6.2f} {bs['speedup_serial']:>9.3f}   |"
              f"  {bo['p']:>5.2f}  {bo['speedup_overlap']:.3f}")
