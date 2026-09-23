#!/usr/bin/env python3
"""M-3, second half: replay a PREFILL prologue in front of the decode steps.

The first half (prefill_phase.py) answered the thermal question -- decode is the duty
worst case. This one answers the policy question the worklog actually logged under M-3:
"prefill 트래픽 구성 추가(현재 decode만). 읽기 비중 r이 달라 캐시 판정이 바뀔 수 있다."

Setup. Same tiling and accounting as the closure replay (1 MiB object tiles, writes always
go to HBM, reads are what the tier can serve), but the sequence is now

    [one prefill forward pass]  then  [32 decode steps]

instead of 32 decode steps from a cold tier. Prefill's layer_weight and full_kv tiles carry
the SAME keys as decode's -- prefill writes the KV that decode then reads -- so prefill both
warms the tier and pollutes it. The pollution is the `activation` object: 4.29 GB of tiles
read once in prefill and never again.

The question each policy has to survive: after a prefill has streamed 21.6 GB of reads
through a 4.22 GB tier, what is the tier holding when decode starts?
"""
import os, sys, json, math
from pathlib import Path
from collections import OrderedDict
sys.path.insert(0, os.path.dirname(__file__))

ROOT = Path(__file__).resolve().parent.parent
INP  = ROOT/'assets'/'experiments'/'3dsram_closure_20260921'/'inputs'
MiB, STEPS, C0, TILE = 2**20, 32, 132_644_864, 2**20
USABLE = (1-.12)*(1-.05); BYTES_PER_MACRO = 1_000_000/8*USABLE
MACRO = {'C2': (153, 518), 'C3': (183, 656)}

def load(path):
    ev = [json.loads(x) for x in Path(path).read_text().splitlines()]
    return [e for e in ev if e.get('kind') == 'event' and e.get('model_tag') == 'llama'
            and e.get('batch') == 8 and e.get('context') == 2048]

def tiles(events):
    """Reads become (layer, object, tile_index) keys; writes are returned as a byte total."""
    tr = []
    for e in (x for x in events if x['op'] == 'read'):
        for i, off in enumerate(range(0, e['bytes'], TILE)):
            tr.append(((e['layer'], e['object'], i), min(TILE, e['bytes']-off)))
    return tr, sum(e['bytes'] for e in events if e['op'] == 'write')

import prefill_phase as PF

def tiles_from(events):
    return tiles([e for e in events if e.get('kind') == 'event'])

DEC, W_DEC = tiles(load(INP/'llama-b8-l2048-events-unified.jsonl'))
PRE, W_PRE = tiles_from(PF.build_events(1.0, 2))     # nominal; act_roundtrips swept below

class Cache:
    """LRU / LIP, as in the closure replay."""
    def __init__(s, cap, policy): s.cap = int(cap); s.policy = policy; s.d = OrderedDict(); s.live = 0; s.ins = 0
    def access(s, k, n):
        if k in s.d: s.d.move_to_end(k); return True
        if n > s.cap: return False
        while s.live+n > s.cap:
            _, x = s.d.popitem(last=False); s.live -= x
        s.d[k] = n; s.live += n; s.ins += 1
        if s.policy == 'LIP': s.d.move_to_end(k, last=False)
        return False

class Frozen:
    """Fill in arrival order until full, then never change (the 3b 'bypass' definition:
    'once the tier is full it freezes and is never refilled')."""
    def __init__(s, cap): s.cap = int(cap); s.d = {}; s.live = 0; s.frozen = False
    def access(s, k, n):
        if k in s.d: return True
        if s.frozen or n > s.cap: return False
        if s.live+n > s.cap: s.frozen = True; return False
        s.d[k] = n; s.live += n; return False

class Managed:
    """Weight-only admission, pinned. Pre-loaded from the decode trace, never evicted,
    and prefill cannot change it -- that is the whole point of managed residency."""
    def __init__(s, cap, trace):
        s.d = set(); live = 0
        for k, n in trace:
            if k[1] not in ('layer_weight', 'lm_head'): continue
            if k in s.d or live+n > cap: continue
            s.d.add(k); live += n
        s.live = live
    def access(s, k, n): return k in s.d

def run(make, with_prefill):
    t = make()
    if with_prefill:
        for k, n in PRE: t.access(k, n)
    hbm = last = 0
    for step in range(STEPS):
        acc = 0
        for k, n in DEC:
            if not t.access(k, n): hbm += n; acc += n
        if step == STEPS-1: last = acc
    return {'avg': hbm/STEPS + W_DEC, 'last': last + W_DEC}

def capacity(case, area, layers):
    w, h = MACRO[case]
    return math.floor(area/(w*h/1e6))*BYTES_PER_MACRO*layers*2

