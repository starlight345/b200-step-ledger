#!/usr/bin/env python3
"""Do rungs 3, 3b and 4 separate once the trace stops being cyclic? (2026-09-21)

Five policies on the same aperiodic trace, all counting BOTH sides of the tier:
    LRU            demand cache, LRU replacement
    LIP            demand cache, LRU-insertion (new lines enter at LRU)
    LIP-bypass     LIP with no-allocate-on-miss once full: fill once, then freeze  (rung 3b)
    managed        pin weight tiles explicitly; KV never enters the tier           (rung 4)
    managed+KV     pin weight first, give the remainder to KV by LRU               (rung 4b)
Reported per policy: HBM bytes/step, tier read (hits), tier fill (writes). The closure replay
counted only the first; the fill side is what flips the verdict.
"""
import json, math, os, csv, sys, collections
from collections import OrderedDict
HERE = os.path.dirname(os.path.abspath(__file__))
MiB = 2**20; TILE = MiB; C0 = 132_644_864; GB = 1e9
USABLE = (1-.12)*(1-.05); BPM = 1_000_000/8*USABLE
MACRO = {'C2': (153, 518), 'C3': (183, 656)}
WEIGHT_OBJ = ('layer_weight', 'lm_head', 'embedding_gather')

def tiles(path):
    ev = [json.loads(x) for x in open(path)]
    steps = collections.defaultdict(list); writes = collections.Counter()
    for e in ev:
        if e['op'] == 'write': writes[e['step']] += e['bytes']; continue
        for i, off in enumerate(range(0, e['bytes'], TILE)):
            steps[e['step']].append(((e['layer'], e['object'], e['req'], i),
                                     min(TILE, e['bytes']-off), e['object']))
    return [steps[s] for s in sorted(steps)], [writes[s] for s in sorted(steps)]

class Tier:
    """One capacity. policy in {LRU, LIP, LIP-bypass, managed, managed+KV, managed+oracleKV}.

    managed+oracleKV is the FAIRNESS CONTROL the peer session asked for: it pins weights and then
    admits KV only from requests whose remaining lifetime is long enough to amortize, using the
    full trace (an oracle no runtime has). It is the ceiling any lifetime-aware KV admission could
    reach. If the oracle still cannot beat pure-weight managed, 'reject KV' is proof-grade."""
    def __init__(s, cap, policy, lifetime=None, min_life=0):
        s.cap = int(cap); s.p = policy; s.d = OrderedDict(); s.live = 0
        s.read = 0; s.fill = 0; s.frozen = False
        s.lifetime = lifetime or {}      # (req, step) -> steps remaining
        s.min_life = min_life; s.step = 0
    def access(s, k, n, obj):
        if k in s.d:
            s.read += n
            if s.p in ('LRU',): s.d.move_to_end(k)
            return True
        if n > s.cap: return False
        if s.p == 'managed' and obj not in WEIGHT_OBJ: return False      # KV never admitted
        if s.p == 'managed+oracleKV' and obj not in WEIGHT_OBJ:
            if s.lifetime.get((k[2], s.step), 0) < s.min_life: return False   # too short-lived to amortize
            if s.live + n > s.cap: return False                               # weights hold their ground
        if s.p == 'LIP-bypass' and s.frozen: return False                # no-allocate once full
        if s.p == 'managed+KV' and obj not in WEIGHT_OBJ and s.live + n > s.cap:
            return False                                                 # weights hold; KV only fills slack
        while s.live + n > s.cap:
            if not s.d: return False
            kk, x = s.d.popitem(last=False)
            if s.p in ('managed', 'managed+KV', 'managed+oracleKV') and kk[1] in WEIGHT_OBJ:  # never evict a pinned weight
                s.d[kk] = x; s.d.move_to_end(kk, last=False); return False
            s.live -= x
        s.d[k] = n; s.live += n; s.fill += n
        if s.p != 'LRU': s.d.move_to_end(k, last=False)
        if s.p == 'LIP-bypass' and s.live >= s.cap: s.frozen = True   # exact: a 0.999 threshold left 3.16 MB unfrozen and showed up as a constant 0.0185 %p residual
        return False

def composition(t):
    c = collections.Counter()
    for k, n in t.d.items(): c['weight' if k[1] in WEIGHT_OBJ else 'kv'] += n
    tot = sum(c.values()) or 1
    return c['weight']/tot, c['kv']/tot, tot

