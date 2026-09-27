#!/usr/bin/env python3
"""R1 (real LLM decode) — predictions written BEFORE measuring, one per prior-work abstraction.

Each predictor is the logical -> physical conversion that tool (or paper) actually implements:
  llmcompass     LLMCompass (ISCA'24) — every operator loads its operands from main memory; no reuse
                 across operators or steps. Bytes are taken from LLMCompass's own operator code
                 (run separately on the GPU host: llmcompass_decode.py), not re-derived here.
  genz           GenZ — static placement, tensors marked 'off' are read off-chip every step (default:
                 weights and KV off-chip). Bytes from GenZ's own operator code (genz_decode.py).
  memexplorer    MemExplorer §2.2 eq. (4): x_remain = (1 - alpha) x with weight storage priority —
                 on-chip capacity C holds min(C, weights) of weights for good (no public code).
  gtsim_l2       GPU-Tile-Sim's L2 as released (include/memory.h): fully-associative LRU, 128-B lines,
                 no persistence controls. On a cyclic decode stream it is simulated here.
  ours_v1 / ours_v2  our models (v1 frozen since H1; v2 with phi from H1, unchanged since H1c).
Byte classes of a decode step come from the model config (weights packed in execution order, the
window covering the first X MiB; KV of context+1 tokens read once per step — the harness's manual engine
writes the new token at position `context` every step; KV append and activations are small).
Grid: baseline; set-aside only (control: must equal baseline); window 127 MiB x S x hitRatio, hitRatio
fine enough to bracket S/127 for every S; the documented recipe window = S, hitRatio 1.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import l2policy_model as V1
import l2policy_model_v2 as V2

MiB = 1 << 20
HF = '/Users/choeseoyeon/code/thirdparty/hf_configs'

def step_bytes(cfg, batch, context):
    H, I, L = cfg['hidden_size'], cfg['intermediate_size'], cfg['num_hidden_layers']
    nh, kvh = cfg['num_attention_heads'], cfg['num_key_value_heads']; hd = H // nh
    per_layer = H * H * 2 + 2 * H * kvh * hd + 3 * H * I + 2 * H          # q,o + k,v + gate,up,down + 2 norms
    align = 128                                                          # 256-B alignment in bf16 elements
    per_layer_al = sum(-(-n // align) * align for n in (H * H, H * kvh * hd, H * kvh * hd, H * H, H * I, H * I, I * H, H, H))
    embed = cfg['vocab_size'] * H
    weights = (L * per_layer_al + -(-H // align) * align + -(-embed // align) * align) * 2
    kv_tok = L * 2 * kvh * hd * 2
    return dict(weights=weights, kv_read=batch * (context + 1) * kv_tok, kv_write=batch * kv_tok,
                act=batch * L * (6 * H + 2 * I) * 2)       # per-layer activation reads/writes, order of magnitude

LEDGER_WEIGHTS = {'SmolLM-135M': 269037824, 'SmolLM-360M': 723650560}   # harness `--mode ledger` on dsil-sy

WORKLOADS = (('SmolLM-135M', 1), ('SmolLM-135M', 8), ('SmolLM-360M', 1))

def grid(model, batch):
    base = dict(model=model, batch=batch, context=512)
    runs = [dict(base, window=0, setaside=0, hitratio=0), dict(base, window=0, setaside=60, hitratio=0)]
    for sa in (12, 24, 36, 48, 60):
        for hr in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0):
            runs.append(dict(base, window=127, setaside=sa, hitratio=hr))
    for sa in (12, 24, 36, 48, 60):
        runs.append(dict(base, window=sa, setaside=sa, hitratio=1.0))
    return runs

def predict(run, C, phi, tool_bytes):
    cfg = json.load(open(os.path.join(HF, run['model'] + '.json')))
    b = step_bytes(cfg, run['batch'], run['context'])
    total_read = b['weights'] + b['kv_read']
    W = min(run['window'] * MiB, b['weights'])
    # our models see the step as a cyclic stream: window (first W bytes of weights) + everything else recurring
    ws_mib = total_read / MiB
    sim = dict(mode='llm', ws=ws_mib, layers=1, window=W / MiB, setaside=run['setaside'], hitratio=run['hitratio'])
    out = {
        'llmcompass': tool_bytes['llmcompass'][run['model'] + f"/B{run['batch']}"],
        'genz': tool_bytes['genz'][run['model'] + f"/B{run['batch']}"],
        'memexplorer': total_read - min(C, b['weights']),
        'gtsim_l2': V1.simulate(dict(sim, window=0, setaside=0, hitratio=0), C, 64 * 1024, knobs=False),
        'ours_v1': V1.simulate(sim, C, 64 * 1024, knobs=True),
        'ours_v2': V2.predict_v2(sim, C, phi),
    }
    return dict(run=run, bytes=b, dram_read_bytes=out)

if __name__ == '__main__':
    tool_bytes = json.load(open(sys.argv[1]))          # {'llmcompass': {...}, 'genz': {...}} from the tool runs
    probe = json.load(open('assets/sweep/gpu_probe_ampere.json'))
    C = int(probe['gpu.l2_cache_bytes'])
    phi = json.load(open('assets/sweep/v2_fit_ampere.json'))['phi']
    for m, w in LEDGER_WEIGHTS.items():
        got = step_bytes(json.load(open(os.path.join(HF, m + '.json'))), 1, 512)['weights']
        assert got == w, (m, got, w)
    runs = []
    for model, batch in WORKLOADS:
        g = grid(model, batch)
        runs += [predict(r, C, phi, tool_bytes) for r in g]
        settings = [dict(window=r['window'], setaside=r['setaside'], hitratio=r['hitratio']) for r in g]
        json.dump(settings, open(f'assets/sweep/r1_settings_{model}_B{batch}.json', 'w'))
    doc = dict(created=time.strftime('%Y-%m-%d %H:%M:%S %Z'), machine=probe['host'], l2_bytes=C, phi=phi,
               tool_bytes=tool_bytes, engine='manual (llm_policy_bench.py), decode at position = context',
               note='R1 real-LLM decode. All predictors frozen before measuring.', runs=runs)
    json.dump(doc, open('assets/sweep/r1_predictions_ampere.json', 'w'), indent=1)
    print(len(runs), 'settings predicted')
