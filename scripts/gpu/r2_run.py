#!/usr/bin/env python3
"""R2 runner — real-LLM decode on workloads v3 has not seen, the grid frozen in r2_predictions.

Same method as r1_run.py (which it imports): per workload (model, batch, context) one model load per pass,
  D  counters: ncu --replay-mode app-range --cache-control none, one profiler range per setting,
     20 warm-up decode steps before each range and 3 inside it;
  T  timing without ncu: CUDA-event wall time and torch.profiler kernel time per step.
The only difference is that the context comes from each run (R1 fixed it at 512). Resumable per workload.

Usage (on the GPU host, venv active, HF_HOME set):
  python r2_run.py r2_predictions_ampere.json r2_measured_ampere.jsonl
"""
import json, os, sys, time
from collections import defaultdict
import r1_run as R1

def bench(model, batch, mode, settings_path, context):
    return [sys.executable, 'llm_policy_bench.py', '--model', R1.HF_ID[model], '--batch', str(batch),
            '--context', str(context), '--mode', mode, '--settings', settings_path,
            '--warmup', str(R1.WARM), '--iters', str(R1.ITERS), '--prof', str(R1.PROF)]

if __name__ == '__main__':
    pred, outp = sys.argv[1], sys.argv[2]
    runs = [r['run'] for r in json.load(open(pred))['runs']]
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
        # r1_run's counters()/timing() build their command with the module-level bench(); point it at this workload
        R1.bench = lambda m, b, mode, sp, _c=context: bench(m, b, mode, sp, _c)
        sp = os.path.abspath(f'r2_settings_{model}_B{batch}_c{context}.json')
        json.dump([dict(window=r['window'], setaside=r['setaside'], hitratio=r['hitratio']) for r in rs], open(sp, 'w'))
        tag = f'{model} B{batch} c{context}'
        print(f'{time.time() - t0:7.0f}s  {tag}: counters ({len(rs)} ranges)', flush=True)
        C = R1.counters(model, batch, sp, len(rs))
        print(f'{time.time() - t0:7.0f}s  {tag}: timing', flush=True)
        T = R1.timing(model, batch, sp, len(rs))
        with open(outp, 'a') as f:
            for r, c, t in zip(rs, C, T):
                f.write(json.dumps(dict(run=r, counters=c, timing=t, t=time.strftime('%H:%M:%S'))) + '\n')
        print(f'{time.time() - t0:7.0f}s  {tag}: done', flush=True)
    print('done', flush=True)
