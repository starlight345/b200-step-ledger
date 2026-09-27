#!/usr/bin/env python3
"""R2 — prospective test of model v3 on real-LLM decode workloads it has not seen; predictions written BEFORE measuring.

v3 (scripts/l2policy_model_v3.py, unchanged since 2026-09-27 02:45 KST) adds one input the R1 models lacked: the
eviction priority each load carries. For R2 that input is read from each workload's own SASS before anything is
measured (scripts/prior/r2_list.sh -> r2_census.py -> r2_classes.py, evidence in assets/sweep/r2_census/<workload>/):
an operand (a weight matrix, the K or V cache) is class E when the kernel reading it does so with LDG.E.EF
(ld.global.cs, evict-first), N otherwise. The rules below were fixed with v3 on R1/C3 and are not changed for R2:
  * window lines keep the access-policy window's properties whatever the instruction says (hitRatio -> persisting,
    the rest -> streaming); the window covers the first W bytes of the packed weights (execution order, 256-B
    aligned, llm_policy_bench.pack_weights);
  * outside the window every weight span takes its matrix's class, norms are N (elementwise LDG.E), the KV cache
    takes the class of the attention kernels' K / V loads; F (fresh) = 0 as in R1;
  * phi = 0.3 and the 16-way structure are v2's (fitted on H1 only).
v3 has no rule for kernels that build their own cache-policy descriptor (createpolicy; C3 showed the window is then
ignored). Such descriptors are not visible in opcodes, so R2 cannot flag them; a large miss would point there.

Workloads (none measured before; R1 = SmolLM-135M B1/B8 and SmolLM-360M B1 at context 512):
  SmolLM-135M B1 c1536, SmolLM-360M B1 c1536 — cuBLAS gemvx (evict-first weights) over a 3x longer KV;
  SmolLM-135M B2 c512 and the other batch > 1 points — CUTLASS GEMM (normal loads): v3 = v2 there, and the
  prediction under test is that the set-aside matters again (unlike B1).
Grid = R1's (47 settings per workload). Predictors: ours v3 (under test), ours v2 and v1 (frozen), GPU-Tile-Sim L2
(FA-LRU, R1's gtsim_l2), AutoScratch semantics, MemExplorer eq. (4). LLMCompass and GenZ are policy-blind like
GPU-Tile-Sim and are not run for R2.

Usage: python3 scripts/r2_predict.py   -> assets/sweep/r2_predictions_ampere.json
"""
import glob, hashlib, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'prior'))
import llm_predict as LP
import l2policy_model as V1
import l2policy_model_v2 as V2
import l2policy_model_v3 as V3
import autoscratch_pin as AS

MiB = 1 << 20
CENSUS = 'assets/sweep/r2_census'
# measurement order (r2_run.py follows the file): the workloads where v3 and v2 disagree (evict-first weights) first
ORDER = ('SmolLM-135M/B1/c1536', 'SmolLM-360M/B1/c1536', 'SmolLM-135M/B2/c512', 'SmolLM-360M/B8/c512',
         'SmolLM-135M/B4/c512', 'SmolLM-360M/B4/c512')

def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()

