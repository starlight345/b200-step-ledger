#!/usr/bin/env python3
"""R1 analysis — frozen predictions of the prior-work tools and our models vs real-LLM decode on the GPU.

  1. DRAM read bytes per step: error of each predictor (absolute, and relative to the logical step bytes).
  2. Policy response: change from the workload's own baseline (no window). This removes any constant
     offset, so it asks only "does the predictor follow what the cache policy does to the traffic?".
  3. Best hitRatio per (workload, set-aside): the setting a designer would pick from each predictor.
  4. Control: set-aside with no window must equal the baseline.
  5. Time: GPU kernel time per step vs DRAM bytes inside one workload (kernels fixed, policy varies),
     and the tools' own latency predictions vs measured kernel time.
Writes assets/sweep/r1_summary_ampere.json for figures and documents.

Usage: python3 r1_compare.py assets/sweep/r1_predictions_ampere.json assets/sweep/r1_measured_ampere.jsonl
"""
import json, sys, statistics as st
from collections import defaultdict

MiB = 1 << 20
PRED = ('llmcompass', 'genz', 'memexplorer', 'gtsim_l2', 'ours_v1', 'ours_v2')

def key(run): return json.dumps(run, sort_keys=True)
def wl(run): return f"{run['model']}/B{run['batch']}"

def load(pp, mp):
    P = {key(r['run']): r for r in json.load(open(pp))['runs']}
    rows = []
    for l in open(mp):
        m = json.loads(l)
        p = P.get(key(m['run']))
        if p and 'counters' in m: rows.append((m['run'], p, m))
    return rows

def linfit(xs, ys):
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs); sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx else float('nan'); a = my - b * mx
    ss = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)); st_ = sum((y - my) ** 2 for y in ys)
    return a, b, 1 - ss / st_ if st_ else float('nan')