def lifetimes(path):
    """(req, step) -> steps that request still has left. Oracle knowledge from the whole trace."""
    ev = [json.loads(x) for x in open(path)]
    last = {}
    for e in ev:
        if e['req'] >= 0: last[e['req']] = max(last.get(e['req'], -1), e['step'])
    out = {}
    for e in ev:
        if e['req'] >= 0: out[(e['req'], e['step'])] = last[e['req']] - e['step']
    return out

def run(steps_tiles, writes, cap, policy, warm=1, lifetime=None, min_life=0):
    """Returns both statistics the two sessions were quoting: the 32-step average AND the
    steady state (last step), plus the resident-set composition per step."""
    t = Tier(C0 + cap, policy, lifetime, min_life); comp_series = []
    for _ in range(warm + 1):
        t.read = t.fill = 0; hbm = 0; n = 0; comp_series = []
        last_hbm = last_read = last_fill = 0
        for i, st in enumerate(steps_tiles):
            t.step = i
            h0, r0, f0 = hbm, t.read, t.fill
            for k, b, obj in st:
                if not t.access(k, b, obj): hbm += b
            hbm += writes[i]; n += 1
            last_hbm, last_read, last_fill = hbm-h0, t.read-r0, t.fill-f0
            w, kv, tot = composition(t); comp_series.append((w, kv, tot))
    w, kv, tot = comp_series[-1]
    return dict(hbm=hbm/n, tier_read=t.read/n, tier_fill=t.fill/n,
                hbm_ss=last_hbm, tier_read_ss=last_read, tier_fill_ss=last_fill,
                resident_weight_frac=w, resident_kv_frac=kv, resident_GB=tot/GB,
                comp_series=comp_series)

def cap_bytes(case, area, layers=2, dies=2):
    w, h = MACRO[case]; return math.floor(area/(w*h/1e6)) * BPM * layers * dies

if __name__ == '__main__':
    POL = ['LRU', 'LIP', 'LIP-bypass', 'managed', 'managed+KV']
    cap = cap_bytes('C2', 600)
    rows = []
    print(f"3D 티어 C2 600 mm² 2층 2다이 = {cap/GB:.3f} GB, 기존 L2 {C0/GB:.3f} GB 포함 총 {(C0+cap)/GB:.3f} GB\n")
    print("통계 규약 (동료 세션 제안 채택): 정상 상태 = 마지막 스텝, 평균 = 128스텝 평균. 두 통계를 모두 적는다.\n")
    print(f"{'mean_len':>9s} {'회전':>5s} {'정책':12s} {'감소 평균':>9s} {'감소 정상':>9s} {'충전 평균':>9s} {'충전 정상':>9s} {'상주 weight':>11s} {'상주 KV':>8s}")
    for L in (10000, 1000, 300, 120, 60, 30, 16, 10):
        p = os.path.join(HERE, 'inputs', f'aperiodic-b8-s128-L{L}.jsonl')
        stl, wr = tiles(p)
        D = sum(b for st in stl for _, b, _ in st)/len(stl) + sum(wr)/len(wr)
        base = run(stl, wr, 0, 'LIP')       # existing L2 only, LIP — same baseline convention as the closure replay
        nreq = len({k[2] for st in stl for k, _, _ in st if k[2] >= 0})
        for pol in POL:
            r = run(stl, wr, cap, pol)
            red = 100*(1 - r['hbm']/base['hbm']); red_ss = 100*(1 - r['hbm_ss']/base['hbm_ss'])
            rows.append(dict(mean_len=L, requests=nreq, policy=pol, D_GB=D/GB,
                             hbm_avg_GB=r['hbm']/GB, hbm_ss_GB=r['hbm_ss']/GB,
                             reduction_avg_pct=red, reduction_ss_pct=red_ss,
                             tier_read_avg_GB=r['tier_read']/GB, tier_fill_avg_GB=r['tier_fill']/GB,
                             tier_read_ss_GB=r['tier_read_ss']/GB, tier_fill_ss_GB=r['tier_fill_ss']/GB,
                             resident_weight_frac=r['resident_weight_frac'],
                             resident_kv_frac=r['resident_kv_frac'], resident_GB=r['resident_GB']))
            print(f"{L:9d} {nreq:5d} {pol:12s} {red:+8.3f}% {red_ss:+8.3f}% {r['tier_fill']/GB:8.3f}G "
                  f"{r['tier_fill_ss']/GB:8.3f}G {100*r['resident_weight_frac']:10.1f}% {100*r['resident_kv_frac']:7.1f}%")
        print()
    with open(os.path.join(HERE, 'outputs', 'aperiodic_policies.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print("wrote outputs/aperiodic_policies.csv")
