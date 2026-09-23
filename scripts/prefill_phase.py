#!/usr/bin/env python3
"""M-3: put prefill into the ledger, and re-derive the tier's duty cycle for it.

Why this blocks the ECTC thermal argument. The duty cycle in ectc_thermal_model.py
(4.80% at the C2 2-layer point) is a DECODE number. If prefill ran the tier harder,
prefill would be the thermal design point and the envelope in the ECTC figures would
be drawn at the wrong place. Nobody had checked: the replay ledger contains zero
prefill events (verified: grep -c prefill -> 0 on both input ledgers).

What comes out. The tier moves the SAME bytes in prefill as in one decode step --
the resident weight set, read once per forward pass -- but spreads them over a window
that is at minimum an order of magnitude longer, because prefill is compute-bound over
B*N tokens while a decode step produces B. So

    duty_prefill / duty_decode = t_decode / t_prefill

and that ratio needs no FLOPS spec to bound: even at an unphysical 100% MFU on the
full BF16 peak, t_prefill for 16,384 tokens exceeds the measured 4.5556 ms decode step
by more than 10x. Decode is the thermal worst case. The prefill exposure is on the
OTHER side of the ledger -- the logic baseline the tier sits on.

Grades: weight/KV bytes structural [public-derived, canon]. Activation and KV-reread
        traffic are IMPLEMENTATION-dependent and are swept, not asserted.
        Decode step time and package power are [measured] (assets/model_evidence.json).
        Prefill time is [derived] from FLOPs with an explicit swept efficiency.
"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(__file__))
from canon_3dsram import get

ROOT = os.path.join(os.path.dirname(__file__), '..')
OUT  = os.path.join(ROOT, 'assets', 'experiments', '3dsram_closure_20260921', 'inputs')
GB   = 1e9

# ---- structure, all derivable from canon --------------------------------------
KV_PER_TOK = get('workload.llama31_8b_kv_bytes_per_token')        # 131072 B
EMB_BYTES  = get('workload.llama31_8b_embedding_bytes')           # 128256 x 4096 x 2
W_STEP     = get('workload.llama31_8b_weight_read_per_step_GB')*GB
VOCAB, DTYPE = 128256, 2
D_MODEL    = EMB_BYTES // (VOCAB*DTYPE)                           # 4096
LAYERS     = 32
LAYER_W    = 13.9592*GB                                           # ledger, 32 layer_weight reads
LM_HEAD    = EMB_BYTES                                            # untied, same size
B, N       = 8, 2048
TOK        = B*N                                                  # 16,384 tokens in the prefill

# ---- measured anchors ---------------------------------------------------------
EV = json.load(open(os.path.join(ROOT, 'assets', 'model_evidence.json')))
GRID = {(r['batch'], r['context_tokens']): r
        for m in EV['models'] if m['key'] == 'llama31_8b' for r in m['decode_grid']}
T_DECODE_MS = GRID[(B, N)]['step_ms']          # 4.5556 [measured]
P_DECODE_W  = GRID[(B, N)]['power_w']          # 698.7  [measured]

# ---- prefill traffic ----------------------------------------------------------
def prefill_bytes(kv_reread=1.0, act_roundtrips=2):
    """One prefill forward pass over TOK tokens. kv_reread: how many times attention
    re-reads the KV it just wrote (0 = fully fused in-kernel, 1 = read once).
    act_roundtrips: d_model-sized HBM round trips of the residual stream per layer."""
    act = LAYERS * act_roundtrips * TOK * D_MODEL * DTYPE
    return {
        'layer_weight_read': LAYER_W,                       # once per forward pass
        'lm_head_read':      LM_HEAD,                       # weight matrix, last token only
        'embedding_gather':  TOK * D_MODEL * DTYPE,
        'kv_write':          TOK * KV_PER_TOK,
        'kv_read':           TOK * KV_PER_TOK * kv_reread,
        'activation':        act,
    }

def build_events(kv_reread=1.0, act_roundtrips=2):
    """Prefill events in layer-interleaved emission order (the nominal; order is swept in
    prefill_policy_replay.py because first-fill policies are order-sensitive)."""
    b = prefill_bytes(kv_reread, act_roundtrips)
    ev, per_layer_w = [], LAYER_W/LAYERS
    def E(layer, obj, op, by, sq, ra):
        return dict(kind='event', model_tag='llama', batch=B, context=N, phase='prefill',
                    step=-1, layer=layer, object=obj, op=op, bytes=round(by),
                    source_quality=sq, routing_assumption=ra)
    for L in range(LAYERS):
        ev.append(E(L, 'layer_weight', 'read', per_layer_w,
                    'enumerated_runtime_parameters', 'dense_or_no_routed_weight_detected'))
        ev.append(E(L, 'full_kv', 'write', b['kv_write']/LAYERS, 'structural',
                    'prefill_writes_whole_kv_cache'))
        ev.append(E(L, 'full_kv', 'read', b['kv_read']/LAYERS, 'implementation_dependent',
                    f'kv_reread={kv_reread}_swept'))
        if act_roundtrips:
            ev.append(E(L, 'activation', 'write', b['activation']/LAYERS/2,
                        'implementation_dependent', f'act_roundtrips={act_roundtrips}_swept'))
            ev.append(E(L, 'activation', 'read', b['activation']/LAYERS/2,
                        'implementation_dependent', f'act_roundtrips={act_roundtrips}_swept'))
    ev.append(E(LAYERS, 'lm_head', 'read', b['lm_head_read'],
                'enumerated_runtime_parameters', 'last_token_only'))
    ev.append(E(0, 'embedding_gather', 'read', b['embedding_gather'], 'structural', 'dense_gather'))
    return ev

def act_roundtrips_bounds():
    """How many d_model-sized HBM round trips the residual stream really makes per layer.
    LOWER bound 2: the layer boundary forces the hidden state to be materialised once
      (one write, one read) -- no amount of fusion removes a layer boundary.
    UPPER bound: every GEMM output is materialised, because none of them fit on chip at
      T = 16,384 tokens. Per layer that is QKV out (d + 2*d_kv), attention out (d),
      gate+up out (2*d_ff) and down out (d), each written once and read once.
    Both are expressed in units of T*d_model*2 B so they share the act_roundtrips axis."""
    d_kv = 8*128                       # 8 KV heads x 128
    d_ff = 14336                       # Llama-3.1-8B SwiGLU intermediate
    per_layer_units = ((D_MODEL + 2*d_kv) + D_MODEL + 2*d_ff + D_MODEL)/D_MODEL
    return 2.0, 2*per_layer_units      # x2 for write+read

def flops():
    gemm = 2 * (LAYER_W/DTYPE) * TOK                        # 2 * params * tokens
    attn = LAYERS * 2 * B * N**2 * D_MODEL                  # causal QK^T + AV, per layer x layers
    head = 2 * (LM_HEAD/DTYPE) * B                          # logits for the last token only
    return gemm + attn + head, gemm, attn

if __name__ == '__main__':
    print(f'Llama-3.1-8B prefill, B={B} N={N} -> {TOK:,} tokens.  d_model={D_MODEL}, layers={LAYERS}\n')
    print('=== 1. traffic composition, with the two implementation axes swept ===')
    print(f"{'kv_reread':>10} {'act_rt':>7} | {'weight':>8} {'kv_w':>7} {'kv_r':>7} {'act':>7} "
          f"{'total':>8} | {'read':>8} {'write':>7} {'r':>6}")
    rows = []
    for kvr in (0.0, 1.0):
        for art in (0, 2, 4):
            b = prefill_bytes(kvr, art)
            w = b['kv_write'] + b['activation']/2
            rd = b['layer_weight_read']+b['lm_head_read']+b['embedding_gather']+b['kv_read']+b['activation']/2
            tot = rd + w
            rows.append((kvr, art, rd, w, tot))
            print(f"{kvr:>10.0f} {art:>7} | {(b['layer_weight_read']+b['lm_head_read'])/GB:>7.2f}G "
                  f"{b['kv_write']/GB:>6.2f}G {b['kv_read']/GB:>6.2f}G {b['activation']/GB:>6.2f}G "
                  f"{tot/GB:>7.2f}G | {rd/GB:>7.2f}G {w/GB:>6.2f}G {rd/tot:>6.3f}")
    print('\n  decode, one step, for comparison: read 17.157 G, write 0.001 G, r = 0.99994 [trace replay]')

    print('\n=== 2. prefill duration, and the duty ratio that decides the design point ===')
    F, gemm, attn = flops()
    print(f'  FLOPs {F:.3e}  (GEMM {gemm/F*100:.1f}%, attention {attn/F*100:.1f}%)')
    import ectc_thermal_model as M
    C_DP = M.capacity_GB(800.0, 2)
    DUTY_DECODE = M.duty(C_DP)
    TIER_BYTES = M.f_red(C_DP)*M.D_STEP
    print(f'  tier serves {TIER_BYTES:.2f} GB in BOTH phases (resident weight, read once per forward')
    print(f'  pass; capacity {C_DP:.2f} GB is all weight under admission), so the duty ratio below')
    print(f'  is exactly the window-length ratio -- no FLOPS spec is needed to sign it.')
    print(f"\n{'achieved':>22} {'t_prefill':>11} {'t_dec/t_pre':>12} {'duty_prefill':>13} {'verdict':>22}")
    for pf, lab in ((4.5e15,'BF16 peak, 100% MFU'), (2.25e15,'BF16 dense peak'),
                    (1.35e15,'60% MFU'), (0.9e15,'40% MFU')):
        t_ms = F/pf*1e3
        ratio = T_DECODE_MS/t_ms
        dp = DUTY_DECODE*ratio
        v = 'decode is worst case' if dp < DUTY_DECODE else 'PREFILL WORSE -- redo'
        print(f'{lab:>22} {t_ms:>8.1f} ms {ratio:>12.4f} {dp*100:>12.3f}% {v:>22}')
    print(f'\n  decode duty for reference: {DUTY_DECODE*100:.2f}%  (tier serves the same '
          f'resident bytes in both; only the window length differs)')

    print('\n=== 3. tier share and tier-side read mix ===')
    b_nom = prefill_bytes(1.0, 2); tot_nom = sum(b_nom.values())
    print(f'  tier share of prefill traffic: {TIER_BYTES/ (tot_nom/GB) *100:5.1f}%  '
          f'(vs {M.f_red(C_DP)*100:.1f}% of a decode step)')
    print(f'  tier-side read share r = 1.000 in BOTH phases: under weight-only admission the tier')
    print(f'  takes no KV writes and no activations. The r shift M-3 warned about (0.99994 -> 0.69-0.89)')
    print(f'  lands on the HBM side, not the tier, so the device BW(r) input is unchanged at r = 1.')

    print('\n=== 4. what prefill DOES change: the baseline the tier sits on ===')
    print(f'  measured package power, decode B={B} N={N}: {P_DECODE_W:.1f} W [measured]')
    print(f'  prefill is compute-bound, so it runs nearer TDP -- unmeasured, and this is the')
    print(f'  real prefill exposure: the tier\'s ~1-3 W rides a hotter junction, not a busier tier.')

    # ---- emit the prefill ledger -------------------------------------------
    ev = build_events()
    path = os.path.join(OUT, 'llama-b8-l2048-events-prefill.jsonl')
    with open(path, 'w') as fh:
        for e in ev: fh.write(json.dumps(e)+'\n')
    tot = sum(e['bytes'] for e in ev)
    print(f'\nwrote {len(ev)} prefill events, {tot/GB:.3f} GB total -> {os.path.relpath(path, ROOT)}')
    print('  nominal axes kv_reread=1.0, act_roundtrips=2; both carried as implementation_dependent.')
