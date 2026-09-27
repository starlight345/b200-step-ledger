#!/usr/bin/env python3
"""L2 capacity projection: how much L2 does LLM decode need, and does the answer depend on the cache policy and on
how the kernels load? Model calculation, anchored by measurement at the one capacity we have (96 MiB).

Workloads are R2's (validated there): SmolLM-360M c1536 B1 (weights read evict-first by cuBLAS gemvx: class E) and
SmolLM-360M c512 B4 (CUTLASS GEMM, normal loads: class N), plus the 135M pair. For each L2 capacity C:
  lru            one fully-associative LRU L2 (GPU-Tile-Sim; Accel-Sim gave the same bytes) — policy-blind
  capacity_only  MemExplorer eq. (4): DRAM = step - min(C, weights) — every stored byte useful
  v3_native      v3 with the workload's own load classes, no access-policy window
  v3_best        v3 with the best (set-aside S <= 10/16 C, window W, hitRatio r) found on a grid — what a designer can
                 reach with the persistence controls. The 16-way structure and phi = 0.3 are v2's. The window is capped
                 at max(128 MiB, 4/3 C): this GPU's maximum is 128 MiB = 4/3 of its L2, and the projection assumes the
                 maximum grows with L2 in that ratio (an assumption, not a measurement).
  v3_*_ef        the same with the weights read evict-first (R3's intervention) — for the batch > 1 workloads only.
The v3 inputs at C != 96 MiB are a projection: v3 was validated at 96 MiB only (R2: MAE 7.5 MiB, 30/30 best picks).
Writes assets/sweep/capacity_projection.json.

Usage: python3 scripts/capacity_projection.py
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import llm_predict as LP
import l2policy_model as V1
import l2policy_model_v3 as V3
import r2_predict as R2

MiB = 1 << 20
CAPS = (48, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640, 704, 768, 832, 896, 960, 1024)  # MiB
WORK = ('SmolLM-360M/B1/c1536', 'SmolLM-360M/B4/c512', 'SmolLM-135M/B1/c1536', 'SmolLM-135M/B4/c512')
R_GRID = tuple(i / 10 for i in range(11))

def evaluate(w, cls, C_mib, phi, tag=''):
    model, B, ctx = w.split('/'); batch, context = int(B[1:]), int(ctx[1:])
    cfg = json.load(open(os.path.join(LP.HF, model + '.json')))
    b = LP.step_bytes(cfg, batch, context)
    step = b['weights'] + b['kv_read']; C = C_mib * MiB
    base = dict(model=model, batch=batch, context=context)
    out = dict(C_mib=C_mib, step_mib=step / MiB)
    sim = dict(mode='llm', ws=step / MiB, layers=1, window=0, setaside=0, hitratio=0)
    out['lru'] = V1.simulate(sim, C, 64 * 1024, knobs=False) / MiB
    out['capacity_only'] = (step - min(C, b['weights'])) / MiB
    c0 = R2.v3_classes(cfg, dict(base, window=0), cls)
    out['v3_native' + tag] = max(0.0, V3.predict_v3(c0, 0, 0, C, phi) / MiB)
    best = (out['v3_native' + tag], dict(window=0, setaside=0, hitratio=0))
    S_grid = sorted({round(C_mib * k / 16, 3) for k in range(0, 11)})
    wmax = max(128.0, C_mib * 4 / 3)
    W_grid = sorted({min(round(C_mib * f, 3), wmax, b['weights'] / MiB) for f in (0.5, 1.0, 4 / 3)} | ({127.0} if C_mib <= 96 else set()))
    for W in W_grid:
        cw = R2.v3_classes(cfg, dict(base, window=W), cls)
        for S in S_grid:
            for r in R_GRID:
                d = max(0.0, V3.predict_v3(cw, S, r, C, phi) / MiB)
                if d < best[0] - 1e-9: best = (d, dict(window=W, setaside=S, hitratio=r))
    out['v3_best' + tag], out['v3_best_setting' + tag] = best
    return out

if __name__ == '__main__':
    phi = json.load(open('assets/sweep/v2_fit_ampere.json'))['phi']
    r2 = json.load(open('assets/sweep/r2_predictions_ampere.json'))
    res = {}; t0 = time.time()
    for w in WORK:
        cls = r2['load_classes'][w]['classes']
        pts = [evaluate(w, cls, c, phi) for c in CAPS]
        if cls['q'] == 'N':                                    # R3's intervention: weights evict-first
            ef = dict(cls, **{k: 'E' for k in ('q', 'k', 'v', 'o', 'gate', 'up', 'down', 'lm_head')})
            for p, c in zip(pts, CAPS):
                e = evaluate(w, ef, c, phi, tag='_ef')
                p.update({k: v for k, v in e.items() if k.endswith('_ef')})
        res[w] = dict(classes=cls, points=pts)
        print(f'{w} ({"".join(cls[k] for k in ("q", "down", "lm_head", "K"))}): {time.time() - t0:.0f}s')
        for p in res[w]['points']:
            ef = f"  | ef: native {p['v3_native_ef']:6.1f} best {p['v3_best_ef']:6.1f}" if 'v3_native_ef' in p else ''
            print(f"  C {p['C_mib']:>5} MiB  step {p['step_mib']:6.1f}  lru {p['lru']:6.1f}  cap-only {p['capacity_only']:6.1f}  "
                  f"v3 native {p['v3_native']:6.1f}  v3 best {p['v3_best']:6.1f} {p['v3_best_setting']}{ef}")
    json.dump(dict(created=time.strftime('%Y-%m-%d %H:%M:%S %Z'), phi=phi, caps_mib=CAPS,
                   note='Model projection anchored at 96 MiB (R2). v3 validated at 96 MiB only.', workloads=res),
              open('assets/sweep/capacity_projection.json', 'w'), indent=1)
    print('wrote assets/sweep/capacity_projection.json')
