#!/usr/bin/env python3
"""G-1: is the traffic-to-time coefficient CAUSAL, or just a fit?

The canon carries HBM effective = 6.40 TB/s as a regression across four measured B200
decode anchors. Every speedup in the project hangs on it, and it has always been labelled
"causality NOT validated" because a fit across (B, N) points moves traffic and compute and
launch overhead together.

This makes the test causal by moving ONE thing. Two independent knobs:

  K1  context length at fixed batch. Weight traffic is constant in N; KV traffic is
      exactly B * N * kv_bytes_per_token. So d(step_time)/d(KV bytes) isolates the
      delivered-byte coefficient with the model, the batch and the kernel set fixed.
  K2  KV cache dtype at fixed (B, N). Halving KV bytes changes no tensor shape and no
      GEMM, only how many bytes the attention kernel fetches.

If both knobs return the same slope, the coefficient is a property of the memory path
rather than an artefact of the sweep, and the structure transfers to B200 with B200's own
slope substituted. That is the claim the ECTC admission floor actually needs -- the
number 6.40 is B200-specific, the STRUCTURE is what has to hold.

This runs on any CUDA GPU. On an RTX PRO 5000 Blackwell it measures that part's slope,
not the B200's; the point is the structure, and the per-platform slope is an input.
"""
import argparse, json, os, statistics, sys, time

