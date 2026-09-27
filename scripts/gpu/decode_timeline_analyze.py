#!/usr/bin/env python3
"""Reads the nsys kernel traces of decode_timeline.sh and reports the numbers burst_shape assumes.

  python3 scripts/gpu/decode_timeline_analyze.py --fetch   # copy tl_*_cuda_gpu_trace.csv from ampere
  python3 scripts/gpu/decode_timeline_analyze.py           # analyse the local copies

Per mode: kernels per step, the gap between consecutive kernels inside a step (median, p90, sum),
the gap between steps, and the kernel time split into weight-streaming GEMMs and everything else.
Kernels are classed by name, as the 2026-09-27 trace shows them: the weight projections (q, k, v, o,
gate, up, down per layer, and lm_head) run as cutlass wmma GEMMs, the two attention matmuls per layer
(scores, P x V) as a different cutlass GEMM (s1688), and cublasLt split-K reductions follow k and v.
"""
import os, sys, csv, json, subprocess, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '..', 'assets', 'sweep', 'decode_timeline')
SERVER, REMOTE = 'dsil-sy', '~/ectc_thermal/timeline'
GEMM_KEYS = ('gemm', 'gemv', 'nvjet', 'cutlass', 'xmma', 'splitk', 'cublas')

def fetch():
    os.makedirs(OUT, exist_ok=True)
    subprocess.run(['scp', '-q', f'{SERVER}:{REMOTE}/tl_*_cuda_gpu_trace.csv', f'{SERVER}:{REMOTE}/timeline.log', OUT + '/'],
                   check=True)

def load(path):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            name = r.get('Name', '')
            if not r.get('Duration (ns)') or r.get('Duration (ns)') == '': continue
            if name.startswith('[CUDA mem') or 'memcpy' in name.lower() or 'memset' in name.lower(): continue
            rows.append((int(r['Start (ns)']), int(r['Duration (ns)']), name))
    rows.sort()
    return rows

def analyse(rows, layers=32, steps=None):
    """Split into steps (every step launches the same kernels, so equal counts; at the largest gaps
    otherwise -- in eager mode the CPU's launch gaps can exceed the step boundary), then
    characterise the middle step."""
    n_steps = steps or 10
    if len(rows) % n_steps == 0:
        k0 = len(rows)//n_steps
        bounds = list(range(0, len(rows) + 1, k0))
    else:
        gaps = [(rows[i][0] - (rows[i-1][0] + rows[i-1][1]), i) for i in range(1, len(rows))]
        cut = sorted(i for _, i in sorted(gaps, reverse=True)[:n_steps - 1])
        bounds = [0] + cut + [len(rows)]
    per = [rows[bounds[j]:bounds[j+1]] for j in range(len(bounds) - 1)]
    k = st.median(len(p) for p in per)
    per = [p for p in per if len(p) == k]
    inner = [p[i][0] - (p[i-1][0] + p[i-1][1]) for p in per for i in range(1, len(p))]
    between = [per[j+1][0][0] - (per[j][-1][0] + per[j][-1][1]) for j in range(len(per) - 1)]
    p = per[len(per)//2]
    gemm = [i for i, r in enumerate(p) if any(key in r[2].lower() for key in GEMM_KEYS)]
    attn = {i for i in gemm if 's1688gemm' in p[i][2].lower()}
    wt = [i for i in gemm if 'wmma' in p[i][2].lower()]
    span = p[-1][0] + p[-1][1] - p[0][0]
    busy = sum(r[1] for r in p)
    res = dict(kernels_per_step=k, steps_used=len(per), gemm_per_step=len(gemm),
               attention_matmuls_recognised=len(attn),
               step_span_us=span/1e3, busy_us=busy/1e3,
               weight_kernels=len(wt), weight_kernel_us=sum(p[i][1] for i in wt)/1e3,
               attention_kernel_us=sum(p[i][1] for i in attn)/1e3,
               other_kernel_us=(busy - sum(p[i][1] for i in wt) - sum(p[i][1] for i in attn))/1e3,
               other_kernels=len(p) - len(wt) - len(attn),
               inner_gap_us_median=st.median(inner)/1e3,
               inner_gap_us_p90=sorted(inner)[int(0.9*len(inner))]/1e3,
               inner_gap_us_sum=sum(inner)/len(per)/1e3,
               between_steps_us_median=(st.median(between)/1e3 if between else None),
               step=[dict(name=r[2][:80], start_us=(r[0] - p[0][0])/1e3, dur_us=r[1]/1e3,
                          cls=('weight' if i in wt else 'attn' if i in attn else 'other'))
                     for i, r in enumerate(p)])
    return res

def main():
    if '--fetch' in sys.argv: fetch()
    out = {}
    for m in ('graph', 'eager'):
        path = os.path.join(OUT, f'tl_{m}_cuda_gpu_trace.csv')
        if not os.path.exists(path): print(f'{m}: no trace yet'); continue
        r = analyse(load(path)); out[m] = r
        print(f"{m:>6}: {r['kernels_per_step']} kernels/step ({r['weight_kernels']} weight GEMM, "
              f"{r['attention_matmuls_recognised']} attention, {r['other_kernels']} other), span {r['step_span_us']:.1f} us, busy {r['busy_us']:.1f} us "
              f"(weights {r['weight_kernel_us']:.1f}, attention {r['attention_kernel_us']:.1f}, other {r['other_kernel_us']:.1f}); "
              f"gap inside a step median {r['inner_gap_us_median']:.2f} us, p90 {r['inner_gap_us_p90']:.2f}, "
              f"sum {r['inner_gap_us_sum']:.1f} us; between steps {r['between_steps_us_median']}")
    if out:
        json.dump(out, open(os.path.join(OUT, 'summary.json'), 'w'), indent=1)

if __name__ == '__main__':
    main()
