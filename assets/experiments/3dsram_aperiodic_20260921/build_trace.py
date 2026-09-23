#!/usr/bin/env python3
"""Aperiodic decode trace: requests arrive, generate, and leave (2026-09-21).

The 3dsram_closure_20260921 replay repeats ONE step 32 times, so the tile identity set never
changes. On such a cyclic trace LIP's first-fill retention is identical to pinning: measured
overlap between the LIP resident set and the trace prefix is 3149/3151. Rungs 3 (demand cache)
and 4 (managed residency) therefore cannot separate there, by construction.

This trace introduces the only thing that separates them: KV identity churn.
    - weights are request-invariant: the same tiles every step, forever
    - each request owns KV tiles keyed by its request id, which appear on arrival and
      disappear on departure
    - a request's KV grows by one token per step it lives
Arrivals are Poisson, lengths are drawn from a lognormal fitted to typical decode lengths, and
the batch is capped. Seeded, so the ledger is reproducible byte-for-byte.
"""
import json, math, random, os, argparse

D_MODEL = 4096; LAYERS = 32; DT = 2
KV_PER_TOKEN_PER_LAYER = 2 * 8 * 128 * DT          # 2(K,V) x 8 kv heads x 128 dim x 2 B = 4096 B
WEIGHT_PER_LAYER = 436_224_000                      # from the preserved ledger
LM_HEAD = 128256 * D_MODEL * DT
EMB_GATHER_PER_REQ = D_MODEL * DT

def build(steps=256, target_batch=8, seed=20260921, mean_len=180, sigma=0.8, prefill_ctx=2048):
    """mean_len is the churn knob: long requests -> near-cyclic trace, short -> high KV turnover."""
    rng = random.Random(seed)
    events = []; live = {}; next_id = 0; arrivals = []
    lam = target_batch / mean_len                   # arrival rate that holds the batch near target
    for _ in range(target_batch):                   # pre-populate so step 0 is already in steady state
        L = max(8, int(rng.lognormvariate(math.log(mean_len), sigma)))
        live[next_id] = dict(ctx=prefill_ctx, remaining=rng.randint(1, L), born=-1); next_id += 1
    for s in range(steps):
        n_arr = 0
        while len(live) + n_arr < target_batch and rng.random() < max(lam, 0.5): n_arr += 1
        for _ in range(n_arr):
            L = max(8, int(rng.lognormvariate(math.log(mean_len), sigma)))
            live[next_id] = dict(ctx=prefill_ctx, remaining=L, born=s); arrivals.append((s, next_id, L)); next_id += 1
        # Real decode order interleaves per layer: weight[l], then every live request's KV[l].
        # The earlier version emitted all 32 weights first, which made first-fill trivially
        # weight-only and hid any difference between bypass and explicit pinning.
        for rid in sorted(live):
            events.append(dict(step=s, layer=-1, object='embedding_gather', req=rid, op='read', bytes=EMB_GATHER_PER_REQ))
        for lyr in range(LAYERS):
            events.append(dict(step=s, layer=lyr, object='layer_weight', req=-1, op='read', bytes=WEIGHT_PER_LAYER))
            for rid, st in sorted(live.items()):
                events.append(dict(step=s, layer=lyr, object='req_kv', req=rid, op='read',
                                   bytes=st['ctx'] * KV_PER_TOKEN_PER_LAYER))
                events.append(dict(step=s, layer=lyr, object='req_kv', req=rid, op='write',
                                   bytes=KV_PER_TOKEN_PER_LAYER))
        events.append(dict(step=s, layer=LAYERS, object='lm_head', req=-1, op='read', bytes=LM_HEAD))
        done = [r for r, st in live.items() if st['remaining'] <= 1]
        for r in done: del live[r]
        for st in live.values(): st['ctx'] += 1; st['remaining'] -= 1
    return events, arrivals

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--steps', type=int, default=256)
    ap.add_argument('--batch', type=int, default=8); ap.add_argument('--seed', type=int, default=20260921)
    ap.add_argument('--mean-len', type=int, default=180)
    ap.add_argument('--ctx', type=int, default=2048)
    a = ap.parse_args()
    ev, arr = build(a.steps, a.batch, a.seed, mean_len=a.mean_len, prefill_ctx=a.ctx)
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, 'inputs', f'aperiodic-b{a.batch}-s{a.steps}-L{a.mean_len}-N{a.ctx}.jsonl')
    with open(p, 'w') as f:
        for e in ev: f.write(json.dumps(e) + '\n')
    GB = 1e9
    import collections
    per = collections.Counter(); byobj = collections.defaultdict(int); batch = collections.Counter()
    for e in ev:
        per[e['step']] += e['bytes']; byobj[(e['object'], e['op'])] += e['bytes']
        if e['object'] == 'embedding_gather': batch[e['step']] += 1
    print(f"wrote {len(ev):,} events -> {os.path.relpath(p, here)}")
    print(f"  스텝 {a.steps}, 요청 {len(arr)}개 도착, 배치 평균 {sum(batch.values())/a.steps:.2f} (최소 {min(batch.values())} 최대 {max(batch.values())})")
    print(f"  스텝당 트래픽 평균 {sum(per.values())/a.steps/GB:.3f} GB (최소 {min(per.values())/GB:.3f} 최대 {max(per.values())/GB:.3f})")
    for k, v in sorted(byobj.items()): print(f"    {k[0]:18s} {k[1]:5s} {v/a.steps/GB:8.4f} GB/step")
    ids = {e['req'] for e in ev if e['req'] >= 0}
    print(f"  고유 요청 id {len(ids)}개 -> KV 타일 정체성이 실제로 바뀐다 (주기 트레이스에는 없던 축)")
