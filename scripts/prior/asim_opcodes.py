#!/usr/bin/env python3
"""Opcode census of NVBit traces (Accel-Sim tracer, trace version 6), run on dsil-sy.

  1. Which base opcodes (first dotted component) are NOT in Accel-Sim's Hopper opcode table — the ones the
     sm_120 traces need an explicit mapping for before the trace-driven frontend accepts them.
  2. Memory-instruction variants with their full modifiers (e.g. LDG.E.EL.128 = evict-last hint), weighted by
     warp-instruction count: which L2 eviction-priority hints the traced kernels themselves carry.
Line format: <cta x y z> <warp> ... PC mask dest_num [dests] opcode ...; the opcode follows the 8-hex-digit
active mask, the destination count and that many destination registers.

Usage: python3 asim_opcodes.py HOPPER_OPCODE_H RUN_DIR [RUN_DIR ...]   -> one JSON line per run
"""
import glob, json, lzma, os, re, sys
from collections import Counter

MASK = re.compile(r'^[0-9a-f]{8}$')
MEM = re.compile(r'^(LD|ST|RED|ATOM|UBLKCP|UTMA|LDGSTS|CCTL)')

def table(path):
    return set(re.findall(r'\{"([A-Z0-9_]+)",\s*OpcodeChar', open(path).read()))

def opcodes(path):
    c = Counter()
    with lzma.open(path, 'rt', errors='replace') as f:
        for line in f:
            if not line or line[0] in '-#\n': continue
            t = line.split()
            for i, tok in enumerate(t):
                if MASK.match(tok) and i + 1 < len(t) and t[i + 1].isdigit():
                    j = i + 2 + int(t[i + 1])
                    if j < len(t): c[t[j]] += 1
                    break
    return c

if __name__ == '__main__':
    known = table(sys.argv[1])
    for run in sys.argv[2:]:
        full = Counter()
        for p in sorted(glob.glob(os.path.join(run, 'traces', 'kernel-*.trace.xz'))):
            full.update(opcodes(p))
        base = Counter()
        for k, v in full.items(): base[k.split('.')[0]] += v
        print(json.dumps(dict(run=os.path.basename(run.rstrip('/')), warp_insts=sum(full.values()),
                              unknown={k: v for k, v in base.most_common() if k not in known},
                              memory={k: v for k, v in full.most_common() if MEM.match(k)})))
