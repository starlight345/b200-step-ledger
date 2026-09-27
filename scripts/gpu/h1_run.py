#!/usr/bin/env python3
"""H1 runner — measure exactly the grid frozen in h1_predictions_<host>.json, on the GPU it names.

Per setting, two passes of the same binary and arguments:
  T  timing, no profiler: l2policy_bench, 30 warm-up steps, 200 timed steps.
  D  counters: ncu over 3 steady-state steps only (--launch-skip past the warm-up), with
     --cache-control none so the profiler does NOT flush L2 between kernels (the default would erase
     exactly the cross-step residency being measured) and --replay-mode application so no kernel is
     replayed against a disturbed cache.
Collected: dram__bytes_read/write and L2 lookup hit/miss sectors (hit rate weighted by sectors).
Resumable: settings already in the output file are skipped.

Usage (on the GPU host):  python3 h1_run.py h1_predictions_ampere.json h1_measured_ampere.jsonl
"""
import csv, io, json, os, subprocess, sys, time

BENCH = os.path.abspath(os.environ.get('L2BENCH', './l2policy_bench'))   # C3 uses the hint build
METRICS = ('dram__bytes_read.sum,dram__bytes_write.sum,'
           'lts__t_sectors_lookup_hit.sum,lts__t_sectors_lookup_miss.sum')
WARM, ITERS, PROF = 30, 200, 3

def bench_args(run):
    a = [f"mode={run['mode']}", f"setaside={run['setaside']}", f"window={run['window']}", f"hitratio={run['hitratio']}"]
    if run['mode'] == 'llm': a += [f"ws={run['ws']}", f"layers={run['layers']}"]
    else: a += [f"hot={run['hot']}", f"chunk={run['chunk']}", f"pool={run['pool']}"]
    if run.get('hint'): a.append(f"hint={run['hint']}")
    return a

def key(run): return json.dumps(run, sort_keys=True)

def timing(run):
    p = subprocess.run([BENCH, *bench_args(run), f'warmup={WARM}', f'iters={ITERS}'],
                       capture_output=True, text=True, timeout=600)
    return json.loads(p.stdout.strip().splitlines()[-1])

def counters(run):
    k = run['layers'] if run['mode'] == 'llm' else 2
    cmd = ['ncu', '--metrics', METRICS, '--cache-control', 'none', '--replay-mode', 'application',
           '--csv', '--print-units', 'base', '--launch-skip', str(WARM * k), '--launch-count', str(PROF * k),
           BENCH, *bench_args(run), f'warmup={WARM}', f'iters={PROF}']
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    rows = [l for l in p.stdout.splitlines() if l.startswith('"')]
    tot = {m: 0.0 for m in METRICS.split(',')}; kernels = set()
    for r in csv.DictReader(io.StringIO('\n'.join(rows))):
        name = r.get('Metric Name'); val = r.get('Metric Value', '').replace(',', '')
        if name in tot and val:
            tot[name] += float(val); kernels.add(r.get('ID'))
    if not kernels:
        raise RuntimeError('ncu returned no rows:\n' + (p.stdout + p.stderr)[-1500:])
    hit, miss = tot['lts__t_sectors_lookup_hit.sum'], tot['lts__t_sectors_lookup_miss.sum']
    return dict(kernels_profiled=len(kernels), steps_profiled=PROF,
                dram_read_per_step=tot['dram__bytes_read.sum'] / PROF,
                dram_write_per_step=tot['dram__bytes_write.sum'] / PROF,
                l2_hit_rate=hit / (hit + miss) if hit + miss else None)

if __name__ == '__main__':
    pred, outp = sys.argv[1], sys.argv[2]
    runs = [r['run'] for r in json.load(open(pred))['runs']]
    done = set()
    if os.path.exists(outp):
        for l in open(outp):
            try: done.add(key(json.loads(l)['run']))
            except Exception: pass
    t0 = time.time()
    with open(outp, 'a') as f:
        for i, run in enumerate(runs):
            if key(run) in done: continue
            rec = dict(run=run, t=time.strftime('%H:%M:%S'))
            try: rec['timing'] = timing(run)
            except Exception as e: rec['timing_error'] = str(e)[-500:]
            try: rec['counters'] = counters(run)
            except Exception as e: rec['counters_error'] = str(e)[-800:]
            f.write(json.dumps(rec) + '\n'); f.flush()
            print(f'[{i + 1}/{len(runs)}] {time.time() - t0:7.0f}s  {run}', flush=True)
    print('done', flush=True)
