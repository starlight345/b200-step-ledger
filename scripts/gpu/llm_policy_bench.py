#!/usr/bin/env python3
"""Real-LLM decode under CUDA L2 persistence — the workload every prior-work tool claims to model.

  * Weights are packed into ONE contiguous buffer in execution order (layer 0 ... layer N-1, final
    norm, tied embedding / LM head last), so a single access-policy window covers exactly "the first
    X MiB of the weights" and every predictor can be told which bytes that is.
  * StaticCache: the KV cache is preallocated; HF's default cache concatenates (copies) every step,
    which would add traffic no model of decode intends to count.
  * Eager kernels on one stream (no CUDA graphs), so the stream's access-policy window applies to all.

  * Engine 'manual' (default) runs the decode step as exactly the operator list the prior-work tools
    model, with the checkpoint's own HF modules (norms, projections, rotary, MLP, LM head): only the
    attention core is written out — scores = bmm(q grouped per KV head, K), softmax, bmm(p, V) — so
    the KV cache is read ONCE per step over the valid context. HF's own path (engine 'hf') reads the
    whole preallocated StaticCache under a mask and materialises a GQA copy of K and V every layer
    (repeat_kv), traffic no prior tool (or our model) is asked to predict. 'check' verifies the manual
    step against HF's logits.
  * Every measured step is a decode step at the same position (context): it writes K,V of the new token
    at `context` and reads context+1 tokens, so all steps have an identical byte footprint.

Modes
  ledger         print the byte classes of one decode step (no GPU measurement of outcomes)
  check          manual step vs HF forward: logits difference and argmax agreement
  time           warm up, then per-step CUDA-event times
  profile        like time, but brackets PROF steady-state steps with cudaProfilerStart/Stop for
                 `ncu --replay-mode app-range --cache-control none`
  sweep-profile  one model load, one profiler range per policy setting in --settings
  sweep-time     per setting: GPU kernel time per step (sum of kernel durations, torch.profiler/CUPTI,
                 so eager launch gaps on the CPU do not count) and wall time per step
"""
import argparse, ctypes, glob, json, os, sys, time
import torch
from transformers import AutoModelForCausalLM, AutoConfig, StaticCache, DynamicCache
from transformers.models.llama.modeling_llama import apply_rotary_pos_emb

MiB = 1 << 20

def cudart():
    import nvidia.cuda_runtime as ncr
    base = os.path.dirname(ncr.__file__) if getattr(ncr, '__file__', None) else list(ncr.__path__)[0]
    for p in glob.glob(os.path.join(base, 'lib', 'libcudart.so*')):
        try: return ctypes.CDLL(p)
        except OSError: pass
    return ctypes.CDLL('libcudart.so.12')

