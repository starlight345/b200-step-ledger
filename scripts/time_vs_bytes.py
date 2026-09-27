#!/usr/bin/env python3
"""Does a DRAM-traffic saving become a time saving? Measured bytes (ncu counters) vs measured time, per workload.

Every H1c / R2 / R3 setting was measured twice: counters (DRAM read bytes per step) and timing (a separate pass).
  H1c: time = ms_median of the synthetic step (one kernel per layer, bandwidth-bound by construction).
  R2/R3: time = median over steps of the summed GPU kernel time of one decode step (kernel_ms; excludes launch gaps).
Per workload: baseline vs the lowest-DRAM setting (bytes and time change), the correlation of bytes and time over all
its settings, and the slope (us of time per MiB of DRAM read), next to 1 / DRAM bandwidth (0.85 us/MiB at 1.23 TB/s):
a slope near 1/BW means each saved MiB saves its transfer time; the share of the step it saves depends on how much of
the step is DRAM time (bytes / BW) at all.
Usage: python3 scripts/time_vs_bytes.py
"""
import json, os, statistics as st
from collections import defaultdict

MiB, BW = 1 << 20, 1.23e12
SETS = (('h1c', 'assets/sweep/h1c_measured_ampere.jsonl'), ('r2', 'assets/sweep/r2_measured_ampere.jsonl'),
        ('r3', 'assets/sweep/r3_measured_ampere.jsonl'))

def wl(q):
    if 'model' in q: return f"{q['model']}/B{q['batch']}/c{q['context']}"
    return '/'.join(f'{k}{q[k]}' for k in sorted(q) if k not in ('window', 'setaside', 'hitratio', 'mode'))

def t_ms(r): return st.median(r['timing']['kernel_ms']) if 'kernel_ms' in r['timing'] else r['timing']['ms_median']

if __name__ == '__main__':
    out = {}
    print(f"{'set':<5}{'workload':<30}{'n':>4}{'DRAM base':>10}{'best':>8}{'saved':>7}   {'time base':>10}{'best':>8}{'saved':>7}"
          f"{'DRAM time':>10}{'corr':>7}{'slope':>7}  (MiB, ms; slope us/MiB, 1/BW = {MiB / BW * 1e6:.2f})")
    for name, path in SETS:
        if not os.path.exists(path): continue
        g = defaultdict(list)
        for r in map(json.loads, open(path)):
            if 'counters' in r and 'timing' in r: g[wl(r['run'])].append(r)
        for w, rs in g.items():
            bs = [r for r in rs if r['run']['window'] == 0 and r['run']['setaside'] == 0]
            if not bs: continue
            b, best = bs[0], min(rs, key=lambda r: r['counters']['dram_read_per_step'])
            xs = [r['counters']['dram_read_per_step'] for r in rs]; ys = [t_ms(r) for r in rs]
            mx, my = st.mean(xs), st.mean(ys)
            sxx, syy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
            sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            d = dict(n=len(rs), dram_base_mib=xs[rs.index(b)] / MiB, dram_best_mib=xs[rs.index(best)] / MiB,
                     time_base_ms=t_ms(b), time_best_ms=t_ms(best), dram_time_base_ms=xs[rs.index(b)] / BW * 1e3,
                     corr=sxy / (sxx * syy) ** .5 if sxx and syy else 0.0,
                     slope_us_per_mib=sxy / sxx * MiB * 1e3 if sxx else 0.0)
            d['dram_saved_pct'] = 100 * (1 - d['dram_best_mib'] / d['dram_base_mib']) if d['dram_base_mib'] else 0.0
            d['time_saved_pct'] = 100 * (1 - d['time_best_ms'] / d['time_base_ms'])
            out[f'{name}:{w}'] = d
            print(f"{name:<5}{w:<30}{d['n']:>4}{d['dram_base_mib']:>10.1f}{d['dram_best_mib']:>8.1f}{d['dram_saved_pct']:>6.1f}%   "
                  f"{d['time_base_ms']:>10.3f}{d['time_best_ms']:>8.3f}{d['time_saved_pct']:>6.1f}%{d['dram_time_base_ms']:>10.3f}"
                  f"{d['corr']:>+7.2f}{d['slope_us_per_mib']:>7.2f}")
    json.dump(out, open('assets/sweep/time_vs_bytes.json', 'w'), indent=1)
    print('wrote assets/sweep/time_vs_bytes.json')
