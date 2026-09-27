#!/usr/bin/env python3
"""D3b — predictions written BEFORE measuring: does the access-policy window reach loads whose L2 policy descriptor the
kernel built itself, when the priority it asks for is normal? And does it reach the TMA bulk-copy path?

Why: D3 found that loads carrying a createpolicy descriptor (evict_first or evict_last) ignore the window, and guessed
the mechanism: the window travels in the driver's default descriptor (constant bank, c[0x0][0x358] on sm_120), so a
kernel-built descriptor replaces it whatever priority it asks for. The static census (scripts/prior/load_hint_census.py)
then found kernel-built descriptors on the TMA loads of every CUTLASS 3.x GEMM in vLLM on sm_90 / sm_100 / sm_120 and in
FlashMLA — so the guess decides whether the window works for those kernels at all. Two readings, frozen here:
  v3       (unchanged, afb0e71d): only the priority matters; hints 4-7 are normal loads, the window applies (= plain);
  v3_desc  (the v3.1 candidate D3 suggested): the window applies only to loads that carry the driver's default
           descriptor. Hints 4, 5 (LDG + createpolicy evict_normal / evict_unchanged) and 7 (UBLKCP + L2::cache_hint
           evict_normal) have a kernel-built descriptor -> no window -> every setting = the kernel's no-window baseline.
           Hint 6 (UBLKCP without a hint) carries no descriptor at all (SASS `UBLKCP.S.G [UR44], [UR4], UR6`); the strict
           reading gives it no window either, but that case is the least certain.
Controls measured in the same session: hint 0 (plain LDG, D2) and hint 3 (ld.global.cs, D3).
Grid = D3's (ws 268 MiB as 32 kernels; baseline, window 127 MiB x set-aside {12, 60} x hitRatio {0.4, 1.0}) plus two
settings where the readings differ most for normal-priority loads: (127, 60, 0.3) and (127, 36, 0.4).
Other predictors as D3: fixed LRU (GPU-Tile-Sim-like), ours v1 (cuda_policy), v2.

Usage: python3 scripts/d3b_predict.py   -> assets/sweep/d3b_predictions_ampere.json
"""
import hashlib, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import l2policy_model as V1
import l2policy_model_v2 as V2
import l2policy_model_v3 as V3

MiB = 1 << 20
HINTS = (0, 3, 4, 5, 6, 7)
SETTINGS = [(0, 0, 0)] + [(127, s, r) for s in (12, 60) for r in (0.4, 1.0)] + [(127, 60, 0.3), (127, 36, 0.4)]
BUILT = (1, 2, 4, 5, 6, 7)          # no driver default descriptor on the loads (6: no descriptor at all)

def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()

def predict(run, C, phi):
    h = run['hint']
    v3 = V3.predict_v3(V3.synth_classes(run, h), run['setaside'], run['hitratio'], C, phi)
    if h in BUILT:
        nowin = dict(run, window=0)
        v3d = V3.predict_v3(V3.synth_classes(nowin, h), run['setaside'], run['hitratio'], C, phi)
    else:
        v3d = v3
    return dict(run=run, dram_bytes=dict(
        fixed_lru=V1.simulate(dict(run, window=0, setaside=0, hitratio=0), C, 64 * 1024, knobs=False),
        cuda_policy=V1.simulate(run, C, 64 * 1024, knobs=True),
        v2=V2.predict_v2(run, C, phi), v3=v3, v3_desc=v3d))

if __name__ == '__main__':
    probe = json.load(open('assets/sweep/gpu_probe_ampere.json'))
    C = int(probe['gpu.l2_cache_bytes'])
    phi = json.load(open('assets/sweep/v2_fit_ampere.json'))['phi']
    runs = [predict(dict(mode='llm', ws=268, layers=32, hint=h, window=w, setaside=s, hitratio=r), C, phi)
            for h in HINTS for w, s, r in SETTINGS]
    doc = dict(created=time.strftime('%Y-%m-%d %H:%M:%S %Z'), machine=probe['host'], l2_bytes=C, phi=phi,
               model_sha256={f: sha(f)[:16] for f in ('scripts/l2policy_model.py', 'scripts/l2policy_model_v2.py',
                                                      'scripts/l2policy_model_v3.py', 'scripts/d3b_predict.py',
                                                      'scripts/gpu/l2policy_bench.cu')},
               note='D3b: kernel-built descriptors with normal priority, and the TMA bulk-copy path. v3 (priority only) vs '
                    'v3_desc (window only through the default descriptor). Frozen before measuring.', runs=runs)
    json.dump(doc, open('assets/sweep/d3b_predictions_ampere.json', 'w'), indent=1)
    print(f"{'hint':>4} {'setting':<16}" + ''.join(f'{k:>12}' for k in runs[0]['dram_bytes']))
    for r in runs:
        q = r['run']
        print(f"{q['hint']:>4} W{q['window']:>3} S{q['setaside']:>2} r{q['hitratio']:<4}  " +
              ''.join(f'{v / MiB:12.1f}' for v in r['dram_bytes'].values()))
