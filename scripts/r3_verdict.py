#!/usr/bin/env python3
"""R3 verdict: the four statements pre-registered at 2026-09-27 16:26 KST (WORKLOG), checked on the measured data.

  1. per workload, the baseline change (R3 measured - R2 measured, same workload) is within 10 MiB of v3's predicted
     change (v3 - v3_without_intervention);
  2. per workload, the set-aside contrast at window 127 MiB, r 0.4 (DRAM(S 12) - DRAM(S 60)) is within 10 MiB of v3's;
  3. over all measured R3 settings, v3 has the lowest MAE of the frozen predictors;
  4. v3 makes the most near-optimal best-hitRatio picks (prior_sim_compare's rule: within 2 % of the step).
Statements 3-4 come from prior_sim_compare.report('r3'), the same code that scores R2.
Usage: python3 scripts/r3_verdict.py  -> assets/sweep/r3_verdict.json
"""
import io, json, os, sys, contextlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'prior'))
import prior_sim_compare as PC

MiB = 1 << 20
TOL = 10.0

def wl(r): return f"{r['run']['model']}/B{r['run']['batch']}/c{r['run']['context']}"
def key(r): return (r['run']['window'], r['run']['setaside'], r['run']['hitratio'])

if __name__ == '__main__':
    P = {(wl(r), key(r)): r for r in json.load(open('assets/sweep/r3_predictions_ampere.json'))['runs']}
    R3 = {(wl(r), key(r)): r['counters']['dram_read_per_step'] / MiB
          for r in map(json.loads, open('assets/sweep/r3_measured_ampere.jsonl')) if 'counters' in r}
    R2 = {(wl(r), key(r)): r['counters']['dram_read_per_step'] / MiB
          for r in map(json.loads, open('assets/sweep/r2_measured_ampere.jsonl')) if 'counters' in r}
    v3 = lambda w, k: P[(w, k)]['dram_read_bytes']['v3'] / MiB
    v3o = lambda w, k: P[(w, k)]['v3_without_intervention'] / MiB
    works = [w for w in dict.fromkeys(x[0] for x in P) if any(x[0] == w for x in R3)]      # prediction-file order
    out = dict(workloads={}, tolerance_mib=TOL)
    B, A, Z = (0, 0, 0), (127, 12, 0.4), (127, 60, 0.4)
    for w in works:
        if sum(1 for x in R3 if x[0] == w) < sum(1 for x in P if x[0] == w): continue       # workload not complete
        dm, dp = R3[(w, B)] - R2[(w, B)], v3(w, B) - v3o(w, B)
        cm, cp = R3[(w, A)] - R3[(w, Z)], v3(w, A) - v3(w, Z)
        # the designer's decision: the lowest-DRAM setting of the grid, 'no policy' (the baseline) included
        best = min((k for x, k in R3 if x == w), key=lambda k: R3[(w, k)])
        pick = min((k for x, k in P if x == w), key=lambda k: v3(w, k))
        best2 = min((k for x, k in R2 if x == w), key=lambda k: R2[(w, k)])
        step = (P[(w, B)]['bytes']['weights'] + P[(w, B)]['bytes']['kv_read']) / MiB
        out['workloads'][w] = dict(
            s1=dict(measured_change=dm, predicted_change=dp, diff=dm - dp, pass_=abs(dm - dp) <= TOL,
                    baseline_r2=R2[(w, B)], baseline_r3=R3[(w, B)]),
            s2=dict(measured=cm, predicted=cp, before_r2=R2[(w, A)] - R2[(w, Z)], diff=cm - cp, pass_=abs(cm - cp) <= TOL),
            best=dict(r3_setting=best, r3_mib=R3[(w, best)], v3_pick=pick, v3_pick_measured=R3[(w, pick)],
                      v3_pick_excess_mib=R3[(w, pick)] - R3[(w, best)],
                      v3_pick_near_opt=R3[(w, pick)] - R3[(w, best)] <= 0.02 * step,
                      r2_setting=best2, r2_mib=R2[(w, best2)]))
        s1, s2, b = out['workloads'][w]['s1'], out['workloads'][w]['s2'], out['workloads'][w]['best']
        print(f"{w:<22} S1 {'PASS' if s1['pass_'] else 'FAIL'} (measured {dm:+.1f}, v3 {dp:+.1f}, diff {dm - dp:+.1f})   "
              f"S2 {'PASS' if s2['pass_'] else 'FAIL'} (before {s2['before_r2']:+.1f} -> measured {cm:+.1f}, v3 {cp:+.1f})   "
              f"best {best} {R3[(w, best)]:.1f}, v3 pick {pick} -> {R3[(w, pick)]:.1f} (+{R3[(w, pick)] - R3[(w, best)]:.1f}); "
              f"before (R2) {best2} {R2[(w, best2)]:.1f}")
    with contextlib.redirect_stdout(io.StringIO()):
        S = PC.report('r3')
    maes = {f: a['mae'] for f, a in S['abs'].items()}
    picks = {f: b['near_opt'] for f, b in S['best'].items()}
    out['s3'] = dict(mae_mib=maes, pass_=min(maes, key=maes.get) == 'v3', n=S['n'])
    out['s4'] = dict(near_opt=picks, groups=next(iter(S['best'].values()))['groups'] if S['best'] else 0,
                     pass_=max(picks.values()) == picks.get('v3') and
                           sum(v == picks.get('v3') for v in picks.values()) == 1)
    print(f"S3 {'PASS' if out['s3']['pass_'] else 'FAIL'}: MAE over {S['n']} settings " +
          ', '.join(f'{PC.label("r3", f)} {m:.2f}' for f, m in sorted(maes.items(), key=lambda x: x[1])))
    print(f"S4 {'PASS' if out['s4']['pass_'] else 'FAIL'}: near-optimal picks of {out['s4']['groups']} groups " +
          ', '.join(f'{PC.label("r3", f)} {n}' for f, n in sorted(picks.items(), key=lambda x: -x[1])))
    json.dump(out, open('assets/sweep/r3_verdict.json', 'w'), indent=1, default=list)
    print('wrote assets/sweep/r3_verdict.json')