def kv_bytes_per_token(cfg):
    """2 (K and V) * layers * kv_heads * head_dim * dtype_bytes."""
    n_layer = cfg.num_hidden_layers
    n_kv = getattr(cfg, 'num_key_value_heads', cfg.num_attention_heads)
    head = getattr(cfg, 'head_dim', cfg.hidden_size // cfg.num_attention_heads)
    return 2 * n_layer * n_kv * head

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='Qwen/Qwen2.5-0.5B')
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--batches', type=int, nargs='+', default=None,
                    help='K2: sweep BATCH at a fixed context instead of sweeping context. '
                         'KV traffic scales as B*N either way, but the mechanism is '
                         'different, so agreeing slopes are independent evidence. '
                         '(The original K2, KV dtype, is unavailable: vLLM 0.10.2 V1 does '
                         'not support --kv-cache-dtype and the V0 fallback hits a '
                         'flash-attention launch error on this Blackwell part.)')
    ap.add_argument('--contexts', type=int, nargs='+', default=[512, 1024, 2048, 4096])
    ap.add_argument('--gen', type=int, default=48, help='decode steps to time per point')
    ap.add_argument('--warmup', type=int, default=8)
    ap.add_argument('--kv-dtype', default='auto', choices=['auto', 'fp8'])
    ap.add_argument('--gpu-frac', type=float, default=0.14)
    ap.add_argument('--eager', action='store_true',
                    help='disable CUDA graphs. Leave OFF: in eager mode a small model is '
                         'launch-latency bound and the traffic slope comes out negative, '
                         'which is the same failure that made the existing B200 '
                         'microbenchmarks unusable for this question.')
    ap.add_argument('--peak-TBs', type=float, default=1.211,
                    help='measured achievable read bandwidth of this part, used as a '
                         'plausibility bound on the fitted slope (RTX PRO 5000 Blackwell: '
                         '1.211 TB/s read, 1.105 copy, by a torch bandwidth probe)')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    from vllm import LLM, SamplingParams
    import torch

    # Prefix caching MUST be off. The step time is extracted by differencing two
    # generation lengths so that prefill cancels; with prefix caching on, the second call
    # reuses the first call's prefill, the cancellation is wrong, and the error grows with
    # N. That inflates B_eff -- it is what first produced 2.39 TB/s on a part whose
    # measured ceiling is 1.21 TB/s.
    kw = dict(model=a.model, dtype='bfloat16', kv_cache_dtype=a.kv_dtype,
              gpu_memory_utilization=a.gpu_frac,
              max_model_len=max(a.contexts)+a.gen*3+8,
              max_num_seqs=max(a.batches) if a.batches else a.batch,
              enable_prefix_caching=False,
              enforce_eager=a.eager, disable_log_stats=True)
    try:
        llm = LLM(**kw)
    except TypeError:
        kw.pop('disable_log_stats'); llm = LLM(**kw)
    cfg = llm.llm_engine.model_config.hf_config
    kvb = kv_bytes_per_token(cfg) * (1 if a.kv_dtype == 'fp8' else 2)

    def tok_prompts(ids_list):
        """generate() took prompt_token_ids= up to ~0.9 and TokensPrompt dicts after.
        The dict form is accepted by both, so use it and stay version-portable."""
        return [{'prompt_token_ids': ids} for ids in ids_list]

    points = ([(a.batch, N) for N in a.contexts] if not a.batches
              else [(B, a.contexts[0]) for B in a.batches])
    knob = 'context' if not a.batches else 'batch'
    print(f'  knob: {knob}\n')
    rows = []
    for (Bn, N) in points:
        prompt = [[1000 + (i % 5000) for i in range(N)] for _ in range(Bn)]
        sp = SamplingParams(max_tokens=a.gen, min_tokens=a.gen, temperature=0.0, ignore_eos=True)
        pr = tok_prompts(prompt)
        llm.generate(pr, SamplingParams(max_tokens=a.warmup, min_tokens=a.warmup,
                                        temperature=0.0, ignore_eos=True))
        torch.cuda.synchronize(); t0 = time.perf_counter()
        llm.generate(pr, sp)
        torch.cuda.synchronize(); t1 = time.perf_counter()
        # prefill is amortised out by differencing two generation lengths
        sp2 = SamplingParams(max_tokens=a.gen*3, min_tokens=a.gen*3, temperature=0.0, ignore_eos=True)
        torch.cuda.synchronize(); t2 = time.perf_counter()
        llm.generate(pr, sp2)
        torch.cuda.synchronize(); t3 = time.perf_counter()
        step_ms = ((t3-t2) - (t1-t0)) / (a.gen*2) * 1e3     # differenced: prefill cancels
        kv_GB = Bn * N * kvb / 1e9
        rows.append(dict(context=N, batch=Bn, kv_dtype=a.kv_dtype, step_ms=step_ms,
                         kv_GB=kv_GB, kv_bytes_per_token=kvb))
        print(f'  N={N:>6} B={Bn:>3}  step {step_ms:8.4f} ms   KV read {kv_GB:7.4f} GB/step')

    # slope of step_ms against KV GB: weights are constant in N, so this is causal
    xs = [r['kv_GB'] for r in rows]; ys = [r['step_ms'] for r in rows]
    n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs); sxy = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    slope = sxy/sxx if sxx else float('nan')          # ms per GB
    b_eff = 1.0/slope if slope else float('nan')      # GB/ms == TB/s
    t0_ms = my - slope*mx
    ss = sum((y-my)**2 for y in ys)
    r2 = 1 - sum((y - (t0_ms+slope*x))**2 for x, y in zip(xs, ys))/ss if ss else float('nan')
    print(f'\n  slope {slope:.5f} ms/GB  ->  B_eff = {b_eff:.3f} TB/s   '
          f'(intercept {t0_ms:.4f} ms, R^2 {r2:.5f})')
    # Guard, corrected. The intercept is NOT a latency term here: weight traffic is
    # constant in N, so it sits in the intercept by construction and a large intercept is
    # expected. The checks that matter are that the slope is positive, well determined,
    # and does not imply a bandwidth the part cannot deliver.
    frac_fixed = t0_ms/max(ys) if max(ys) else float('nan')
    checks = {
        'slope positive':        slope > 0,
        'R^2 > 0.95':            r2 > 0.95,
        f'B_eff <= measured peak {a.peak_TBs:.3f} TB/s': 0 < b_eff <= a.peak_TBs*1.05,
    }
    for k, v in checks.items():
        print(f'    [{"PASS" if v else "FAIL"}] {k}')
    out_ok = all(checks.values())
    print(f'  intercept is {frac_fixed*100:.1f}% of the largest step -- expected, it carries '
          f'the N-independent weight traffic')
    print(f'  verdict: {"causal slope usable" if out_ok else "NOT a usable bandwidth slope"}')
    out = dict(model=a.model, knob=knob, batch=a.batch, kv_dtype=a.kv_dtype, rows=rows,
               slope_ms_per_GB=slope, B_eff_TBs=b_eff, intercept_ms=t0_ms, r2=r2,
               fixed_fraction=frac_fixed, bandwidth_bound=out_ok, eager=a.eager)
    if a.out:
        json.dump(out, open(a.out, 'w'), indent=2); print(f'  wrote {a.out}')
    return out

if __name__ == '__main__':
    main()
