#!/usr/bin/env python3
"""G-4: measure package power in prefill versus decode.

ECTC_STORY step 5 says the tier's own heat is negligible and what binds is the absolute
junction temperature it sits at -- the logic plane's. It also says prefill, being
compute-bound, runs nearer TDP than decode. That second half was asserted from first
principles and never measured: the canon has decode package power (698.7 W on B200) and
nothing for prefill.

This measures both phases on the same part in the same run, so the comparison is a ratio
and does not depend on the part. Two phases are separated by construction rather than by
trying to slice one timeline:

  PREFILL   max_tokens=1 over a long prompt. One decode step out of a whole forward pass
            over B*N tokens, so the window is prefill to within a percent.
  DECODE    a long generation, with power sampled only after the prefill window has
            certainly closed (a settle fraction of the run is discarded).

Sampling is NVML at ~20 Hz in a side thread; the phase boundary is taken from wall clock
in the main thread, so the two never contend.
"""
import argparse, json, os, statistics, sys, threading, time

class PowerSampler(threading.Thread):
    """NVML if it is importable, otherwise a streaming `nvidia-smi -lms`. The venv that
    has a working vLLM for this driver has no pynvml and no pip, so the subprocess path
    is the one that actually runs here. Samples are timestamped on arrival in this
    thread, which is accurate to well under the 50 ms stream interval."""
    def __init__(self, hz=20):
        super().__init__(daemon=True)
        self.hz = hz; self.samples = []; self._halt = threading.Event()   # NOT the name Thread already uses internally
        self.proc = None; self.nvml = None
        try:
            import pynvml
            self.nvml = pynvml; pynvml.nvmlInit()
            self.h = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            self.nvml = None
    def run(self):
        if self.nvml is not None:
            while not self._halt.is_set():
                try:
                    self.samples.append((time.perf_counter(),
                                         self.nvml.nvmlDeviceGetPowerUsage(self.h)/1000.0))
                except Exception:
                    pass
                time.sleep(1.0/self.hz)
            return
        import subprocess
        ms = int(1000/self.hz)
        self.proc = subprocess.Popen(
            ['nvidia-smi', '--query-gpu=power.draw', '--format=csv,noheader,nounits',
             '-lms', str(ms)],   # the flag needs a space: '-lms50' is rejected
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        for line in self.proc.stdout:
            if self._halt.is_set(): break
            line = line.strip()
            try:
                self.samples.append((time.perf_counter(), float(line)))
            except ValueError:
                pass
    def stop(self):
        self._halt.set()
        if self.proc is not None:
            try: self.proc.terminate()
            except Exception: pass
        self.join(timeout=3)
    def between(self, t0, t1):
        return [w for t, w in self.samples if t0 <= t <= t1]

def stats(ws):
    if not ws: return dict(n=0)
    return dict(n=len(ws), mean=statistics.mean(ws), p95=sorted(ws)[int(len(ws)*0.95)-1],
                peak=max(ws), sd=(statistics.pstdev(ws) if len(ws) > 1 else 0.0))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True)
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--prefill-ctx', type=int, default=8192)
    ap.add_argument('--decode-ctx', type=int, default=2048)
    ap.add_argument('--decode-tokens', type=int, default=512)
    ap.add_argument('--settle', type=float, default=0.35,
                    help='fraction of the decode run discarded so the prefill window cannot leak in')
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--gpu-frac', type=float, default=0.80)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    from vllm import LLM, SamplingParams
    import torch
    llm = LLM(model=a.model, dtype='bfloat16', gpu_memory_utilization=a.gpu_frac,
              max_model_len=max(a.prefill_ctx, a.decode_ctx + a.decode_tokens) + 16,
              enable_prefix_caching=False, disable_log_stats=True)

    smp = PowerSampler(); smp.start()
    # nvidia-smi takes a moment to start streaming; wait until samples actually arrive
    t_wait = time.perf_counter()
    while not smp.samples and time.perf_counter() - t_wait < 15:
        time.sleep(0.25)
    if not smp.samples:
        print('  ERROR: no power samples; is nvidia-smi available?'); sys.exit(1)
    time.sleep(2.0)
    idle = stats(smp.between(0, time.perf_counter()))
    print(f'  idle           mean {idle["mean"]:7.1f} W  (n={idle["n"]})')

    pre_p, dec_p = [], []
    for rep in range(a.repeats):
        # --- prefill window
        pr = [{'prompt_token_ids': [1000 + (i % 5000) for i in range(a.prefill_ctx)]}
              for _ in range(a.batch)]
        torch.cuda.synchronize(); t0 = time.perf_counter()
        llm.generate(pr, SamplingParams(max_tokens=1, min_tokens=1, temperature=0.0, ignore_eos=True))
        torch.cuda.synchronize(); t1 = time.perf_counter()
        pre_p.append((t0, t1))
        time.sleep(0.6)
        # --- decode window
        dr = [{'prompt_token_ids': [1000 + (i % 5000) for i in range(a.decode_ctx)]}
              for _ in range(a.batch)]
        torch.cuda.synchronize(); t2 = time.perf_counter()
        llm.generate(dr, SamplingParams(max_tokens=a.decode_tokens, min_tokens=a.decode_tokens,
                                        temperature=0.0, ignore_eos=True))
        torch.cuda.synchronize(); t3 = time.perf_counter()
        dec_p.append((t2 + (t3-t2)*a.settle, t3))
        time.sleep(0.6)

    pw = [w for t0, t1 in pre_p for w in smp.between(t0, t1)]
    dw = [w for t0, t1 in dec_p for w in smp.between(t0, t1)]
    smp.stop()
    P, D = stats(pw), stats(dw)
    print(f'  PREFILL  B={a.batch} N={a.prefill_ctx:<6} mean {P["mean"]:7.1f} W   p95 {P["p95"]:7.1f}   '
          f'peak {P["peak"]:7.1f}   (n={P["n"]}, sd {P["sd"]:.1f})')
    print(f'  DECODE   B={a.batch} N={a.decode_ctx:<6} mean {D["mean"]:7.1f} W   p95 {D["p95"]:7.1f}   '
          f'peak {D["peak"]:7.1f}   (n={D["n"]}, sd {D["sd"]:.1f})')
    if D['n'] and P['n']:
        print(f'\n  prefill / decode  mean {P["mean"]/D["mean"]:.3f}x   peak {P["peak"]/D["peak"]:.3f}x')
        print(f'  -> prefill runs {"HOTTER" if P["mean"] > D["mean"] else "COOLER"} than decode '
              f'by {abs(P["mean"]-D["mean"]):.1f} W')
    out = dict(model=a.model, batch=a.batch, prefill_ctx=a.prefill_ctx, decode_ctx=a.decode_ctx,
               idle=idle, prefill=P, decode=D,
               ratio_mean=(P['mean']/D['mean']) if D.get('n') else None)
    if a.out: json.dump(out, open(a.out, 'w'), indent=2); print(f'  wrote {a.out}')

if __name__ == '__main__':
    main()
