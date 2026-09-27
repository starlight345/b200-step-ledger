#!/usr/bin/env python3
"""Collect every finished Accel-Sim run (asim_all.sh) into one JSONL, one line per workload.

Kernels per step: 32 for the synthetic llm workload (layers), 2 for clean (hot + chunk), and for R1 the traced
kernel count / 2 (two decode steps inside the profiler range). Every run traces two steps: the first is warm-up,
the second is the prediction (LRU-type caches reach steady state after one pass of a cyclic stream).
Run on dsil-sy:  python3 asim_collect.py > accelsim_runs.jsonl
"""
import glob, json, os, subprocess, sys

R = os.path.expanduser('~/l2probe/asim/runs')
HERE = os.path.dirname(os.path.abspath(__file__))

def name_to_workload(n):
    p = n.split('_')
    if p[0] == 'llm': return f'llm {p[1]}', 32, 1
    if p[0] == 'clean': return f'clean {p[1]} {p[2]} 2048', 2, 1
    return f"{p[1]}/{p[2]}", None, 1                               # r1_SmolLM-135M_B1 -> SmolLM-135M/B1

for d in sorted(glob.glob(os.path.join(R, '*'))):
    log = os.path.join(d, 'sim', 'sim.log')
    if not os.path.isdir(d) or not os.path.exists(os.path.join(d, 'sim', 'sim_meta.json')): continue
    n = os.path.basename(d); w, kps, warm = name_to_workload(n)
    tm = json.load(open(os.path.join(d, 'trace_meta.json')))
    # kernels = entries of kernelslist.g (trace_meta counts raw and processed files together)
    tm['kernels'] = sum(1 for l in open(os.path.join(d, 'traces', 'kernelslist.g')) if l.startswith('kernel-'))
    if kps is None:
        if tm['kernels'] % 2: print(f'# {n}: {tm["kernels"]} kernels not divisible by 2', file=sys.stderr); continue
        kps = tm['kernels'] // 2
    p = subprocess.run([sys.executable, os.path.join(HERE, 'asim_parse.py'), log, str(kps), str(warm)],
                       capture_output=True, text=True)
    if p.returncode: print(f'# {n}: parse failed {p.stderr[-300:]}', file=sys.stderr); continue
    r = json.loads(p.stdout)
    r.update(workload=w, run=n, trace=tm, sim=json.load(open(os.path.join(d, 'sim', 'sim_meta.json'))),
             config_sha256=open(os.path.join(d, 'sim', 'config.sha256')).read().split())
    tail = open(log, errors='replace').read()[-3000:]
    r['completed'] = 'GPGPU-Sim: *** exit detected ***' in tail or 'simulation time' in tail.lower()
    print(json.dumps(r))
