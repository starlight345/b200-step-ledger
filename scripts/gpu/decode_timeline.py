#!/usr/bin/env python3
"""Measured kernel timeline of a Llama-3.1-8B decode step (B = 8, context 2,048), for burst_shape.

burst_shape.py builds the tier's schedule from byte counts with two numbers nobody measured: the
gap between kernels (1.5 us, assumed) and how the step's fixed time t0 = 1.852 ms splits between
those gaps and one host gap. This runs the decode step under nsys and reports both, plus the time
of the kernels that stream no weights (norms, rotary, softmax, residual adds, argmax).

The step is llm_policy_bench.ManualDecode (the checkpoint's own HF modules, attention written out,
the same position every step so every step has the same footprint), imported read-only. Modes:
  graph   the step captured once as a CUDA graph and replayed back to back -- how vLLM and TensorRT-LLM
          run decode; nsys --cuda-graph-trace=node reports its kernels
  eager   plain launches, for reference (its gaps are the CPU's, not the GPU's)
Each mode runs WARM steps, then MEAS steps inside cudaProfilerStart/Stop with one NVTX range per step.
The GPU is an RTX PRO 5000 Blackwell, not a B200: weight-streaming kernels scale with bandwidth, so
the numbers that transfer are the kernel sequence, the per-kernel gap in graph replay and the time of
the non-streaming kernels. Run only when the GPU is otherwise idle (decode_timeline.sh waits for it).

  nsys profile -t cuda,nvtx --cuda-graph-trace=node --capture-range=cudaProfilerApi \
      -o tl_graph python decode_timeline.py --mode graph
"""
import argparse, os, sys, json
import torch
sys.path.insert(0, os.path.expanduser('~/l2probe'))
from transformers import AutoModelForCausalLM, DynamicCache
from llm_policy_bench import ManualDecode

ap = argparse.ArgumentParser()
ap.add_argument('--model', default='NousResearch/Meta-Llama-3.1-8B')
ap.add_argument('--batch', type=int, default=8); ap.add_argument('--context', type=int, default=2048)
ap.add_argument('--mode', default='graph', choices=('graph', 'eager'))
ap.add_argument('--warm', type=int, default=20); ap.add_argument('--meas', type=int, default=10)
a = ap.parse_args()

torch.manual_seed(0)
model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).cuda().eval()
cfg = model.config
eng = ManualDecode(model, a.batch, a.context + 8)
ids = torch.randint(0, cfg.vocab_size, (a.batch, a.context), device='cuda')
with torch.no_grad():
    dc = DynamicCache()
    out = model(input_ids=ids, past_key_values=dc, use_cache=True, logits_to_keep=1)
    tok = out.logits[:, -1:].argmax(-1)
    eng.load_prefill(dc, a.context); cs = eng.rope(a.context)
del dc, out; torch.cuda.empty_cache()

tok_static = tok.clone()
def body():
    nxt = eng.step(tok_static, a.context, cs)[:, -1:].argmax(-1)
    tok_static.copy_(nxt)

with torch.no_grad():
    if a.mode == 'graph':
        s = torch.cuda.Stream(); s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(3): body()                       # warm-up on a side stream before capture
        torch.cuda.current_stream().wait_stream(s); torch.cuda.synchronize()
        g = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g): body()
        run = g.replay
    else:
        run = body
    for _ in range(a.warm): run()
    torch.cuda.synchronize()
    ev = [torch.cuda.Event(enable_timing=True) for _ in range(a.meas + 1)]
    torch.cuda.cudart().cudaProfilerStart()
    ev[0].record()
    for i in range(a.meas):
        torch.cuda.nvtx.range_push(f'step{i}'); run(); torch.cuda.nvtx.range_pop(); ev[i + 1].record()
    torch.cuda.synchronize(); torch.cuda.cudart().cudaProfilerStop()
ms = sorted(ev[i].elapsed_time(ev[i + 1]) for i in range(a.meas))
print('TIMELINE ' + json.dumps(dict(model=a.model, batch=a.batch, context=a.context, mode=a.mode,
                                    step_ms_median=ms[len(ms)//2], step_ms=ms,
                                    gpu=torch.cuda.get_device_name())), flush=True)
