#!/usr/bin/env python3
"""Parse an Accel-Sim (GPGPU-Sim 4.x) log into per-kernel and per-step DRAM bytes, L2 hits/misses and cycles.

GPGPU-Sim prints a statistics block after every kernel. Counters that are cumulative over the simulation
('total dram reads/writes', the L2 breakdown, gpu_tot_sim_cycle) are differenced kernel to kernel; the DRAM
counters count DRAM accesses of dram_atom_size bytes (burst length x bus width = 16 x 2 B = 32 B in the
SM120_RTXPRO5000 config; checked: a cold 1.5 MiB kernel reads 49152 = 1.5 MiB / 32 B).

Usage: asim_parse.py sim.log KERNELS_PER_STEP WARM_STEPS [ATOM_BYTES]  -> one JSON line
"""
import json, re, sys

KEYS = {
    'dram_rd': re.compile(r'^total dram reads = (\d+)'),
    'dram_wr': re.compile(r'^total dram writes = (\d+)'),
    'tot_cycle': re.compile(r'^gpu_tot_sim_cycle = (\d+)'),
    'l2_rd_hit': re.compile(r'^\s*L2_cache_stats_breakdown\[GLOBAL_ACC_R\]\[HIT\] = (\d+)'),
    'l2_rd_miss': re.compile(r'^\s*L2_cache_stats_breakdown\[GLOBAL_ACC_R\]\[MISS\] = (\d+)'),
    'l2_rd_smiss': re.compile(r'^\s*L2_cache_stats_breakdown\[GLOBAL_ACC_R\]\[SECTOR_MISS\] = (\d+)'),
    'l2_rd_hit_res': re.compile(r'^\s*L2_cache_stats_breakdown\[GLOBAL_ACC_R\]\[HIT_RESERVED\] = (\d+)'),
}
NAME = re.compile(r'^kernel_name = (\S+)')

def parse(path):
    ks, cur = [], None
    for line in open(path, errors='replace'):
        m = NAME.match(line)
        if m:
            cur = dict(name=m.group(1)); ks.append(cur); continue
        if cur is None: continue
        for k, rx in KEYS.items():
            m = rx.match(line)
            if m and k not in cur: cur[k] = int(m.group(1))
    return [k for k in ks if 'dram_rd' in k]

def per_kernel(ks):
    """Difference the cumulative counters (checked to be non-decreasing)."""
    out, prev = [], {}
    for k in ks:
        d = dict(name=k['name'])
        for f in KEYS:
            if f in k:
                d[f] = k[f] - prev.get(f, 0); prev[f] = k[f]
        out.append(d)
    return out

if __name__ == '__main__':
    path, kps, warm = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    atom = int(sys.argv[4]) if len(sys.argv) > 4 else 32
    ks = parse(path)
    cum_ok = all(ks[i]['dram_rd'] >= ks[i - 1]['dram_rd'] for i in range(1, len(ks)))
    pk = per_kernel(ks) if cum_ok else ks
    n = len(pk); steps = n // kps
    step = []
    for s in range(steps):
        sl = pk[s * kps:(s + 1) * kps]
        step.append({f: sum(k.get(f, 0) for k in sl) for f in KEYS})
    meas = step[warm:]
    res = dict(log=path, kernels=n, kernels_per_step=kps, steps=steps, warm=warm, cumulative=cum_ok, atom=atom,
               dram_read_per_step=[s['dram_rd'] * atom for s in step],
               dram_write_per_step=[s['dram_wr'] * atom for s in step],
               cycles_per_step=[s['tot_cycle'] for s in step],
               l2_read_hit_per_step=[s['l2_rd_hit'] for s in step],
               l2_read_miss_per_step=[s['l2_rd_miss'] + s['l2_rd_smiss'] for s in step])
    if meas:
        res['dram_read_bytes'] = sum(s['dram_rd'] for s in meas) * atom / len(meas)
        res['dram_write_bytes'] = sum(s['dram_wr'] for s in meas) * atom / len(meas)
        res['cycles'] = sum(s['tot_cycle'] for s in meas) / len(meas)
    print(json.dumps(res))