def layout(cfg):
    """Packed weight spans (operand, bytes) in pack_weights order: per layer q,k,v,o,gate,up,down + 2 norms,
    final norm, tied embedding (LM head) last; each span rounded up to 256 B."""
    H, I, L = cfg['hidden_size'], cfg['intermediate_size'], cfg['num_hidden_layers']
    nh, kvh = cfg['num_attention_heads'], cfg['num_key_value_heads']; hd = H // nh
    al = lambda n: -(-n // 128) * 128 * 2
    spans = []
    for _ in range(L):
        spans += [('q', al(H * H)), ('k', al(H * kvh * hd)), ('v', al(H * kvh * hd)), ('o', al(H * H)),
                  ('gate', al(H * I)), ('up', al(H * I)), ('down', al(I * H)), ('norm', al(H)), ('norm', al(H))]
    return spans + [('norm', al(H)), ('lm_head', al(cfg['vocab_size'] * H))]

def v3_classes(cfg, run, cls):
    """MiB per step in v3's classes W (window), E (evict-first), N (normal), F (fresh)."""
    b = LP.step_bytes(cfg, run['batch'], run['context'])
    spans = layout(cfg); total = sum(n for _, n in spans)
    assert total == b['weights'], (total, b['weights'])
    Wb = min(run['window'] * MiB, total)
    E = N = pos = 0
    for op, n in spans:
        out = max(0, pos + n - max(pos, Wb))                  # bytes of this span beyond the window
        if cls.get(op, 'N') == 'E': E += out
        else: N += out
        pos += n
    for half in ('K', 'V'):
        if cls[half] == 'E': E += b['kv_read'] / 2
        else: N += b['kv_read'] / 2
    return dict(W=Wb / MiB, E=E / MiB, N=N / MiB, F=0.0)

def grid(model, batch, context):
    return [dict(r, context=context) for r in LP.grid(model, batch)]      # R1's 47 settings at this context

def predict(run, C, phi, cls):
    cfg = json.load(open(os.path.join(LP.HF, run['model'] + '.json')))
    b = LP.step_bytes(cfg, run['batch'], run['context'])
    total = b['weights'] + b['kv_read']
    W = min(run['window'] * MiB, b['weights'])
    sim = dict(mode='llm', ws=total / MiB, layers=1, window=W / MiB, setaside=run['setaside'], hitratio=run['hitratio'])
    c3 = v3_classes(cfg, run, cls)
    out = {
        'memexplorer': total - min(C, b['weights']),
        'gtsim_l2': V1.simulate(dict(sim, window=0, setaside=0, hitratio=0), C, 64 * 1024, knobs=False),
        'ours_v1': V1.simulate(sim, C, 64 * 1024, knobs=True),
        'ours_v2': V2.predict_v2(sim, C, phi),
        'autoscratch': AS.simulate(sim, C),
        'v3': V3.predict_v3(c3, run['setaside'], run['hitratio'], C, phi),
    }
    return dict(run=run, bytes=b, v3_classes_mib=c3, dram_read_bytes=out)

if __name__ == '__main__':
    probe = json.load(open('assets/sweep/gpu_probe_ampere.json'))
    C = int(probe['gpu.l2_cache_bytes'])
    phi = json.load(open('assets/sweep/v2_fit_ampere.json'))['phi']
    work, evidence = [], {}
    dirs = {json.load(open(os.path.join(d, 'classes.json')))['workload']: d for d in glob.glob(os.path.join(CENSUS, 'r2_*'))}
    for d in [dirs[w] for w in ORDER if w in dirs]:
        c = json.load(open(os.path.join(d, 'classes.json')))
        if c['unmatched']: sys.exit(f'{d}: operands without a matching kernel {c["unmatched"]}')
        model, B, ctx = c['workload'].split('/'); batch, context = int(B[1:]), int(ctx[1:])
        cls = {op: v['class'] for op, v in c['operands'].items()}
        work.append((model, batch, context, cls))
        evidence[c['workload']] = dict(classes=cls, census_sha256=sha(os.path.join(d, 'census.jsonl'))[:16],
                                       kernels={op: v['kernel'] for op, v in c['operands'].items()})
    t0 = time.time(); runs = []
    for model, batch, context, cls in work:
        runs += [predict(r, C, phi, cls) for r in grid(model, batch, context)]
        print(f'{model} B{batch} c{context}: classes {"".join(cls[k] for k in ("q","k","v","o","gate","up","down","lm_head","K","V"))} '
              f'(q k v o gate up down lm_head K V)  {time.time() - t0:.0f}s', flush=True)
    doc = dict(created=time.strftime('%Y-%m-%d %H:%M:%S %Z'), machine=probe['host'], l2_bytes=C, phi=phi,
               model_sha256={f: sha(f)[:16] for f in ('scripts/l2policy_model.py', 'scripts/l2policy_model_v2.py',
                                                      'scripts/l2policy_model_v3.py', 'scripts/prior/autoscratch_pin.py',
                                                      'scripts/r2_predict.py')},
               load_classes=evidence, engine='manual (llm_policy_bench.py), decode at position = context',
               note='R2 real-LLM decode, workloads unseen by v3. All predictors frozen before measuring.', runs=runs)
    json.dump(doc, open('assets/sweep/r2_predictions_ampere.json', 'w'), indent=1)
    print(len(runs), 'settings predicted')