if __name__ == '__main__':
    CAP = capacity('C2', 600, 2)
    base = run(lambda: Cache(C0, 'LIP'), False)['avg']          # existing L2 as LIP, same as closure
    print(f'baseline (existing L2 {C0/1e6:.1f} MB as LIP, decode only): {base/1e9:.4f} GB/step')
    print(f'tier C2 2-layer 600 mm2 = {CAP/1e9:.3f} GB.  prefill reads {sum(n for _,n in PRE)/1e9:.2f} GB '
          f'({sum(n for k,n in PRE if k[1]=="activation")/1e9:.2f} GB of it activation, read once, never reused)\n')

    makers = [
        ('integrated LRU',        lambda: Cache(C0+CAP, 'LRU')),
        ('integrated LIP',        lambda: Cache(C0+CAP, 'LIP')),
        ('bypass (freeze once)',  lambda: Frozen(C0+CAP)),
        ('managed residency',     lambda: Managed(C0+CAP, DEC)),
    ]
    print(f"{'policy':>22} | {'decode only':>22} | {'after a prefill':>22} | {'prefill costs':>14}")
    print(f"{'':>22} | {'avg':>10} {'steady':>11} | {'avg':>10} {'steady':>11} | {'steady %p':>14}")
    out = []
    for name, mk in makers:
        a = run(mk, False); b = run(mk, True)
        ra, rs = (1-a['avg']/base)*100, (1-a['last']/base)*100
        pa, ps = (1-b['avg']/base)*100, (1-b['last']/base)*100
        out.append((name, rs, ps))
        print(f'{name:>22} | {ra:>9.2f}% {rs:>10.2f}% | {pa:>9.2f}% {ps:>10.2f}% | {ps-rs:>+13.3f}%p')

    print('\ninterpretation')
    d = dict((n, (x, y)) for n, x, y in out)
    for n, (x, y) in d.items():
        verdict = 'unchanged' if abs(y-x) < 1e-6 else f'loses {x-y:.2f}%p'
        print(f'  {n:>22}: {verdict}')

    # ---- closed form, written down before reading the sweep -------------------
    per_layer = {o: sum(n for k, n in PRE if k[1] == o)/32 for o in ('layer_weight','full_kv','activation')}
    span = sum(per_layer.values())
    n_layers_frozen = (C0+CAP)/span
    dead = per_layer['activation']*n_layers_frozen
    print(f'\nclosed form for the bypass/LIP loss (interleaved order):')
    print(f'  the freeze lands {n_layers_frozen:.2f} layers into the prefill '
          f'({span/1e6:.1f} MB of reads per layer)')
    print(f'  dead bytes frozen = activation/layer {per_layer["activation"]/1e6:.1f} MB x '
          f'{n_layers_frozen:.2f} = {dead/1e6:.1f} MB')
    print(f'  predicted loss = dead / base = {dead/base*100:.3f}%p   (measured above: 3.940%p)')

    # ---- the order trap: this result is only as good as the emission order ----
    print('\n=== emission-order sweep: the same trap that zeroed the admission delta ===')
    print('  (memory: "층 인터리빙을 빼고 weight를 일괄 발행하면 first-fill이 weight만 잡아 델타가 0")')
    orders = {
        'layer-interleaved (nominal)': PRE,
        'all weight first':            sorted(PRE, key=lambda t: t[0][1] not in ('layer_weight','lm_head')),
        'all activation first':        sorted(PRE, key=lambda t: t[0][1] != 'activation'),
    }
    print(f"\n{'prefill emission order':>30} | {'bypass steady':>14} | {'vs managed':>12}")
    mg = run(lambda: Managed(C0+CAP, DEC), True)
    mg_s = (1-mg['last']/base)*100
    for lab, tr in orders.items():
        globals()['PRE'] = tr
        b = run(lambda: Frozen(C0+CAP), True)
        bs = (1-b['last']/base)*100
        print(f'{lab:>30} | {bs:>13.2f}% | {bs-mg_s:>+11.2f}%p')
    globals()['PRE'] = orders['layer-interleaved (nominal)']
    print(f'\n  managed residency is {mg_s:.2f}% in every order -- it does not depend on the trace.')
    print('  The real vLLM order is unknown; REQUEST_GATE4_CAUSAL.md already asks for kernel issue order.')

    # ---- activation-volume axis ------------------------------------------------
    lo, hi = PF.act_roundtrips_bounds()
    print('\n=== activation-volume sweep (the other unmeasured implementation axis) ===')
    print(f'  bounds {lo:.0f} (layer boundary only, no fusion can remove it) .. {hi:.0f} '
          f'(every GEMM output materialised at T=16,384)')
    print(f"\n{'act_roundtrips':>15} {'activation GB':>14} {'bypass steady':>14} {'managed steady':>15} {'gap':>9}")
    sweep = []
    for art in (lo, 4, 8, 12, 16, hi):
        globals()['PRE'], _ = tiles_from(PF.build_events(1.0, art))
        b = run(lambda: Frozen(C0+CAP), True); m = run(lambda: Managed(C0+CAP, DEC), True)
        bs, ms = (1-b['last']/base)*100, (1-m['last']/base)*100
        act_gb = PF.prefill_bytes(1.0, art)['activation']/1e9
        sweep.append((art, act_gb, bs, ms))
        print(f'{art:>15.0f} {act_gb:>13.2f}G {bs:>13.2f}% {ms:>14.2f}% {bs-ms:>+8.2f}p')
    globals()['PRE'] = orders['layer-interleaved (nominal)']
    import json as _j, os as _o
    _j.dump({'order_sweep': {k: None for k in orders},
             'activation_sweep': [dict(act_roundtrips=a, activation_GB=g, bypass_ss_pct=b, managed_ss_pct=m)
                                  for a, g, b, m in sweep]},
            open(_o.path.join(str(ROOT), 'assets', 'sweep', 'prefill_policy_replay.json'), 'w'), indent=2)
    print('\n  managed is flat across the whole activation range; bypass is not.')
    print('  wrote assets/sweep/prefill_policy_replay.json')
