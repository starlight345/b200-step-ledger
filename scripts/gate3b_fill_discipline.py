#!/usr/bin/env python3
"""Gate 3b — fill discipline as a device-spec axis.

The ladder's fourth rung cannot be argued on HBM bytes: on a periodic trace the
managed bound and a scan-resistant cache land within 0.007 %p of each other.
This script re-states the rung on the axis where the configurations DO separate,
which is the device requirement: how much write capability the tier must have
before the configuration is even break-even.

Steady state means the LAST replayed step. The 32-step average is a different
statistic (it carries the cold fill) and the two must not be mixed -- LIP is
13.862 GB/step in steady state and 13.965 GB/step averaged.

Read-only with respect to the closure experiment; it re-replays the same ledger.
"""
from pathlib import Path
from collections import OrderedDict
import json, math, sys, csv

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'assets/experiments/3dsram_closure_20260921'
SRC = EXP / 'inputs/llama-b8-l2048-events-unified.jsonl'

MiB = 2**20; STEPS = 32; C0 = 132_644_864; TILE = MiB          # canon: existing_l2_bytes
USABLE = (1-.12)*(1-.05); BYTES_PER_MACRO = 1_000_000/8*USABLE
MACRO = {'C2': (153, 518), 'C3': (183, 656)}                   # canon: macro_dims_um
T0_MS = 1.852                                                  # canon: fixed_term_ms
B_HBM = 6.40                                                   # canon: hbm_effective_tbs

ev = [json.loads(x) for x in SRC.read_text().splitlines()]
ev = [e for e in ev if e.get('kind') == 'event' and e.get('model_tag') == 'llama'
      and e.get('batch') == 8 and e.get('context') == 2048]
reads = [e for e in ev if e['op'] == 'read']
F = sum(e['bytes'] for e in reads)
W_NATIVE = sum(e['bytes'] for e in ev if e['op'] == 'write')
trace = []
for e in reads:
    for i, off in enumerate(range(0, e['bytes'], TILE)):
        trace.append(((e['layer'], e['object'], i), min(TILE, e['bytes'] - off)))


class Cache:
    """LRU / LIP / LIP+bypass. bypass = stop allocating once the tier is full,
    so residency is written once and then frozen."""
    def __init__(self, cap, policy):
        self.cap = int(cap); self.policy = policy
        self.d = OrderedDict(); self.live = 0; self.ins = 0
        self.fill_bytes = 0; self.hit_bytes = 0

    def access(self, k, n):
        if k in self.d:
            self.d.move_to_end(k); self.hit_bytes += n; return True
        if n > self.cap:
            return False
        if self.policy == 'LIP_bypass' and self.live + n > self.cap:
            return False                      # frozen: miss does not allocate
        while self.live + n > self.cap:
            _, x = self.d.popitem(last=False); self.live -= x
        self.d[k] = n; self.live += n; self.ins += 1; self.fill_bytes += n
        if self.policy in ('LIP', 'LIP_bypass'):
            self.d.move_to_end(k, last=False)
        return False


def replay(cap, policy):
    """Return steady-state (last step) byte flows."""
    a = Cache(cap, policy)
    for s in range(STEPS):
        h0, f0, m0 = a.hit_bytes, a.fill_bytes, 0
        for k, n in trace:
            if not a.access(k, n):
                m0 += n
        if s == STEPS - 1:
            return {'tier_read': a.hit_bytes - h0, 'fill': a.fill_bytes - f0,
                    'hbm': m0 + W_NATIVE}
    raise AssertionError


def managed(cap):
    """Pinned prefix, written once at load, never refilled."""
    live, pinned = 0, set()
    for k, n in trace:
        if live + n > cap:
            continue
        pinned.add(k); live += n
    tier_read = sum(n for k, n in trace if k in pinned)
    return {'tier_read': tier_read, 'fill': 0, 'hbm': F - tier_read + W_NATIVE}


def capacity(case, area, layers):
    w, h = MACRO[case]
    n = math.floor(area / (w * h / 1e6))
    return n * BYTES_PER_MACRO * layers * 2


def step_ms(D_hbm, R, W, B_R, B_W, mode):
    """D_hbm, R, W in bytes; B_* in TB/s -> ms (GB/(TB/s) is already ms)."""
    t_hbm = D_hbm / 1e9 / B_HBM
    t_tier = R / 1e9 / B_R + (W / 1e9 / B_W if W else 0.0)
    return T0_MS + (t_hbm + t_tier if mode == 'serial' else max(t_hbm, t_tier))


