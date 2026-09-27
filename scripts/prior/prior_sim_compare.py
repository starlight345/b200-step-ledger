#!/usr/bin/env python3
"""Policy-aware prior simulators vs our model, on the held-out data (H1c synthetic, R1 and R2 real-LLM decode).

For each set, every setting measured with counters is joined with (a) the predictions frozen before that
measurement and (b) the prior simulators added afterwards (prior_sim_predictions.json: accelsim, autoscratch).
  1. DRAM read bytes per step: MAE, bias, share within 5 % of the step.
  2. Policy response: (setting - own-workload baseline), which removes any constant offset.
  3. Best hitRatio per (workload, set-aside): what a designer would pick from each predictor, and its cost.
A predictor enters a set only if it covers every setting of it. Accel-Sim could not afford R1's SmolLM-360M B1
(tracing hours + ~1 day of simulation), so R1 is also reported on the subset it covers ('r1_accelsim'), where
every predictor is scored on the same settings. R2 (workloads v3 had not seen), R3 (R2's batch > 1 workloads with the
weights read evict-first) and N1 (negative control, WS ~ 34x L2) have every predictor, v3 included, frozen in their
own predictions file before measuring, so they need no after-the-fact file; each is reported once its measurements exist.
Writes assets/sweep/prior_sim_summary.json.

Usage: python3 scripts/prior/prior_sim_compare.py
"""
import json, os, statistics as st
from collections import defaultdict

MiB = 1 << 20
SETS = {
    'h1c': ('assets/sweep/h1c_predictions_ampere.json', 'assets/sweep/h1c_measured_ampere.jsonl',
            ('no_residency', 'capacity_only', 'fixed_lru', 'cuda_policy', 'v2')),
    'r1': ('assets/sweep/r1_predictions_ampere.json', 'assets/sweep/r1_measured_ampere.jsonl',
           ('llmcompass', 'genz', 'memexplorer', 'gtsim_l2', 'ours_v1', 'ours_v2')),
    'r2': ('assets/sweep/r2_predictions_ampere.json', 'assets/sweep/r2_measured_ampere.jsonl',
           ('memexplorer', 'gtsim_l2', 'ours_v1', 'ours_v2', 'autoscratch', 'v3')),
    'r3': ('assets/sweep/r3_predictions_ampere.json', 'assets/sweep/r3_measured_ampere.jsonl',
           ('memexplorer', 'gtsim_l2', 'ours_v1', 'ours_v2', 'autoscratch', 'v3')),
    'n1': ('assets/sweep/n1_predictions_ampere.json', 'assets/sweep/n1_measured_ampere.jsonl',
           ('memexplorer', 'gtsim_l2', 'ours_v1', 'ours_v2', 'autoscratch', 'v3')),
}
NEW = ('accelsim', 'autoscratch', 'v3')
LABEL = {'no_residency': 'no residency (LLMCompass-like)', 'capacity_only': 'capacity only (MemExplorer-like)',
         'fixed_lru': 'GPU-Tile-Sim L2 (FA-LRU)', 'cuda_policy': 'ours v1', 'v2': 'ours v2',
         'llmcompass': 'LLMCompass', 'genz': 'GenZ', 'memexplorer': 'MemExplorer eq.4', 'gtsim_l2': 'GPU-Tile-Sim L2',
         'ours_v1': 'ours v1', 'ours_v2': 'ours v2', 'accelsim': 'Accel-Sim 2.0', 'autoscratch': 'AutoScratch semantics',
         'v3': 'ours v3 (R1: post hoc)'}

def key(run): return json.dumps(run, sort_keys=True)

def label(name, f): return 'ours v3 (prospective)' if name in ('r2', 'r3', 'n1') and f == 'v3' else LABEL[f]

def load(name, need=None):
    """Joined rows of a set; with need, only the settings that predictor covers."""
    pp, mp, frozen = SETS[name]
    P = {key(r['run']): r for r in json.load(open(pp))['runs']}
    N = {key(r['run']): r for r in json.load(open('assets/sweep/prior_sim_predictions.json'))['sets'].get(name, [])}
    rows = []
    for l in open(mp):
        m = json.loads(l)
        if 'counters' not in m: continue
        k = key(m['run']); p, n = P.get(k), N.get(k)
        if name in ('r2', 'r3', 'n1') and p:         # all frozen in one file; workload keyed with its context
            r = m['run']; n = dict(workload=f"{r['model']}/B{r['batch']}/c{r['context']}", dram_read_bytes={})
        if not p or not n: continue
        pred = {f: (p['dram_bytes'] if 'dram_bytes' in p else p['dram_read_bytes'])[f] for f in frozen}
        pred.update(n['dram_read_bytes'])
        step = p['step_bytes'] if 'step_bytes' in p else p['bytes']['weights'] + p['bytes']['kv_read']
        rows.append(dict(run=m['run'], wl=n['workload'], meas=m['counters']['dram_read_per_step'], step=step, pred=pred))
    if need: rows = [r for r in rows if need in r['pred']]
    preds = [f for f in dict.fromkeys(frozen + NEW) if all(f in r['pred'] for r in rows)]
    return rows, preds

