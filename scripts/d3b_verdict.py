#!/usr/bin/env python3
"""D3b verdict: the statements pre-registered at 2026-09-27 18:40 KST (WORKLOG), checked on the measured data.

  1. controls: hint 0 (plain LDG) at (127, 60, 0.4) within 238.6 +- 8 MiB (D2); hint 3 (ld.global.cs) at (127, 12, 0.4) and
     (127, 60, 0.4) within 212.8 / 212.7 +- 8 (D3). Otherwise the session is void.
  2. hints 4, 5, 7 (kernel-built descriptor, normal / unchanged priority): the mean saving against the hint's own baseline over
     (127, 60, 0.3), (127, 60, 0.4), (127, 36, 0.4) is < 10 MiB -> v3_desc (window only through the default descriptor),
     > 20 MiB -> v3 (priority only), otherwise inconclusive.
     Amended before measuring (WORKLOG 19:19): the primary rule is relative to the same-session plain control, because the
     plain loads' own mean saving over these settings is itself near 20 MiB: ratio = mean saving(h) / mean saving(hint 0);
     < 0.3 -> v3_desc, > 0.7 -> v3, otherwise inconclusive. The absolute rule above is reported as secondary.
  3. hint 6 (bulk copy without a descriptor): the same rules, exploratory.
  4. each hint's baseline within 268 MiB +- 5 % (the bulk kernel reads every byte); otherwise that hint is not judged.
Also: MAE of every frozen predictor over all measured settings and over hints 4-7.
Usage: python3 scripts/d3b_verdict.py  -> assets/sweep/d3b_verdict.json
"""
import json, statistics as st

MiB = 1 << 20
DISC = ((127, 60, 0.3), (127, 60, 0.4), (127, 36, 0.4))

def key(q): return (q['hint'], q['window'], q['setaside'], q['hitratio'])

if __name__ == '__main__':
    P = {key(r['run']): r['dram_bytes'] for r in json.load(open('assets/sweep/d3b_predictions_ampere.json'))['runs']}
    M = {key(r['run']): r['counters']['dram_read_per_step'] / MiB
         for r in map(json.loads, open('assets/sweep/d3b_measured_ampere.jsonl')) if 'counters' in r}
    out = dict(n=len(M), statements={}, hints={})
    g = lambda h, s: M.get((h,) + s)
    c = dict(h0=g(0, (127, 60, 0.4)), h3_s12=g(3, (127, 12, 0.4)), h3_s60=g(3, (127, 60, 0.4)))
    ok1 = all(v is not None for v in c.values()) and abs(c['h0'] - 238.6) <= 8 and abs(c['h3_s12'] - 212.8) <= 8 \
        and abs(c['h3_s60'] - 212.7) <= 8
    out['statements']['s1_controls'] = dict(values=c, pass_=ok1)
    print(f"S1 controls {'PASS' if ok1 else 'FAIL'}: hint 0 S60 r.4 {c['h0']}, hint 3 S12/S60 r.4 {c['h3_s12']} / {c['h3_s60']}")
    for h in (0, 3, 4, 5, 6, 7):
        base = g(h, (0, 0, 0))
        if base is None: continue
        sane = abs(base - 268.0) <= 0.05 * 268.0
        sav = [base - g(h, s) for s in DISC if g(h, s) is not None]
        mean = st.mean(sav) if sav else None
        verdict = None if not sane or mean is None else 'v3_desc' if mean < 10 else 'v3' if mean > 20 else 'inconclusive'
        ref = out['hints'].get(0, {}).get('mean_saving')
        ratio = mean / ref if (mean is not None and ref) else None
        rel = None if not sane or ratio is None else 'v3_desc' if ratio < 0.3 else 'v3' if ratio > 0.7 else 'inconclusive'
        out['hints'][h] = dict(baseline=base, baseline_ok=sane, savings=sav, mean_saving=mean, verdict_abs=verdict,
                               ratio_to_plain=ratio, verdict=rel if h != 0 else None,
                               measured={f'{s}': g(h, s) for s in [(0, 0, 0)] + [(127, a, r) for a in (12, 60) for r in (0.4, 1.0)] + list(DISC)})
        print(f"hint {h}: baseline {base:.1f} ({'ok' if sane else 'OUT OF RANGE'}), savings at {DISC}: "
              + ', '.join(f'{x:+.1f}' for x in sav) + f"  mean {mean:+.1f}"
              + (f"  ratio to plain {ratio:.2f} -> {rel} (absolute rule: {verdict})" if h != 0 and ratio is not None else ''))
    out['statements']['s2_built_normal'] = {h: out['hints'].get(h, {}).get('verdict') for h in (4, 5, 7)}
    out['statements']['s3_bulk_no_desc'] = out['hints'].get(6, {}).get('verdict')
    out['statements']['s4_baselines'] = {h: d['baseline_ok'] for h, d in out['hints'].items()}
    maes = {}
    for sel, name in ((lambda k: True, 'all'), (lambda k: k[0] >= 4, 'hints_4_7')):
        ks = [k for k in M if k in P and sel(k)]
        maes[name] = {f: st.mean(abs(P[k][f] / MiB - M[k]) for k in ks) for f in P[ks[0]]} if ks else {}
        print(f'MAE ({name}, {len(ks)} settings): ' + ', '.join(f'{f} {v:.2f}' for f, v in sorted(maes[name].items(), key=lambda x: x[1])))
    out['mae_mib'] = maes
    json.dump(out, open('assets/sweep/d3b_verdict.json', 'w'), indent=1, default=str)
    print('wrote assets/sweep/d3b_verdict.json')
