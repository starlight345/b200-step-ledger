#!/usr/bin/env python3
"""R3 — intervention test, predictions written BEFORE measuring.

R2 showed that from batch 2 the decode weights are read by a CUTLASS GEMM with normal-priority loads, and the
set-aside matters again (unlike batch 1, where cuBLAS gemvx reads them evict-first). R3 changes only that: every
decode projection (q, k, v, o, gate, up, down, LM head) runs through scripts/gpu/cs_linear.py (CUDA kernel
cs_linear_kernel.cu, weights via __ldcs), which reads the weight matrix with ld.global.cs (SASS LDG.E.EF) — the batch-1 load class — and everything else as before (prefill, norms,
attention GEMMs on the KV cache). Same four workloads as R2's batch > 1 set, same 47-setting grid.

What is predicted, with the models exactly as frozen for R2 (v3 sha afb0e71d1c541c29, phi 0.3):
  v3 with the weight operands in class E (the intervention), K and V in class N (unchanged kernels);
  the prior predictors of r2_predict (v2, v1, GPU-Tile-Sim L2, AutoScratch semantics, MemExplorer eq. 4), which
  cannot represent a load class and therefore predict R3 exactly as they predicted R2;
  and, for reference, v3 without the intervention (= R2's frozen v3), so the predicted effect is explicit.

Usage: python3 scripts/r3_predict.py   -> assets/sweep/r3_predictions_ampere.json
"""
import hashlib, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import r2_predict as R2

MiB = 1 << 20
WORKLOADS = ('SmolLM-135M/B2/c512', 'SmolLM-135M/B4/c512', 'SmolLM-360M/B4/c512', 'SmolLM-360M/B8/c512')
WEIGHTS = ('q', 'k', 'v', 'o', 'gate', 'up', 'down', 'lm_head')

def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()

if __name__ == '__main__':
    probe = json.load(open('assets/sweep/gpu_probe_ampere.json'))
    C = int(probe['gpu.l2_cache_bytes'])
    phi = json.load(open('assets/sweep/v2_fit_ampere.json'))['phi']
    r2 = json.load(open('assets/sweep/r2_predictions_ampere.json'))
    r2v3 = {json.dumps(r['run'], sort_keys=True): r['dram_read_bytes']['v3'] for r in r2['runs']}
    runs, classes = [], {}
    for w in WORKLOADS:
        model, B, ctx = w.split('/'); batch, context = int(B[1:]), int(ctx[1:])
        cls = dict(r2['load_classes'][w]['classes'])
        assert all(cls[k] == 'N' for k in WEIGHTS), (w, cls)          # R2 census: CUTLASS, normal loads
        cls.update({k: 'E' for k in WEIGHTS})                          # the intervention
        classes[w] = cls
        for r in R2.grid(model, batch, context):
            p = R2.predict(r, C, phi, cls)
            p['run'] = dict(r, weights_cs=True)
            p['v3_without_intervention'] = r2v3[json.dumps(r, sort_keys=True)]
            runs.append(p)
    doc = dict(created=time.strftime('%Y-%m-%d %H:%M:%S %Z'), machine=probe['host'], l2_bytes=C, phi=phi,
               model_sha256={f: sha(f)[:16] for f in ('scripts/l2policy_model_v3.py', 'scripts/r2_predict.py', 'scripts/r3_predict.py',
                                                      'scripts/gpu/cs_linear.py', 'scripts/gpu/cs_linear_kernel.cu')},
               r2_predictions_sha256=sha('assets/sweep/r2_predictions_ampere.json')[:16], load_classes=classes,
               note='R3 intervention (weights read evict-first at batch > 1). All predictors frozen before measuring.',
               runs=runs)
    json.dump(doc, open('assets/sweep/r3_predictions_ampere.json', 'w'), indent=1)
    print(len(runs), 'settings predicted')
    for w in WORKLOADS:
        g = {(r['run']['window'], r['run']['setaside'], r['run']['hitratio']): r for r in runs
             if f"{r['run']['model']}/B{r['run']['batch']}/c{r['run']['context']}" == w}
        b = g[(0, 0, 0)]; s12, s60 = g[(127, 12, 0.4)], g[(127, 60, 0.4)]
        best = min(g, key=lambda k: g[k]['dram_read_bytes']['v3'])
        print(f"{w}: step {(b['bytes']['weights'] + b['bytes']['kv_read']) / MiB:.1f} MiB (KV {b['bytes']['kv_read'] / MiB:.1f}); "
              f"v3 baseline {b['dram_read_bytes']['v3'] / MiB:.1f} (without intervention {b['v3_without_intervention'] / MiB:.1f}); "
              f"S12-S60 at W127 r.4: v3 {(s12['dram_read_bytes']['v3'] - s60['dram_read_bytes']['v3']) / MiB:+.1f} "
              f"(without {(s12['v3_without_intervention'] - s60['v3_without_intervention']) / MiB:+.1f}); "
              f"v3 best {best} {g[best]['dram_read_bytes']['v3'] / MiB:.1f}")
