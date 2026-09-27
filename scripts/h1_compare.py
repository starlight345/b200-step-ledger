#!/usr/bin/env python3
"""H1/H2 analysis — frozen predictions vs measurements on the same GPU.

  1. DRAM bytes per step: error of each predictor (the primary accuracy metric).
  2. Optimal hitRatio: per (workload, set-aside) group, argmin of measured DRAM vs each predictor's argmin.
  3. Time: measured step time vs predicted (overlap / serial).
  4. H2 causal slope: inside one workload the kernels, launch shapes, addresses and requested bytes are
     identical across policy settings, so d(time)/d(DRAM bytes) there is the marginal cost of an HBM
     byte with compute held fixed — the quantity the cross-condition 6.40 TB/s fit could not give.

Usage: python3 h1_compare.py assets/sweep/h1_predictions_ampere.json assets/sweep/h1_measured_ampere.jsonl
"""
import json, sys, statistics as st
from collections import defaultdict

MiB = 1 << 20
PRED = ('no_residency', 'capacity_only', 'fixed_lru', 'cuda_policy', 'cuda_policy_lip')

def key(run): return json.dumps(run, sort_keys=True)

def group(run):
    w = f"llm ws={run['ws']:g}" if run['mode'] == 'llm' else f"clean hot={run['hot']:g}"
    return w

def load(pred_path, meas_path):
    P = {key(r['run']): r for r in json.load(open(pred_path))['runs']}
    rows = []
    for l in open(meas_path):
        m = json.loads(l)
        if 'counters' not in m or 'timing' not in m: continue
        p = P.get(key(m['run']))
        if p: rows.append((m['run'], p, m))
    return rows

def linfit(xs, ys):
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs); sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx else float('nan'); a = my - b * mx
    ss = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)); st_ = sum((y - my) ** 2 for y in ys)
    return a, b, 1 - ss / st_ if st_ else float('nan')

if __name__ == '__main__':
    rows = load(sys.argv[1], sys.argv[2])
    PRED = tuple(rows[0][1]['dram_bytes'].keys())      # every predictor frozen in the file (v2 appears from H1c on)
    print(f'{len(rows)} settings with both passes; predictors: {", ".join(PRED)}\n')

    # 1. DRAM bytes
    print('=== 1. DRAM read bytes per step: prediction error (MiB; relative to step bytes) ===')
    print(f"{'predictor':<16}{'MAE MiB':>10}{'max MiB':>10}{'MAE %step':>11}{'within 5%':>11}")
    err = {}
    for k in PRED:
        e = [(p['dram_bytes'][k] - m['counters']['dram_read_per_step']) for _, p, m in rows]
        rel = [abs(x) / p['step_bytes'] for x, (_, p, _) in zip(e, rows)]
        err[k] = e
        print(f"{k:<16}{st.mean(abs(x) for x in e) / MiB:>10.2f}{max(abs(x) for x in e) / MiB:>10.2f}"
              f"{100 * st.mean(rel):>10.2f}%{100 * sum(r < .05 for r in rel) / len(rel):>10.0f}%")

    by = defaultdict(list)
    for run, p, m in rows: by[group(run)].append((run, p, m))
    print('\n  per workload, MAE in MiB:')
    print(f"  {'workload':<18}" + ''.join(f'{k[:11]:>13}' for k in PRED))
    for g, rs in sorted(by.items()):
        print(f'  {g:<18}' + ''.join(
            f"{st.mean(abs(p['dram_bytes'][k] - m['counters']['dram_read_per_step']) for _, p, m in rs) / MiB:>13.2f}"
            for k in PRED))

    # 2. optimal hitRatio
    print('\n=== 2. Best hitRatio per (workload, set-aside): measured vs predicted argmin of DRAM ===')
    gs = defaultdict(list)
    for run, p, m in rows:
        if run['window'] > 0 and run['setaside'] > 0: gs[(group(run), run['setaside'])].append((run, p, m))
    hits = {k: 0 for k in ('cuda_policy', 'cuda_policy_lip', 'capacity_only', 'v2') if k in PRED}
    print(f"  {'group':<28}{'S MiB':>7}{'measured':>10}" + ''.join(f'{k[:9]:>10}' for k in hits) + "   measured DRAM at best (MiB)")
    for (g, sa), rs in sorted(gs.items()):
        rs = sorted(rs, key=lambda t: t[0]['hitratio'])
        mbest = min(rs, key=lambda t: t[2]['counters']['dram_read_per_step'])
        pb = {k: min(rs, key=lambda t: t[1]['dram_bytes'][k])[0]['hitratio'] for k in hits}
        for k in hits:
            # a predictor "gets it" if its argmin lands on a setting whose measured DRAM is within 2% of the best
            mb = mbest[2]['counters']['dram_read_per_step']
            md = [t for t in rs if t[0]['hitratio'] == pb[k]][0][2]['counters']['dram_read_per_step']
            hits[k] += (md - mb) <= 0.02 * mbest[1]['step_bytes']
        print(f"  {g:<28}{sa:>7.1f}{mbest[0]['hitratio']:>10.3f}" + ''.join(f'{pb[k]:>10.3f}' for k in hits)
              + f"   {mbest[2]['counters']['dram_read_per_step'] / MiB:7.1f}")
    print('  groups where the predicted best hitRatio is (near-)optimal on hardware: ' +
          ', '.join(f'{k} {v}/{len(gs)}' for k, v in hits.items()))

    # 3. time
    print('\n=== 3. Step time: measured vs predicted (mean abs % error) ===')
    for k in [k for k in ('capacity_only', 'fixed_lru', 'cuda_policy', 'cuda_policy_lip', 'v2') if k in PRED]:
        for mode in [m for m in ('overlap_ms', 'serial_ms') if m in rows[0][1]['time'][k]]:
            e = [abs(p['time'][k][mode] - m['timing']['ms_median']) / m['timing']['ms_median'] for _, p, m in rows]
            print(f'  {k:<16}{mode:<11}{100 * st.mean(e):6.1f}%')

    # 4. H2 causal slope
    print('\n=== 4. H2: time vs DRAM bytes with the kernels fixed (only the policy changes) ===')
    print(f"  {'workload':<18}{'n':>4}{'DRAM span MiB':>15}{'slope ms/GB':>13}{'=> TB/s':>9}{'R2':>7}")
    for g, rs in sorted(by.items()):
        xs = [m['counters']['dram_read_per_step'] / 1e9 for _, _, m in rs]
        ys = [m['timing']['ms_median'] for _, _, m in rs]
        if max(xs) - min(xs) < 0.005: print(f'  {g:<18}{len(rs):>4}   (DRAM does not vary)'); continue
        a, b, r2 = linfit(xs, ys)
        print(f'  {g:<18}{len(rs):>4}{(max(xs) - min(xs)) * 1e3 / 1.048576:>15.1f}{b:>13.4f}{1 / b if b > 0 else float("nan"):>9.3f}{r2:>7.3f}')
    print('  (calibrated streaming DRAM rate on this GPU: see h1_calib_ampere.json)')