if __name__ == '__main__':
    rows = load(sys.argv[1], sys.argv[2])
    meas = lambda m: m['counters']['dram_read_per_step']
    logical = lambda p: p['bytes']['weights'] + p['bytes']['kv_read']
    S = dict(n=len(rows), predictors=PRED)
    print(f'{len(rows)} settings measured\n')

    # 1. absolute error
    print('=== 1. DRAM read bytes per step: prediction error ===')
    print(f"{'predictor':<13}{'MAE MiB':>9}{'bias MiB':>10}{'max MiB':>9}{'MAE %step':>11}{'within 2%':>11}{'within 5%':>11}")
    S['abs'] = {}
    for k in PRED:
        e = [p['dram_read_bytes'][k] - meas(m) for _, p, m in rows]
        rel = [abs(x) / logical(p) for x, (_, p, _) in zip(e, rows)]
        S['abs'][k] = dict(mae=st.mean(abs(x) for x in e) / MiB, bias=st.mean(e) / MiB, max=max(abs(x) for x in e) / MiB,
                           mae_pct=100 * st.mean(rel), within2=100 * sum(r < .02 for r in rel) / len(rel),
                           within5=100 * sum(r < .05 for r in rel) / len(rel))
        a = S['abs'][k]
        print(f"{k:<13}{a['mae']:>9.2f}{a['bias']:>10.2f}{a['max']:>9.2f}{a['mae_pct']:>10.2f}%{a['within2']:>10.0f}%{a['within5']:>10.0f}%")
    by = defaultdict(list)
    for t in rows: by[wl(t[0])].append(t)
    print('\n  per workload, MAE MiB (measured baseline | logical step):')
    print(f"  {'workload':<17}" + ''.join(f'{k[:11]:>12}' for k in PRED) + '    base / logical MiB')
    S['per_workload'] = {}
    for g, rs in by.items():
        base = [t for t in rs if t[0]['window'] == 0 and t[0]['setaside'] == 0][0]
        S['per_workload'][g] = dict(
            mae={k: st.mean(abs(p['dram_read_bytes'][k] - meas(m)) for _, p, m in rs) / MiB for k in PRED},
            baseline=meas(base[2]) / MiB, logical=logical(base[1]) / MiB,
            measured_range=(max(meas(m) for _, _, m in rs) - min(meas(m) for _, _, m in rs)) / MiB)
        w = S['per_workload'][g]
        print(f'  {g:<17}' + ''.join(f"{w['mae'][k]:>12.2f}" for k in PRED) + f"    {w['baseline']:.1f} / {w['logical']:.1f}")

    # 2. policy response relative to the workload's own baseline
    print('\n=== 2. Policy response: (setting - baseline), error of each predictor (MiB) ===')
    S['delta'] = {}
    for k in PRED:
        errs, pairs = [], []
        for g, rs in by.items():
            b = [t for t in rs if t[0]['window'] == 0 and t[0]['setaside'] == 0][0]
            for run, p, m in rs:
                if run['window'] == 0: continue
                dm = meas(m) - meas(b[2]); dp = p['dram_read_bytes'][k] - b[1]['dram_read_bytes'][k]
                errs.append(dp - dm); pairs.append((dp, dm))
        mx = st.mean(d for _, d in pairs); my = st.mean(d for d, _ in pairs)
        sxy = sum((dm - mx) * (dp - my) for dp, dm in pairs)
        sxx = sum((dm - mx) ** 2 for _, dm in pairs); syy = sum((dp - my) ** 2 for dp, _ in pairs)
        r = sxy / (sxx * syy) ** .5 if sxx and syy else 0.0
        S['delta'][k] = dict(mae=st.mean(abs(e) for e in errs) / MiB, r=r)
        print(f"  {k:<13} MAE {S['delta'][k]['mae']:6.2f} MiB   corr(pred, meas) {r:+.3f}")
    allm = [meas(m) - meas([t for t in by[wl(run)] if t[0]['window'] == 0 and t[0]['setaside'] == 0][0][2])
            for run, _, m in rows if run['window'] > 0]
    print(f'  measured policy effect: min {min(allm) / MiB:+.1f}, max {max(allm) / MiB:+.1f} MiB per step')
    S['measured_delta_range'] = [min(allm) / MiB, max(allm) / MiB]

    # 3. best hitRatio
    print('\n=== 3. Best hitRatio per (workload, set-aside), window 127 MiB ===')
    gs = defaultdict(list)
    for run, p, m in rows:
        if run['window'] == 127: gs[(wl(run), run['setaside'])].append((run, p, m))
    S['best'] = {k: 0 for k in PRED}; S['best_rows'] = []
    print(f"  {'workload':<17}{'S':>4}{'meas r':>8}{'DRAM':>8}" + ''.join(f'{k[:9]:>11}' for k in PRED))
    for (g, sa), rs in sorted(gs.items()):
        mb = min(rs, key=lambda t: meas(t[2]))
        line = f'  {g:<17}{sa:>4}{mb[0]["hitratio"]:>8.2f}{meas(mb[2]) / MiB:>8.1f}'
        row = dict(workload=g, setaside=sa, measured_best=mb[0]['hitratio'], measured_dram=meas(mb[2]) / MiB, pick={})
        for k in PRED:
            vals = [t[1]['dram_read_bytes'][k] for t in rs]
            if max(vals) - min(vals) < 1:                       # flat: the predictor cannot choose
                row['pick'][k] = None; line += f"{'flat':>11}"; continue
            pk = min(rs, key=lambda t: t[1]['dram_read_bytes'][k])
            loss = (meas(pk[2]) - meas(mb[2])) / MiB
            row['pick'][k] = dict(hitratio=pk[0]['hitratio'], loss=loss)
            S['best'][k] += loss <= 0.02 * logical(mb[1]) / MiB
            line += f"{pk[0]['hitratio']:>6.2f}({loss:+.0f})"
        S['best_rows'].append(row); print(line)
    print('  (x(+y): predictor picks hitRatio x, costing y MiB/step over the measured best)')
    print('  near-optimal picks (within 2% of step): ' + ', '.join(f'{k} {v}/{len(gs)}' for k, v in S['best'].items()))

    # 4. control
    print('\n=== 4. Control: set-aside 60 MiB, no window vs baseline ===')
    for g, rs in by.items():
        b = [t for t in rs if t[0]['window'] == 0 and t[0]['setaside'] == 0][0]
        c = [t for t in rs if t[0]['window'] == 0 and t[0]['setaside'] == 60][0]
        print(f'  {g:<17} baseline {meas(b[2]) / MiB:7.2f}  set-aside only {meas(c[2]) / MiB:7.2f} MiB')

    # 5. time
    if all('timing' in m for _, _, m in rows):
        print('\n=== 5. Time: GPU kernel time per step vs DRAM (policy varies, kernels fixed) ===')
        tb = json.load(open(sys.argv[1]))['tool_bytes']
        S['time'] = {}
        for g, rs in by.items():
            xs = [meas(m) / 1e9 for _, _, m in rs]; ks = [st.median(m['timing']['kernel_ms']) for _, _, m in rs]
            ws = [m['timing']['ms_median'] for _, _, m in rs]
            a, b, r2 = linfit(xs, ks)
            base = [t for t in rs if t[0]['window'] == 0 and t[0]['setaside'] == 0][0]
            kb = st.median(base[2]['timing']['kernel_ms'])
            S['time'][g] = dict(slope_ms_per_GB=b, r2=r2, kernel_ms_baseline=kb, wall_ms_baseline=base[2]['timing']['ms_median'],
                                kernel_ms_range=[min(ks), max(ks)], llmcompass_ms=tb['llmcompass_latency_ms'][g],
                                genz_ms=tb['genz_latency_ms'][g])
            print(f'  {g:<17} kernel {min(ks):.3f}~{max(ks):.3f} ms, slope {b:.3f} ms/GB (R2 {r2:.2f}); '
                  f'wall {base[2]["timing"]["ms_median"]:.2f} ms; LLMCompass {tb["llmcompass_latency_ms"][g]:.3f} ms, '
                  f'GenZ {tb["genz_latency_ms"][g]:.3f} ms')
    json.dump(S, open('assets/sweep/r1_summary_ampere.json', 'w'), indent=1)
    print('\nwrote assets/sweep/r1_summary_ampere.json')
