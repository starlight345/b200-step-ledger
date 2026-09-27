#!/usr/bin/env python3
"""Per-kernel census of memory instructions in NVBit traces (Accel-Sim tracer v6): which load variants a kernel
issues and how many 32-B sectors each touches — e.g. LDG.E.EF.U16 (ld.global.cs, evict-first) vs LDG.E.U16 or
LDG.E.LTC128B.128 (normal priority). This is the input v3's load classes are read from.

Line format: [cta x y z warp] PC mask dest_num [dests] opcode src_num [srcs] mem_width [addr_format addresses]
imm1 imm2 ...; address formats (trace_parser.cc): 0 = one address per active lane, 1 = base + stride,
2 = base + deltas between successive active lanes. Width is read from the opcode (the parser does the same,
because NVBit can report it wrongly). Two counts per variant: requests = sectors unique per warp instruction summed
over instructions (what the SMs ask of L1/L2; gemvx asks for each weight sector 16 times, one bf16 per lane per
row), and unique_sectors = distinct sectors over the whole kernel (the bytes the variant brings in, x 32 B) —
the load class is read from unique_sectors. Shared-memory and constant-bank instructions are skipped.

Usage: python3 r2_census.py RUN_DIR  -> one JSON line per traced kernel
"""
import glob, json, lzma, os, re, sys
from collections import defaultdict

MASK = re.compile(r'^[0-9a-f]{8}$')
SKIP = ('LDS', 'STS', 'LDSM', 'LDC', 'ULDC', 'LDCU', 'ATOMS', 'LDL', 'STL')

def width(op):
    w = 4
    for t in op.split('.')[1:]:
        if t in ('U8', 'S8'): w = 1
        elif t in ('U16', 'S16'): w = 2
        elif t == '64': w = 8
        elif t == '128': w = 16
    return w

def lanes(mask):
    return [s for s in range(32) if mask >> s & 1]

def census(path):
    name, kid, var = None, None, defaultdict(lambda: [0, 0, set()])   # opcode -> [warp insts, requests, sectors]
    with lzma.open(path, 'rt', errors='replace') as f:
        for line in f:
            if line.startswith('-kernel name = '): name = line.split('=', 1)[1].strip(); continue
            if line.startswith('-kernel id = '): kid = int(line.split('=')[1]); continue
            if not line or line[0] in '-#\n': continue
            t = line.split()
            j = None
            for i, tok in enumerate(t):
                if MASK.match(tok) and i + 1 < len(t) and t[i + 1].isdigit():
                    mask = int(tok, 16); j = i + 2 + int(t[i + 1]); break
            if j is None or j >= len(t): continue
            op = t[j]
            if op.split('.')[0] in SKIP: continue
            k = j + 2 + int(t[j + 1])                                 # mem_width field
            if k >= len(t) or t[k] == '0': continue
            fmt = int(t[k + 1]); act = lanes(mask); w = width(op)
            if fmt == 0:
                addrs = [int(a, 16) for a in t[k + 2:k + 2 + len(act)]]
            elif fmt == 1:
                base, stride = int(t[k + 2], 16), int(t[k + 3])
                addrs = [base + n * stride for n in range(len(act))]
            else:
                base = int(t[k + 2], 16); addrs = [base]
                for dlt in t[k + 3:k + 2 + len(act)]: addrs.append(addrs[-1] + int(dlt))
            sec = set()
            for a in addrs:
                sec.update(range(a // 32, (a + w - 1) // 32 + 1))
            v = var[op]; v[0] += 1; v[1] += len(sec); v[2].update(sec)
    return dict(id=kid, name=name, variants={o: dict(warp_insts=a, requests=b, unique_sectors=len(u))
                                             for o, (a, b, u) in sorted(var.items(), key=lambda x: -len(x[1][2]))})

if __name__ == '__main__':
    run = sys.argv[1]
    for p in sorted(glob.glob(os.path.join(run, 'traces', 'kernel-*.trace.xz')),
                    key=lambda p: int(os.path.basename(p).split('-')[1])):
        print(json.dumps(census(p)), flush=True)
