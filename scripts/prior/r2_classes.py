#!/usr/bin/env python3
"""R2 load classes from SASS, fixed before measuring: which bytes of a decode step each load variant brings in.

For every kernel of layer 0 and of the tail (r2_list.sh: kernels.json + census.jsonl), the distinct 32-B sectors
per load variant are matched against the operand sizes the step must read: per layer q, k, v, o, gate, up, down
(bf16) and the K and V cache (batch x kv_heads x (context + 1) x head_dim), in the tail the LM head (tied
embedding). A variant is evict-first when its opcode carries .EF (ld.global.cs); every other global load
(LDG.E, LDG.E.LTC128B, LD.E, LDGSTS ...) is normal priority. The operand is class E if the sectors that read it are
evict-first, N otherwise.

The matmul kernels read their operands in execution order q, k, v, then QK (K cache) and PV (V cache), o, gate,
up, down; the listing gives that order and the census gives each kernel's bytes, so the mapping is checked by
size, not assumed (a kernel whose bytes match no operand is reported).

Usage: python3 r2_classes.py WORKLOAD_DIR MODEL BATCH CONTEXT   (WORKLOAD_DIR = asim/list/r2_* copied locally)
       -> JSON: per operand {bytes, kernel, evict_first_sectors, normal_sectors, class}
"""
import json, os, sys

HF = '/Users/choeseoyeon/code/thirdparty/hf_configs'
LOADS = ('LDG', 'LD', 'LDGSTS', 'UBLKCP', 'UTMALDG')

def operands(cfg, batch, context):
    H, I, L = cfg['hidden_size'], cfg['intermediate_size'], cfg['num_hidden_layers']
    nh, kvh = cfg['num_attention_heads'], cfg['num_key_value_heads']; hd = H // nh
    kv = batch * kvh * (context + 1) * hd * 2
    layer = [('q', H * H * 2), ('k', H * kvh * hd * 2), ('v', H * kvh * hd * 2), ('K', kv), ('V', kv),
             ('o', H * H * 2), ('gate', H * I * 2), ('up', H * I * 2), ('down', I * H * 2)]
    return layer, [('lm_head', cfg['vocab_size'] * H * 2)]

def split(variants):
    ef = sum(v['unique_sectors'] for o, v in variants.items() if o.split('.')[0] in LOADS and '.EF' in o)
    nm = sum(v['unique_sectors'] for o, v in variants.items() if o.split('.')[0] in LOADS and '.EF' not in o)
    return ef, nm

def main(d, model, batch, context):
    cfg = json.load(open(os.path.join(HF, model + '.json')))
    kj = json.load(open(os.path.join(d, 'kernels.json')))
    cen = {c['id']: c for c in map(json.loads, open(os.path.join(d, 'census.jsonl')))}
    first = kj['step_first_id']; s, P = kj['prefix'], kj['per_layer']
    layer_ids = list(range(first + s, first + s + P))
    tail_ids = list(range(first + s + kj['layers'] * P, first + kj['K']))
    layer_ops, tail_ops = operands(cfg, batch, context)
    out, unmatched = {}, []
    for ids, ops in ((layer_ids, layer_ops), (tail_ids, tail_ops)):
        big = []
        for i in ids:
            c = cen.get(i)
            if c is None: continue
            ef, nm = split(c['variants'])
            big.append((i, c['name'], ef, nm))
        # the operand reads: kernels whose load sectors reach 90 % of an operand's size, in order
        need = list(ops)
        for i, name, ef, nm in big:
            if not need: break
            op, nb = need[0]
            sec = nb / 32
            if ef + nm >= 0.9 * sec:
                # the operand's own sectors: the larger variant group is the operand stream (the other one holds
                # the activation vector / the partner operand, orders of magnitude smaller for weights)
                cls = 'E' if ef >= 0.9 * sec and ef >= nm else 'N'
                out[op] = dict(bytes=nb, kernel_id=i, kernel=name[:90], evict_first_sectors=ef, normal_sectors=nm,
                               operand_sectors=int(sec), **{'class': cls})
                need.pop(0)
        unmatched += [op for op, _ in need]
    print(json.dumps(dict(workload=f'{model}/B{batch}/c{context}', operands=out, unmatched=unmatched), indent=1))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
