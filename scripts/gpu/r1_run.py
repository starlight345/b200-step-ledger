#!/usr/bin/env python3
"""R1 runner — real LLM decode (llm_policy_bench.py, manual engine), the grid frozen in r1_predictions.

Per workload (model, batch) one model load per pass, one policy setting after another:
  D  counters: ncu --replay-mode app-range, one cudaProfilerStart/Stop range per setting (range i =
     setting i), 20 warm-up decode steps before each range, 3 steps inside it, --cache-control none
     so nothing is flushed between kernels. dram__bytes_read/write and L2 lookup hit/miss sectors.
  T  timing, no ncu: per setting 60 steps of CUDA-event wall time and 3 x 3 steps of GPU kernel time
     (sum of kernel durations via torch.profiler; eager decode is launch-bound on the CPU).
Resumable per workload and pass: a workload whose records are complete is skipped.

Usage (on the GPU host, venv active, HF_HOME set):
  python r1_run.py r1_predictions_ampere.json r1_measured_ampere.jsonl
"""
import csv, io, json, os, subprocess, sys, time
from collections import defaultdict

METRICS = ('dram__bytes_read.sum,dram__bytes_write.sum,'
           'lts__t_sectors_lookup_hit.sum,lts__t_sectors_lookup_miss.sum')
WARM, ITERS, PROF = 20, 60, 3
NCU = '/usr/local/cuda-12.8/bin/ncu'
HF_ID = {'SmolLM-135M': 'HuggingFaceTB/SmolLM-135M', 'SmolLM-360M': 'HuggingFaceTB/SmolLM-360M'}

def bench(model, batch, mode, settings_path):
    return [sys.executable, 'llm_policy_bench.py', '--model', HF_ID[model], '--batch', str(batch),
            '--context', '512', '--mode', mode, '--settings', settings_path,
            '--warmup', str(WARM), '--iters', str(ITERS), '--prof', str(PROF)]

def settings_lines(text):
    out = {}
    for l in text.splitlines():
        if l.startswith('SETTING '):
            r = json.loads(l[8:]); out[r['i']] = r
    return out

def counters(model, batch, settings_path, n):
    cmd = [NCU, '--metrics', METRICS, '--cache-control', 'none', '--replay-mode', 'app-range',
           '--csv', '--print-units', 'base', *bench(model, batch, 'sweep-profile', settings_path)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    rows = [l for l in p.stdout.splitlines() if l.startswith('"')]
    tot = defaultdict(lambda: defaultdict(float))
    for r in csv.DictReader(io.StringIO('\n'.join(rows))):
        name = r.get('Metric Name'); val = (r.get('Metric Value') or '').replace(',', '')
        if name in METRICS.split(',') and val:
            tot[int(r['ID'])][name] += float(val)
    ids = sorted(tot)
    if len(ids) != n:
        raise RuntimeError(f'ncu returned {len(ids)} ranges for {n} settings:\n' + (p.stdout + p.stderr)[-2500:])
    info = settings_lines(p.stdout)
    res = []
    for i, rid in enumerate(ids):
        t = tot[rid]; hit, miss = t['lts__t_sectors_lookup_hit.sum'], t['lts__t_sectors_lookup_miss.sum']
        res.append(dict(range_id=rid, steps_profiled=PROF, policy_rc=info.get(i, {}).get('policy_rc'),
                        setaside_got=info.get(i, {}).get('setaside_got'),
                        dram_read_per_step=t['dram__bytes_read.sum'] / PROF,
                        dram_write_per_step=t['dram__bytes_write.sum'] / PROF,
                        l2_hit_rate=hit / (hit + miss) if hit + miss else None))
    return res

def timing(model, batch, settings_path, n):
    p = subprocess.run(bench(model, batch, 'sweep-time', settings_path), capture_output=True, text=True, timeout=7200)
    info = settings_lines(p.stdout)
    if len(info) != n:
        raise RuntimeError(f'timing returned {len(info)} settings for {n}:\n' + (p.stdout + p.stderr)[-2500:])
    return [dict(ms_median=info[i]['ms_median'], kernel_ms=info[i]['kernel_ms'], policy_rc=info[i]['policy_rc'])
            for i in range(n)]

if __name__ == '__main__':
    pred, outp = sys.argv[1], sys.argv[2]
    runs = [r['run'] for r in json.load(open(pred))['runs']]
    work = defaultdict(list)
    for r in runs: work[(r['model'], r['batch'])].append(r)
    done = set()
    if os.path.exists(outp):
        for l in open(outp):
            try:
                m = json.loads(l)
                if 'counters' in m and 'timing' in m: done.add((m['run']['model'], m['run']['batch']))
            except Exception: pass
    t0 = time.time()
    for (model, batch), rs in work.items():
        if (model, batch) in done: continue
        sp = os.path.abspath(f'r1_settings_{model}_B{batch}.json')
        json.dump([dict(window=r['window'], setaside=r['setaside'], hitratio=r['hitratio']) for r in rs], open(sp, 'w'))
        print(f'{time.time() - t0:7.0f}s  {model} B{batch}: counters ({len(rs)} ranges)', flush=True)
        C = counters(model, batch, sp, len(rs))
        print(f'{time.time() - t0:7.0f}s  {model} B{batch}: timing', flush=True)
        T = timing(model, batch, sp, len(rs))
        with open(outp, 'a') as f:
            for r, c, t in zip(rs, C, T):
                f.write(json.dumps(dict(run=r, counters=c, timing=t, t=time.strftime('%H:%M:%S'))) + '\n')
        print(f'{time.time() - t0:7.0f}s  {model} B{batch}: done', flush=True)
    print('done', flush=True)