def pack_weights(model):
    """Move every parameter into one contiguous bf16 buffer, execution order, 256-B aligned."""
    layers = model.model.layers
    order = []
    for layer in layers:
        order += [p for _, p in layer.named_parameters()]
    order += [p for _, p in model.model.norm.named_parameters()]
    seen = {id(p) for p in order}
    tail = [p for p in model.parameters() if id(p) not in seen]      # embedding (tied LM head) last
    order += tail
    align = 256 // 2
    total = sum((p.numel() + align - 1) // align * align for p in order)
    flat = torch.empty(total, dtype=torch.bfloat16, device='cuda')
    off, spans = 0, []
    for p in order:
        n = p.numel(); flat[off:off + n].copy_(p.data.reshape(-1)); p.data = flat[off:off + n].view_as(p)
        spans.append(n * 2); off += (n + align - 1) // align * align
    torch.cuda.synchronize(); torch.cuda.empty_cache()
    return flat, total * 2, spans

def set_policy(rt, stream_ptr, base_ptr, window_b, setaside_b, hitratio):
    rt.cudaDeviceSetLimit(ctypes.c_int(0x06), ctypes.c_size_t(int(setaside_b)))   # cudaLimitPersistingL2CacheSize
    got = ctypes.c_size_t(0); rt.cudaDeviceGetLimit(ctypes.byref(got), ctypes.c_int(0x06))
    buf = (ctypes.c_ubyte * 64)()                                                   # cudaStreamAttrValue (union)
    class Win(ctypes.Structure):
        _fields_ = [('base_ptr', ctypes.c_void_p), ('num_bytes', ctypes.c_size_t), ('hitRatio', ctypes.c_float),
                    ('hitProp', ctypes.c_int), ('missProp', ctypes.c_int)]
    w = Win.from_buffer(buf)
    if window_b > 0:
        w.base_ptr, w.num_bytes, w.hitRatio, w.hitProp, w.missProp = base_ptr, int(window_b), float(hitratio), 2, 1
    rc = rt.cudaStreamSetAttribute(ctypes.c_void_p(stream_ptr), ctypes.c_int(1), ctypes.byref(buf))
    rt.cudaCtxResetPersistingL2Cache()
    return rc, got.value

class ManualDecode:
    """Decode step = the prior tools' operator list, on the checkpoint's own modules."""
    def __init__(self, model, batch, max_len):
        cfg = model.config; self.m = model; self.B = batch
        self.L, self.nh = cfg.num_hidden_layers, cfg.num_attention_heads
        self.kvh = getattr(cfg, 'num_key_value_heads', self.nh)
        self.hd = getattr(cfg, 'head_dim', None) or cfg.hidden_size // self.nh
        self.g = self.nh // self.kvh
        shape = (self.L, batch, self.kvh, max_len, self.hd)
        self.K = torch.zeros(shape, dtype=torch.bfloat16, device='cuda')
        self.V = torch.zeros(shape, dtype=torch.bfloat16, device='cuda')

    def load_prefill(self, cache, n):
        for l in range(self.L):
            lay = cache.layers[l] if hasattr(cache, 'layers') else None
            k = lay.keys if lay is not None else cache.key_cache[l]
            v = lay.values if lay is not None else cache.value_cache[l]
            self.K[l, :, :, :n].copy_(k[:, :, :n]); self.V[l, :, :, :n].copy_(v[:, :, :n])

    def rope(self, P):
        x = torch.zeros(self.B, 1, self.m.config.hidden_size, dtype=torch.bfloat16, device='cuda')
        return self.m.model.rotary_emb(x, torch.full((self.B, 1), P, device='cuda', dtype=torch.long))

    def step(self, tok, P, cs):
        B, kvh, g, hd = self.B, self.kvh, self.g, self.hd
        mm = self.m.model; cos, sin = cs
        x = mm.embed_tokens(tok)                                         # [B,1,H]
        for l, layer in enumerate(mm.layers):
            a = layer.self_attn
            h = layer.input_layernorm(x)
            q = a.q_proj(h).view(B, 1, self.nh, hd).transpose(1, 2)
            k = a.k_proj(h).view(B, 1, kvh, hd).transpose(1, 2)
            v = a.v_proj(h).view(B, 1, kvh, hd).transpose(1, 2)
            q, k = apply_rotary_pos_emb(q, k, cos, sin)
            self.K[l, :, :, P:P + 1].copy_(k); self.V[l, :, :, P:P + 1].copy_(v)
            Kc = self.K[l, :, :, :P + 1].reshape(B * kvh, P + 1, hd)     # views: K, V read once
            Vc = self.V[l, :, :, :P + 1].reshape(B * kvh, P + 1, hd)
            s = torch.bmm(q.reshape(B * kvh, g, hd), Kc.transpose(1, 2)) * a.scaling
            p = torch.softmax(s, dim=-1, dtype=torch.float32).to(torch.bfloat16)
            o = torch.bmm(p, Vc).reshape(B, 1, self.nh * hd)            # head order kv*g + j, as HF
            x = x + a.o_proj(o)
            x = x + layer.mlp(layer.post_attention_layernorm(x))
        return self.m.lm_head(mm.norm(x))                                # [B,1,vocab]

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True); ap.add_argument('--batch', type=int, default=1)
    ap.add_argument('--context', type=int, default=512); ap.add_argument('--mode', default='time')
    ap.add_argument('--window', type=float, default=0); ap.add_argument('--setaside', type=float, default=0)
    ap.add_argument('--hitratio', type=float, default=0); ap.add_argument('--warmup', type=int, default=20)
    ap.add_argument('--iters', type=int, default=60); ap.add_argument('--prof', type=int, default=3)
    ap.add_argument('--settings', default='', help='sweep mode: JSON list of {window,setaside,hitratio}')
    ap.add_argument('--engine', default='manual', choices=('manual', 'hf'))
    ap.add_argument('--weights-cs', action='store_true',
                    help='R3 intervention: decode projections read their weights with ld.global.cs (evict-first, as '
                         'cuBLAS gemvx does at batch 1); see cs_linear.py. Prefill and the HF reference are unchanged')
    ap.add_argument('--no-policy-calls', action='store_true',
                    help='call no persistence API (Accel-Sim tracing: NVBit 1.8 fails in cudaCtxResetPersistingL2Cache); baseline only')
    a = ap.parse_args()
    if a.no_policy_calls and (a.window or a.setaside or a.settings):
        sys.exit('--no-policy-calls runs the baseline only')
    torch.manual_seed(0)
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).cuda().eval()
    cfg = model.config
    flat, wbytes, spans = pack_weights(model)
    if a.weights_cs:
        import cs_linear
        n_cs = cs_linear.patch(model)                 # off until the decode steps start
    L, H = cfg.num_hidden_layers, cfg.hidden_size
    kvh = getattr(cfg, 'num_key_value_heads', cfg.num_attention_heads); hd = getattr(cfg, 'head_dim', H // cfg.num_attention_heads)
    kv_per_token = L * 2 * kvh * hd * 2
    max_len = a.context + a.warmup + a.iters + a.prof + 8
    kv_tokens_read = a.context + 1 if a.engine == 'manual' else max_len
    ledger = dict(model=a.model, batch=a.batch, context=a.context, engine=a.engine, layers=L, hidden=H, kv_heads=kvh,
                  head_dim=hd, weight_bytes=wbytes, kv_bytes_per_token=kv_per_token,
                  kv_read_bytes_step=a.batch * kv_tokens_read * kv_per_token, kv_write_bytes_step=a.batch * kv_per_token,
                  kv_alloc_bytes=a.batch * max_len * kv_per_token, vocab=cfg.vocab_size,
                  lm_head_bytes=cfg.vocab_size * H * 2, tied=bool(getattr(cfg, 'tie_word_embeddings', False)))
    if a.mode == 'ledger':
        print(json.dumps(ledger)); sys.exit(0)

    ids = torch.randint(0, cfg.vocab_size, (a.batch, a.context), device='cuda')
    if a.engine == 'manual':
        eng = ManualDecode(model, a.batch, max_len)
        with torch.no_grad():
            dc = DynamicCache()
            out = model(input_ids=ids, past_key_values=dc, use_cache=True)
            tok = out.logits[:, -1:].argmax(-1)
            eng.load_prefill(dc, a.context); cs = eng.rope(a.context)
            if a.mode == 'check':
                res = []
                for t in range(3):                                  # three real decode steps, P = context + t
                    ref = model(input_ids=tok, past_key_values=dc, use_cache=True).logits[:, -1].float()
                    if a.weights_cs: cs_linear.set_enabled(True)          # reference stays on cuBLAS
                    man = eng.step(tok, a.context + t, eng.rope(a.context + t))[:, -1].float()
                    if a.weights_cs: cs_linear.set_enabled(False)
                    res.append(dict(P=a.context + t, max_abs=float((ref - man).abs().max()),
                                    ref_absmax=float(ref.abs().max()),
                                    cos=float(torch.nn.functional.cosine_similarity(ref, man, dim=-1).min()),
                                    argmax_agree=float((ref.argmax(-1) == man.argmax(-1)).float().mean())))
                    tok = ref.argmax(-1, keepdim=True)
                print(json.dumps(dict(ledger=ledger, check=res))); sys.exit(0)
        del dc; torch.cuda.empty_cache()
    else:
        cache = StaticCache(config=cfg, max_batch_size=a.batch, max_cache_len=max_len, device='cuda', dtype=torch.bfloat16)
        with torch.no_grad():
            out = model(input_ids=ids, past_key_values=cache, use_cache=True,
                        cache_position=torch.arange(a.context, device='cuda'))
            tok = out.logits[:, -1:].argmax(-1)
    if a.weights_cs: cs_linear.set_enabled(True); ledger['weights_cs_modules'] = n_cs
    rt = cudart(); s = torch.cuda.current_stream()
    if a.no_policy_calls: rc, got = None, None
    else: rc, got = set_policy(rt, s.cuda_stream, flat.data_ptr(), min(a.window * MiB, wbytes), a.setaside * MiB, a.hitratio)
    pos = a.context
    def step():
        global pos, tok
        if a.engine == 'manual':                  # same position every step: identical byte footprint
            tok = eng.step(tok, a.context, cs)[:, -1:].argmax(-1); return
        o = model(input_ids=tok, past_key_values=cache, use_cache=True,
                  cache_position=torch.tensor([pos], device='cuda'))
        tok = o.logits[:, -1:].argmax(-1); pos += 1

    def kernel_ms_per_step(n):
        from torch.profiler import profile, ProfilerActivity
        with profile(activities=[ProfilerActivity.CUDA]) as pr:
            for _ in range(n): step()
            torch.cuda.synchronize()
        us = sum(e.device_time_total for e in pr.key_averages() if e.device_type.name == 'CUDA'
                 and not e.key.startswith('cudaProfiler'))
        return us / 1e3 / n
    if a.mode in ('sweep-profile', 'sweep-time'):
        # one model load, many policy settings; each setting is its own profiler range (ncu app-range
        # reports ranges in start order, so range i is setting i)
        settings = json.load(open(a.settings))
        with torch.no_grad():
            for i, st in enumerate(settings):
                rc, got = set_policy(rt, s.cuda_stream, flat.data_ptr(), min(st['window'] * MiB, wbytes),
                                     st['setaside'] * MiB, st['hitratio'])
                for _ in range(a.warmup): step()
                torch.cuda.synchronize()
                rec = dict(i=i, setting=st, policy_rc=rc, setaside_got=got)
                if a.mode == 'sweep-profile':
                    torch.cuda.cudart().cudaProfilerStart()
                    for _ in range(a.prof): step()
                    torch.cuda.synchronize(); torch.cuda.cudart().cudaProfilerStop()
                else:
                    ev = [torch.cuda.Event(enable_timing=True) for _ in range(a.iters + 1)]; ev[0].record()
                    for k in range(a.iters): step(); ev[k + 1].record()
                    torch.cuda.synchronize()
                    ms = sorted(ev[k].elapsed_time(ev[k + 1]) for k in range(a.iters)); rec['ms_median'] = ms[len(ms) // 2]
                    rec['kernel_ms'] = [kernel_ms_per_step(a.prof) for _ in range(3)]
                print('SETTING ' + json.dumps(rec), flush=True)
        set_policy(rt, s.cuda_stream, 0, 0, 0, 0)
        print('LEDGER ' + json.dumps(ledger)); sys.exit(0)
    with torch.no_grad():
        for _ in range(a.warmup): step()
        torch.cuda.synchronize()
        if a.mode == 'profile':
            torch.cuda.cudart().cudaProfilerStart()
            for _ in range(a.prof): step()
            torch.cuda.synchronize(); torch.cuda.cudart().cudaProfilerStop()
            print(json.dumps(dict(ledger=ledger, policy_rc=rc, setaside_got=got, prof_steps=a.prof))); sys.exit(0)
        ev = [torch.cuda.Event(enable_timing=True) for _ in range(a.iters + 1)]
        ev[0].record()
        for i in range(a.iters): step(); ev[i + 1].record()
        torch.cuda.synchronize()
    ms = sorted(ev[i].elapsed_time(ev[i + 1]) for i in range(a.iters))
    if not a.no_policy_calls: set_policy(rt, s.cuda_stream, 0, 0, 0, 0)
    print(json.dumps(dict(ledger=ledger, policy_rc=rc, setaside_got=got, window=a.window, setaside=a.setaside,
                          hitratio=a.hitratio, ms_median=ms[len(ms) // 2], ms_p10=ms[len(ms) // 10], ms_p90=ms[len(ms) * 9 // 10])))