def is_base(run): return run['window'] == 0 and run['setaside'] == 0

def report(name, need=None):
    rows, preds = load(name, need)
    S = dict(n=len(rows), predictors=preds, workloads=sorted({r['wl'] for r in rows}), abs={}, delta={}, best={})
    print(f'\n##### {name}{f" ({need} subset)" if need else ""}: {len(rows)} measured settings, workloads {S["workloads"]}')
    print(f"{'predictor':<34}{'MAE MiB':>9}{'bias':>9}{'MAE %':>8}{'<5 %':>7}   {'Δ-MAE':>7}{'corr':>7}")
    base = {r['wl']: r for r in rows if is_base(r['run'])}
    for f in preds:
        e = [r['pred'][f] - r['meas'] for r in rows]
        rel = [abs(x) / r['step'] for x, r in zip(e, rows)]
        a = dict(mae=st.mean(abs(x) for x in e) / MiB, bias=st.mean(e) / MiB, mae_pct=100 * st.mean(rel),
                 within5=100 * sum(x < .05 for x in rel) / len(rel))
        pairs = [(r['pred'][f] - base[r['wl']]['pred'][f], r['meas'] - base[r['wl']]['meas'])
                 for r in rows if not is_base(r['run']) and r['wl'] in base]
        d = dict(mae=st.mean(abs(p - m) for p, m in pairs) / MiB)
        mp, mm = st.mean(p for p, _ in pairs), st.mean(m for _, m in pairs)
        sxy = sum((p - mp) * (m - mm) for p, m in pairs); sxx = sum((p - mp) ** 2 for p, _ in pairs)
        syy = sum((m - mm) ** 2 for _, m in pairs)
        d['corr'] = sxy / (sxx * syy) ** .5 if sxx and syy else 0.0
        S['abs'][f], S['delta'][f] = a, d
        print(f"{label(name, f):<34}{a['mae']:>9.2f}{a['bias']:>+9.2f}{a['mae_pct']:>7.1f}%{a['within5']:>6.0f}%   "
              f"{d['mae']:>7.2f}{d['corr']:>+7.3f}")
    # best hitRatio per (workload, set-aside, window) group with >= 3 hitRatio values
    gs = defaultdict(list)
    for r in rows:
        if r['run']['window'] > 0: gs[(r['wl'], r['run']['setaside'], r['run']['window'])].append(r)
    gs = {k: v for k, v in gs.items() if len({r['run']['hitratio'] for r in v}) >= 3}
    for f in preds:
        ok, lost = 0, []
        for (wl, sa, w), rs in gs.items():
            mb = min(rs, key=lambda r: r['meas'])
            vals = [r['pred'][f] for r in rs]
            if max(vals) - min(vals) < 1:                                # flat: sees no benefit, keeps the baseline
                pick, near = base[wl], False                             # (never counted near-optimal, as r1_compare)
            else:
                pick = min(rs, key=lambda r: r['pred'][f]); near = None
            loss = pick['meas'] - mb['meas']; lost.append(loss / MiB)
            ok += (loss <= 0.02 * mb['step']) if near is None else near
        S['best'][f] = dict(groups=len(gs), near_opt=ok, mean_loss_mib=st.mean(lost) if lost else 0.0)
    print(f"  best-hitRatio groups: {len(gs)};  near-optimal picks (within 2 % of step) / mean extra MiB per step"
          " (a predictor that sees no policy effect keeps the baseline):")
    print('  ' + ', '.join(f"{label(name, f)} {S['best'][f]['near_opt']} / {S['best'][f]['mean_loss_mib']:.1f}" for f in preds))
    return S

if __name__ == '__main__':
    out = {name: report(name) for name in SETS if os.path.exists(SETS[name][1])}
    out['r1_accelsim'] = report('r1', need='accelsim')
    json.dump(out, open('assets/sweep/prior_sim_summary.json', 'w'), indent=1)
    print('\nwrote assets/sweep/prior_sim_summary.json')
