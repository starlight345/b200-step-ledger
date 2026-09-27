#!/usr/bin/env python3
"""R3 runner — the R2 batch > 1 workloads again with the intervention (llm_policy_bench.py --weights-cs: decode
projections read their weights with ld.global.cs, see cs_linear.py), over the grid frozen in r3_predictions.

Identical to r2_run.py (same counters / timing passes, same 20 warm-up + 3 profiled steps) except for the flag.
Kernel time in the timing pass is NOT comparable with R2 (the projections run as Triton kernels instead of CUTLASS);
the DRAM counters are the measurement under test. Resumable per workload.

Usage (on the GPU host, venv active, HF_HOME set):
  python r3_run.py r3_predictions_ampere.json r3_measured_ampere.jsonl
"""
import json, os, sys, time
from collections import defaultdict
import r1_run as R1
import r2_run as R2

def bench(model, batch, mode, settings_path, context):
    return R2.bench(model, batch, mode, settings_path, context) + ['--weights-cs']

if __name__ == '__main__':
    pred, outp = sys.argv[1], sys.argv[2]
    runs = [r['run'] for r in json.load(open(pred))['runs']]
    assert all(r.get('weights_cs') for r in runs)
    work = defaultdict(list)
    for r in runs: work[(r['model'], r['batch'], r['context'])].append(r)
    done = set()
    if os.path.exists(outp):
        for l in open(outp):
            try:
                m = json.loads(l)
                if 'counters' in m and 'timing' in m: done.add((m['run']['model'], m['run']['batch'], m['run']['context']))
            except Exception: pass
    t0 = time.time()
    for (model, batch, context), rs in work.items():
        if (model, batch, context) in done: continue
        R1.bench = lambda m, b, mode, sp, _c=context: bench(m, b, mode, sp, _c)
        sp = os.path.abspath(f'r3_settings_{model}_B{batch}_c{context}.json')
        json.dump([dict(window=r['window'], setaside=r['setaside'], hitratio=r['hitratio']) for r in rs], open(sp, 'w'))
        tag = f'{model} B{batch} c{context} (weights .cs)'
        print(f'{time.time() - t0:7.0f}s  {tag}: counters ({len(rs)} ranges)', flush=True)
        C = R1.counters(model, batch, sp, len(rs))
        print(f'{time.time() - t0:7.0f}s  {tag}: timing', flush=True)
        T = R1.timing(model, batch, sp, len(rs))
        with open(outp, 'a') as f:
            for r, c, t in zip(rs, C, T):
                f.write(json.dumps(dict(run=r, counters=c, timing=t, t=time.strftime('%H:%M:%S'))) + '\n')
        print(f'{time.time() - t0:7.0f}s  {tag}: done', flush=True)
    print('done', flush=True)
