#!/usr/bin/env python3
"""발행 순서에 결과가 의존하는가 — 정책 결과를 쓰기 전에 반드시 통과해야 하는 검사.

보존 장부의 순서는 층 단위 인터리빙(weight -> kv)이고 embedding_gather 가 맨 끝이다.
이것은 실제 실행 순서가 아니라 **거친 모델링 선택**이므로, 결론이 순서에 걸려 있으면
p* = 0.02 같은 결과는 그 trace 의 성질이지 설계의 성질이 아니다.

여섯 순서를 비교한다.
  L0 preserved       장부 그대로 (weight, kv) x32, lm_head, embedding  ← 현재
  L1 forward         embedding, (weight, kv) x32, lm_head              ← 올바른 forward
  L2 weight-first    모든 weight -> 모든 kv
  L3 kv-first        모든 kv -> 모든 weight
  L4 operation-aware 층마다 QKV -> KV read -> O -> MLP                  ← 실제 연산 순서에 가장 가까움
  L5 shuffled        완전 무작위 (대조군)
"""
import json, math, random, statistics
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT/'assets/experiments/3dsram_closure_20260921'
MiB = 2**20; C0 = 132_644_864; STEPS = 32
ev = [json.loads(x) for x in (EXP/'inputs/llama-b8-l2048-events-unified.jsonl').read_text().splitlines()]
ev = [e for e in ev if e.get('kind') == 'event' and e.get('model_tag') == 'llama'
      and e.get('batch') == 8 and e.get('context') == 2048]
W_NATIVE = sum(e['bytes'] for e in ev if e['op'] == 'write')
RD = [e for e in ev if e['op'] == 'read']
CAP = math.floor(600/0.079254)*(1_000_000/8*0.836)*2*2 + C0
T0_MS, B_HBM = 1.85, 6.40

# Llama-3.1-8B 층 하나의 weight 분해 (2 B/value)
QKV = (4096*4096 + 2*4096*1024)*2          # 50,331,648  KV read 앞
O   = (4096*4096)*2                        # 33,554,432  뒤
MLP = (3*4096*14336)*2                     # 352,321,536 뒤

def tiles_of(layer, obj, nbytes, base=0):
    out = []
    for i, off in enumerate(range(0, nbytes, MiB)):
        out.append(((layer, obj, base+i), min(MiB, nbytes-off)))
    return out

def build(order):
    W = {e['layer']: e['bytes'] for e in RD if e['object'] == 'layer_weight'}
    K = {e['layer']: e['bytes'] for e in RD if e['object'] == 'full_kv'}
    LM = next(e for e in RD if e['object'] == 'lm_head')
    EM = next(e for e in RD if e['object'] == 'embedding_gather')
    t = []
    if order == 'L0':
        for e in RD: t += tiles_of(e['layer'], e['object'], e['bytes'])
    elif order == 'L1':
        t += tiles_of(-1, 'embedding_gather', EM['bytes'])
        for l in sorted(W): t += tiles_of(l, 'layer_weight', W[l]); t += tiles_of(l, 'full_kv', K[l])
        t += tiles_of(32, 'lm_head', LM['bytes'])
    elif order == 'L2':
        t += tiles_of(-1, 'embedding_gather', EM['bytes'])
        for l in sorted(W): t += tiles_of(l, 'layer_weight', W[l])
        t += tiles_of(32, 'lm_head', LM['bytes'])
        for l in sorted(K): t += tiles_of(l, 'full_kv', K[l])
    elif order == 'L3':
        for l in sorted(K): t += tiles_of(l, 'full_kv', K[l])
        t += tiles_of(-1, 'embedding_gather', EM['bytes'])
        for l in sorted(W): t += tiles_of(l, 'layer_weight', W[l])
        t += tiles_of(32, 'lm_head', LM['bytes'])
    elif order == 'L4':                     # 실제 연산 순서
        t += tiles_of(-1, 'embedding_gather', EM['bytes'])
        for l in sorted(W):
            nb = W[l]; q = min(QKV, nb); o = min(O, nb-q); m = nb-q-o
            t += tiles_of(l, 'layer_weight', q, 0)                       # QKV proj
            t += tiles_of(l, 'full_kv', K[l])                            # attention
            t += tiles_of(l, 'layer_weight', o, 10_000)                  # O proj
            t += tiles_of(l, 'layer_weight', m, 20_000)                  # MLP
        t += tiles_of(32, 'lm_head', LM['bytes'])
    elif order == 'L5':
        for e in RD: t += tiles_of(e['layer'], e['object'], e['bytes'])
        random.Random(20260923).shuffle(t)
    return t

def replay(trace, p, q, seed=7):
    rng = random.Random(seed)
    pinned, live = set(), 0
    if q > 0:
        budget = CAP*q
        for k, n in trace:
            if live + n > budget: break
            pinned.add(k); live += n
    dyn_cap = CAP - live; d = OrderedDict(); dyn = 0
    for s in range(STEPS):
        hbm = tr = tw = 0
        for k, n in trace:
            if k in pinned: tr += n; continue
            if k in d: tr += n; continue
            hbm += n
            if p <= 0 or n > dyn_cap or rng.random() >= p: continue
            while dyn + n > dyn_cap:
                if not d: break
                _, x = d.popitem(last=False); dyn -= x
            d[k] = n; dyn += n; tw += n; d.move_to_end(k, last=False)
    return hbm + W_NATIVE, tr, tw

if __name__ == '__main__':
    NAMES = {'L0':'preserved (현재)','L1':'forward (올바른 순서)','L2':'weight-first',
             'L3':'kv-first','L4':'operation-aware','L5':'shuffled (대조군)'}
    traces = {k: build(k) for k in NAMES}
    base = None
    for k, t in traces.items():
        assert abs(sum(n for _, n in t) - 17_157_390_336) < 2_000_000, (k, sum(n for _,n in t))
    BASE_HBM = 17_157_390_336 - C0*(STEPS-1)/STEPS + W_NATIVE
    BASE_T = T0_MS + BASE_HBM/1e9/B_HBM

    print(f'기준 step {BASE_T:.4f} ms · 티어 {CAP/1e9:.3f} GB · 32스텝 · 시드 3개\n')
    PS = [0.0, 0.02, 0.10, 0.50, 1.0]
    print(f"{'순서':<22}" + ''.join(f'p={p:<7.2f}' for p in PS) + '   q=1 (전량 고정)')
    print(f"{'':<22}" + '  HBM 감소 [%] / 충전 [GB/step]')
    for key, name in NAMES.items():
        t = traces[key]; cells = []
        for p in PS:
            rs = [replay(t, p, 0.0, sd) for sd in (7, 20260923, 31337)]
            red = statistics.mean(100*(1-r[0]/BASE_HBM) for r in rs)
            fil = statistics.mean(r[2]/1e9 for r in rs)
            cells.append(f'{red:5.2f}/{fil:5.2f}')
        rq = replay(t, 0.0, 1.0)
        qred = 100*(1-rq[0]/BASE_HBM)
        print(f'{name:<22}' + ' '.join(cells) + f'   {qred:6.2f}% / {rq[2]/1e9:.2f}')
