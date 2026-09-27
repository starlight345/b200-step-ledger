#!/usr/bin/env python3
"""Predictions of the policy-aware prior simulators, on every setting we have measured (H1, H1b, H1c, R1).

Added AFTER those measurements, so none of these may be tuned: each is the prior tool (or the prior paper's
stated semantics) with the device's hardware values and nothing else.
  accelsim     Accel-Sim 2.0 / GPGPU-Sim 4.x, trace-driven, SM120_RTXPRO5000 config (scripts/prior/asim_run.sh).
               It cannot express set-aside or an access-policy window, so each workload is simulated once at the
               baseline and that value is its prediction for every setting of the workload.
  autoscratch  AutoScratch's residency semantics (MLSys'23; code not public): selected lines pinned up to the
               set-aside, the rest LRU, no hitRatio/streaming distinction (scripts/prior/autoscratch_pin.py).
  v3           our model v3 (l2policy_model_v3.py: v2 + evict-first instruction class). Synthetic sets use plain
               loads, where v3 = v2 exactly. On R1 it is POST HOC (the rule came from R1 and C3): the weight-load
               class is read from each workload's SASS — B1 decode = cuBLAS gemvx with LDG.E.EF (evict-first),
               B8 decode = CUTLASS wmma GEMM with LDG.E.LTC128B / LD.E (normal); KV reads normal.
Workloads map onto the same cyclic streams our models use (l2policy_model.workload; R1 as llm_predict.predict).

Usage: python3 scripts/prior/prior_sim_predict.py   -> assets/sweep/prior_sim_predictions.json
"""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
import autoscratch_pin as AS
import llm_predict as LP
import l2policy_model_v3 as V3

MiB = 1 << 20
SETS = {'h1': 'assets/sweep/h1_predictions_ampere.json', 'h1b': 'assets/sweep/h1b_predictions_ampere.json',
        'h1c': 'assets/sweep/h1c_predictions_ampere.json', 'r1': 'assets/sweep/r1_predictions_ampere.json'}
ASIM = 'assets/sweep/accelsim_runs.jsonl'

def wl_synth(run):
    return f"llm {run['ws']:g}" if run['mode'] == 'llm' else f"clean {run['hot']:g} {run['chunk']:g} {run['pool']:g}"

def wl_r1(run): return f"{run['model']}/B{run['batch']}"

# weight-load class from the traced SASS of each R1 workload (asim_opcodes.py census / kernel listing)
R1_WEIGHTS_EVICT_FIRST = {('SmolLM-135M', 1): True, ('SmolLM-135M', 8): False, ('SmolLM-360M', 1): True}

def r1_v3_classes(run):
    cfg = json.load(open(os.path.join(LP.HF, run['model'] + '.json')))
    b = LP.step_bytes(cfg, run['batch'], run['context'])
    W = min(run['window'] * MiB, b['weights']); rest = (b['weights'] - W) / MiB; kv = b['kv_read'] / MiB
    if R1_WEIGHTS_EVICT_FIRST[(run['model'], run['batch'])]: return dict(W=W / MiB, E=rest, N=kv, F=0.0)
    return dict(W=W / MiB, E=0.0, N=rest + kv, F=0.0)

def r1_stream(run):
    """R1 decode step as the cyclic stream llm_predict gives our models: weights (window = first W bytes) + KV."""
    cfg = json.load(open(os.path.join(LP.HF, run['model'] + '.json')))
    b = LP.step_bytes(cfg, run['batch'], run['context'])
    W = min(run['window'] * MiB, b['weights'])
    return dict(mode='llm', ws=(b['weights'] + b['kv_read']) / MiB, layers=1, window=W / MiB,
                setaside=run['setaside'], hitratio=run['hitratio'])

if __name__ == '__main__':
    C = int(json.load(open('assets/sweep/gpu_probe_ampere.json'))['gpu.l2_cache_bytes'])
    phi = json.load(open('assets/sweep/v2_fit_ampere.json'))['phi']
    asim = {}
    if os.path.exists(ASIM):
        for l in open(ASIM):
            d = json.loads(l); asim[d['workload']] = d
    out = dict(created=time.strftime('%Y-%m-%d %H:%M:%S %Z'), l2_bytes=C,
               note='Prior policy-aware simulators, added after the measurements; zero fitted parameters.',
               accelsim_workloads=asim, sets={})
    t0 = time.time()
    for name, path in SETS.items():
        rows = []
        for r in json.load(open(path))['runs']:
            run = r['run']
            if name == 'r1':
                w, sim = wl_r1(run), r1_stream(run); cls = r1_v3_classes(run)
            else:
                w, sim = wl_synth(run), run; cls = V3.synth_classes(run, 0)
            d = dict(autoscratch=AS.simulate(sim, C),
                     v3=V3.predict_v3(cls, run['setaside'], run['hitratio'], C, phi))
            if w in asim: d['accelsim'] = asim[w]['dram_read_bytes']
            rows.append(dict(run=run, workload=w, dram_read_bytes=d))
        out['sets'][name] = rows
        print(f'{name}: {len(rows)} settings, accelsim workloads {sorted({x["workload"] for x in rows if "accelsim" in x["dram_read_bytes"]})}')
    json.dump(out, open('assets/sweep/prior_sim_predictions.json', 'w'), indent=1)
    print(f'wrote assets/sweep/prior_sim_predictions.json in {time.time() - t0:.1f}s')