def required_BW(D_hbm, R, W, B_R, mode, D_base):
    """Minimum absolute write bandwidth (TB/s) for speedup >= 1. None = no
    constraint (nothing to write); inf = unreachable at any B_W."""
    if W == 0:
        return None
    budget = (D_base / 1e9 / B_HBM) - (R / 1e9 / B_R) if mode == 'overlap' else \
             ((D_base - D_hbm) / 1e9 / B_HBM) - (R / 1e9 / B_R)
    return float('inf') if budget <= 0 else (W / 1e9) / budget


CASE, LAYERS = 'C2', 2
base = replay(C0, 'LIP')
D_base_naive = base['hbm']
# Baseline step time is anchored on the canonical 17.031 GB/step, which is the
# existing-L2 LIP replay; keep the two consistent.
D_BASE = D_base_naive
T_BASE = T0_MS + D_BASE / 1e9 / B_HBM

print(f"ledger: F = {F/1e9:.4f} GB/step read, native write {W_NATIVE/1e6:.3f} MB/step")
print(f"baseline (existing L2 {C0/1e6:.1f} MB, LIP): HBM {D_BASE/1e9:.4f} GB/step,"
      f" step {T_BASE:.4f} ms\n")

rows = []
for area in (600, 800):
    cap = capacity(CASE, area, LAYERS)
    configs = {
        'integrated LRU':        replay(C0 + cap, 'LRU'),
        'integrated LIP':        replay(C0 + cap, 'LIP'),
        'integrated LIP+bypass': replay(C0 + cap, 'LIP_bypass'),
        'managed residency':     managed(C0 + cap),
    }
    print(f"===== {CASE} {LAYERS}L {area} mm^2 : tier {cap/1e9:.3f} GB "
          f"(+ existing L2 -> {(C0+cap)/1e9:.3f} GB) =====")
    print(f"{'config':24s} {'HBM red':>9s} {'tier read':>10s} {'fill':>10s} "
          f"{'fill/D':>8s} | required B_W (TB/s) for speedup>=1")
    print(f"{'':24s} {'':>9s} {'GB/step':>10s} {'GB/step':>10s} {'':>8s} | "
          f"{'ser B_R=19':>11s} {'ovl B_R=19':>11s} {'ser B_R=15':>11s} {'ovl B_R=15':>11s}")
    for name, x in configs.items():
        red = 100 * (1 - x['hbm'] / D_BASE)
        cells = []
        for mode, br in (('serial', 19.0), ('overlap', 19.0),
                         ('serial', 15.0), ('overlap', 15.0)):
            r = required_BW(x['hbm'], x['tier_read'], x['fill'], br, mode, D_BASE)
            cells.append('  none' if r is None else
                         ('  impossible' if r == float('inf') else f'{r:11.2f}'))
        print(f"{name:24s} {red:+8.4f}% {x['tier_read']/1e9:10.4f} "
              f"{x['fill']/1e9:10.4f} {100*x['fill']/(F+W_NATIVE):7.2f}% |"
              + ''.join(cells))
        rows.append(dict(area_mm2=area, config=name, hbm_reduction_pct=round(red, 4),
                         tier_read_GB=round(x['tier_read']/1e9, 4),
                         fill_GB=round(x['fill']/1e9, 4),
                         fill_frac_of_D_pct=round(100*x['fill']/(F+W_NATIVE), 2)))
    print()
    print(f"{'config':24s} " + ' '.join(f"{f'{m[:3]} {br}/{bw}':>12s}"
          for m in ('serial', 'overlap') for br, bw in ((19, 19), (19, 5), (15, 5))))
    for name, x in configs.items():
        outs = []
        for mode in ('serial', 'overlap'):
            for br, bw in ((19, 19), (19, 5), (15, 5)):
                t = step_ms(x['hbm'], x['tier_read'], x['fill'], br, bw, mode)
                outs.append(f"{T_BASE/t:12.3f}")
        print(f"{name:24s} " + ' '.join(outs))
        rows[-len(configs) + list(configs).index(name)]  # keep order
    print()

with (ROOT / 'assets/sweep/gate3b_fill_discipline.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("wrote assets/sweep/gate3b_fill_discipline.csv")
