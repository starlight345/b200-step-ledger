#!/usr/bin/env python3
"""N1 — negative control, predictions written BEFORE measuring: a model whose decode working set is ~34x the L2.

Why: every other real-LLM workload (R1-R3) keeps the reused working set within 3-9x of the 96 MiB L2, where the
persistence controls move the DRAM traffic by up to ~20 %. The paper must also show where they do not matter, so
that "why small models?" is answered by the data: SmolLM2-1.7B (3.2 GiB of bf16 weights), batch 1 and 4, context
512. Load classes come from the model's own SASS census (r2_list.sh -> r2_fetch.sh -> classes.json), as for R2.
Grid (9 settings per workload): baseline; set-aside 60 MiB only; window 127 MiB x S {12, 60} x r {0.2, 0.4, 1.0};
the documented recipe window = S = 60, r 1. Predictors as R2: v3, v2, v1, GPU-Tile-Sim L2, AutoScratch semantics,
MemExplorer eq. (4) — frozen code (r2_predict.predict).

Usage: python3 scripts/n1_predict.py   -> assets/sweep/n1_predictions_ampere.json
"""
import hashlib, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import r2_predict as R2

MiB = 1 << 20
WORKLOADS = ('SmolLM2-1.7B/B1/c512', 'SmolLM2-1.7B/B4/c512')
GRID = [(0, 0, 0.0), (0, 60, 0.0)] + [(127, s, r) for s in (12, 60) for r in (0.2, 0.4, 1.0)] + [(60, 60, 1.0)]

def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()

if __name__ == '__main__':
    probe = json.load(open('assets/sweep/gpu_probe_ampere.json'))
    C = int(probe['gpu.l2_cache_bytes'])
    phi = json.load(open('assets/sweep/v2_fit_ampere.json'))['phi']
    runs, classes = [], {}
    for w in WORKLOADS:
        model, B, ctx = w.split('/'); batch, context = int(B[1:]), int(ctx[1:])
        c = json.load(open(f'assets/sweep/r2_census/r2_{model}_B{batch}_c{context}/classes.json'))
        if c['unmatched']: sys.exit(f'{w}: operands without a matching kernel {c["unmatched"]}')
        cls = {op: v['class'] for op, v in c['operands'].items()}
        classes[w] = cls
        for win, sa, hr in GRID:
            runs.append(R2.predict(dict(model=model, batch=batch, context=context, window=win, setaside=sa, hitratio=hr),
                                   C, phi, cls))
    doc = dict(created=time.strftime('%Y-%m-%d %H:%M:%S %Z'), machine=probe['host'], l2_bytes=C, phi=phi,
               model_sha256={f: sha(f)[:16] for f in ('scripts/l2policy_model_v3.py', 'scripts/r2_predict.py',
                                                      'scripts/n1_predict.py')},
               load_classes=classes, note='N1 negative control (WS ~ 34x L2). All predictors frozen before measuring.',
               runs=runs)
    json.dump(doc, open('assets/sweep/n1_predictions_ampere.json', 'w'), indent=1)
    for w in WORKLOADS:
        rs = [r for r in runs if f"{r['run']['model']}/B{r['run']['batch']}/c{r['run']['context']}" == w]
        step = (rs[0]['bytes']['weights'] + rs[0]['bytes']['kv_read']) / MiB
        spread = {k: (max(r['dram_read_bytes'][k] for r in rs) - min(r['dram_read_bytes'][k] for r in rs)) / MiB
                  for k in rs[0]['dram_read_bytes']}
        print(f"{w}: step {step:.0f} MiB (WS/L2 {step * MiB / C:.1f}), classes {''.join(classes[w][k] for k in ('q', 'down', 'lm_head', 'K'))}; "
              f"baseline " + ', '.join(f"{k} {rs[0]['dram_read_bytes'][k] / MiB:.0f}" for k in ('v3', 'ours_v2', 'gtsim_l2', 'memexplorer')) +
              f"; predicted policy spread (max - min over settings) " + ', '.join(f'{k} {v:.1f}' for k, v in spread.items()))
