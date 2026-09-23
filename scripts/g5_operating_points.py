#!/usr/bin/env python3
"""Second workload vector: the duty envelope the tier must actually cover.

The ECTC template (ECTC 2020) does not characterise a package against one workload; it
uses two power-indicative vectors, an average case and a worst case, and builds the power
map from both. Our thermal work so far stands on ONE decode operating point (B=8, N=2048).
This measures step time and decode power across a grid of operating points on real
hardware and turns each into a tier duty cycle, so the envelope is measured rather than
assumed from a single anchor.

For each point: step time by differencing two generation lengths (prefill cancels, prefix
caching off), package power sampled at 20 Hz over the settled part of the decode run, and
the implied tier duty
        d = f_red * D_step / (B_R * t_step)
with D_step the measured-structure per-step demand and f_red the trace-replay tier share.
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True)
    ap.add_argument('--points', default='8x2048,8x8192,16x2048,32x2048,32x4096',
                    help='comma list of BxN operating points')
    ap.add_argument('--gen', type=int, default=64)
    ap.add_argument('--gpu-frac', type=float, default=0.85)
    ap.add_argument('--out', default='g5_points.json')
    a = ap.parse_args()

    from vllm import LLM, SamplingParams
    import torch
    from g4_phase_power import PowerSampler, stats

    pts = [tuple(int(v) for v in p.split('x')) for p in a.points.split(',')]
    maxB = max(b for b, _ in pts); maxN = max(n for _, n in pts)
    llm = LLM(model=a.model, dtype='bfloat16', gpu_memory_utilization=a.gpu_frac,
              max_model_len=maxN + a.gen*3 + 16, max_num_seqs=maxB,
              enable_prefix_caching=False, disable_log_stats=True)

    smp = PowerSampler(); smp.start()
    tw = time.perf_counter()
    while not smp.samples and time.perf_counter()-tw < 15: time.sleep(0.25)
    time.sleep(1.5)

    W_PER_STEP = 15.010          # GB, canon weight read per decode step [public-derived]
    KV_PER_TOK = 131072          # B, canon
    rows = []
    for (B, N) in pts:
        pr = [{'prompt_token_ids': [1000 + (i % 5000) for i in range(N)]} for _ in range(B)]
        llm.generate(pr, SamplingParams(max_tokens=8, min_tokens=8, temperature=0.0, ignore_eos=True))
        torch.cuda.synchronize(); t0 = time.perf_counter()
        llm.generate(pr, SamplingParams(max_tokens=a.gen, min_tokens=a.gen,
                                        temperature=0.0, ignore_eos=True))
        torch.cuda.synchronize(); t1 = time.perf_counter()
        torch.cuda.synchronize(); t2 = time.perf_counter()
        llm.generate(pr, SamplingParams(max_tokens=a.gen*3, min_tokens=a.gen*3,
                                        temperature=0.0, ignore_eos=True))
        torch.cuda.synchronize(); t3 = time.perf_counter()
        step_ms = ((t3-t2) - (t1-t0))/(a.gen*2)*1e3
        pw = stats(smp.between(t2 + (t3-t2)*0.35, t3))
        D_GB = W_PER_STEP + B*N*KV_PER_TOK/1e9          # structural per-step demand
        rows.append(dict(batch=B, context=N, step_ms=step_ms, demand_GB=D_GB,
                         power_mean_W=pw.get('mean'), power_sd_W=pw.get('sd'),
                         power_peak_W=pw.get('peak')))
        print(f'  B={B:>3} N={N:>6}  step {step_ms:8.3f} ms   demand {D_GB:7.3f} GB   '
              f'power {pw.get("mean", float("nan")):6.1f} W (sd {pw.get("sd", 0):.1f})')
    smp.stop()

    # tier duty at each point, with the canonical tier share and fabric cap
    F_RED, B_R = 0.2400, 19.0
    print(f'\n  implied tier duty (f_red={F_RED}, B_R={B_R} TB/s):')
    print(f"{'point':>14} {'served GB':>10} {'burst ms':>10} {'duty %':>9}")
    for r in rows:
        served = F_RED*r['demand_GB']; burst = served/B_R          # GB/(TB/s) == ms
        r['tier_served_GB'] = served; r['burst_ms'] = burst
        r['duty'] = burst/r['step_ms']
        print(f"{'B=%d N=%d' % (r['batch'], r['context']):>14} {served:>10.3f} {burst:>10.4f} "
              f"{r['duty']*100:>8.3f}%")
    ds = [r['duty'] for r in rows]
    print(f'\n  duty envelope across operating points: {min(ds)*100:.2f}% .. {max(ds)*100:.2f}%')
    json.dump(dict(model=a.model, f_red=F_RED, B_R_TBs=B_R, rows=rows), open(a.out, 'w'), indent=2)
    print(f'  wrote {a.out}')

if __name__ == '__main__':
    main()
