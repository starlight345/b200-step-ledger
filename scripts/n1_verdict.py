#!/usr/bin/env python3
"""N1 verdict: the statements pre-registered at 2026-09-27 19:54 KST (WORKLOG), checked on the measured data.

  1. for both workloads, the measured DRAM spread over the 9 settings (max - min) is <= 3 % of the logical step;
  2. every frozen predictor's MAE is <= 5 % of the logical step (mean of |error| / step over all measured settings);
  3. (v3) measured baseline - logical step is within -48.3 +- 20 MiB for B1 and 0 +- 20 MiB for B4.
Usage: python3 scripts/n1_verdict.py  -> assets/sweep/n1_verdict.json
"""
import json, statistics as st

MiB = 1 << 20
EXPECT = {'SmolLM2-1.7B/B1/c512': -48.3, 'SmolLM2-1.7B/B4/c512': 0.0}

def wl(q): return f"{q['model']}/B{q['batch']}/c{q['context']}"
def key(q): return (wl(q), q['window'], q['setaside'], q['hitratio'])

if __name__ == '__main__':
    P = {key(r['run']): r for r in json.load(open('assets/sweep/n1_predictions_ampere.json'))['runs']}
    M = {key(r['run']): r['counters']['dram_read_per_step'] / MiB
         for r in map(json.loads, open('assets/sweep/n1_measured_ampere.jsonl')) if 'counters' in r}
    out = dict(n=len(M), workloads={})
    preds = list(next(iter(P.values()))['dram_read_bytes'])
    rel = {f: [] for f in preds}
    for w in dict.fromkeys(k[0] for k in M):
        ks = [k for k in M if k[0] == w]
        p0 = P[ks[0]]; step = (p0['bytes']['weights'] + p0['bytes']['kv_read']) / MiB
        vals = [M[k] for k in ks]
        spread = max(vals) - min(vals)
        base = M.get((w, 0, 0, 0))
        d = dict(n=len(ks), step_mib=step, spread_mib=spread, spread_pct=100 * spread / step, s1=spread <= 0.03 * step,
                 baseline=base, baseline_minus_step=None if base is None else base - step,
                 best=min(ks, key=M.get), best_mib=min(vals), mae={})
        if base is not None:
            d['s3'] = abs((base - step) - EXPECT[w]) <= 20
        for f in preds:
            e = [abs(P[k]['dram_read_bytes'][f] / MiB - M[k]) for k in ks]
            d['mae'][f] = st.mean(e); rel[f] += [x / step for x in e]
        out['workloads'][w] = d
        print(f"{w}: step {step:.1f}, measured {min(vals):.1f}..{max(vals):.1f} (spread {spread:.1f} = {d['spread_pct']:.2f} %) "
              f"S1 {'PASS' if d['s1'] else 'FAIL'}; baseline - step {d['baseline_minus_step']:+.1f} (v3 {EXPECT[w]:+.1f} +- 20) "
              f"S3 {'PASS' if d.get('s3') else 'FAIL'}; best {d['best'][1:]} {d['best_mib']:.1f}")
        print('   MAE MiB: ' + ', '.join(f'{f} {v:.1f}' for f, v in sorted(d['mae'].items(), key=lambda x: x[1])))
    out['mae_pct'] = {f: 100 * st.mean(v) for f, v in rel.items() if v}
    out['s2'] = all(v <= 5 for v in out['mae_pct'].values())
    print(f"S2 {'PASS' if out['s2'] else 'FAIL'}: MAE % of step " +
          ', '.join(f'{f} {v:.2f}' for f, v in sorted(out['mae_pct'].items(), key=lambda x: x[1])))
    json.dump(out, open('assets/sweep/n1_verdict.json', 'w'), indent=1, default=list)
    print('wrote assets/sweep/n1_verdict.json')
