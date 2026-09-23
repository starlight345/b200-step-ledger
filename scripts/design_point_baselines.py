#!/usr/bin/env python3
"""Baseline comparison for DESIGN_POINT_3DSRAM.md §6-C (2026-09-20).

Compares, on the lab's whole-model calculator with the device team's BW(r):
  A. baseline placement policies (weight-first, KV-first, state-first) vs the
     ledger policy (rank by traffic/resident byte, admit only if gain > 0);
  B. where the tier's own gain becomes large (workload x tier size);
  C. the same-silicon alternative to C1 (128 mm² of lower Si as Si N5 SRAM).

Model calculation only. Timing anchors are the B=8, N=2048 nb1 medians, so the
overlapped speedups at larger batches ignore compute scaling and are optimistic.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import design_point_precheck as d
MB = 1e6; HBM = 8.0

def run(mk, B, N, C, policy='auto', fixed=None):
    m = d.MODELS[mk]; obj = d.objects(m, B, N)
    if C > 0: first = d.place(obj, C, policy)
    else:
        first = None
        for o in obj.values(): o['sr'] = o['sw'] = o['placed'] = 0
    total = sum(o['read']+o['write'] for o in obj.values()); served = sum(o['sr']+o['sw'] for o in obj.values())
    sread = sum(o['sr'] for o in obj.values()); r = sread/served if served else 1.0
    bw = fixed if fixed else d.bw_delivered(r)[0]
    hbm = total-served; hbm_ms = hbm/(HBM*1e12)*1e3; tier_ms = served/(bw*1e12)*1e3; raw = total/(HBM*1e12)*1e3
    compute = max(.02, m['base']-raw); pred = max(compute, hbm_ms, tier_ms); base = max(compute, raw)
    return dict(first=first, share=served/total*100, serial=(raw-(hbm_ms+tier_ms))/raw*100, overlap=base/pred, r=r, bw=bw)

TIERS = [('C3 1die', 278), ('C1 1die', 590), ('C1 2die', 1180), ('C1 2die 2layer', 2360)]
GRID = [('Granite', 'granite', [(8,8192),(32,8192),(64,8192),(128,8192),(128,2048)]),
        ('Llama-3.1-8B', 'llama', [(8,512),(32,512),(64,2048),(128,2048)]),
        ('DeepSeek-V2-Lite', 'deepseek', [(8,2048),(32,2048),(64,4096),(128,4096)]),
        ('gpt-oss-120b', 'gptoss', [(16,8192),(64,8192),(128,8192)]),
        ('Llama-2-7B MHA', 'llama2', [(8,2048),(32,2048)])]

if __name__ == '__main__':
    print("A. baseline policies vs ledger, C3 278 MB, BW(r) coupled; serial-sum % saving (negative = loss)")
    print(f"{'workload':34s} {'weight-1st':>10s} {'kv-1st':>8s} {'state-1st':>10s} {'ledger':>8s} {'picks':>9s}")
    for label, mk, B, N in d.SCEN:
        row = [run(mk, B, N, 278*MB, policy=p)['serial'] for p in ('weight','kv','state')]
        best = max(row); picks = ['weight','kv','state'][row.index(best)] if best > 0 else 'no-admit'
        print(f"{label:34s} {row[0]:9.2f}% {row[1]:7.2f}% {row[2]:9.2f}% {max(0,best):7.2f}% {picks:>9s}")
    print("\nB. tier's own gain: % of step HBM traffic served / overlapped speedup / first object (ledger, BW(r))")
    print(f"{'workload':30s} " + ' '.join(f"{t[0]:>17s}" for t in TIERS))
    for name, mk, pts in GRID:
        for B, N in pts:
            cells = []
            for tn, C in TIERS:
                e = run(mk, B, N, C*MB); cells.append(f"{e['share']:5.1f}% {e['overlap']:5.3f}× {e['first'][:2]}")
            print(f"{name+' B='+str(B)+' N='+str(N):30s} " + ' '.join(f"{c:>17s}" for c in cells))
    print("\nC. same-silicon baseline for C1: 128 mm² lower Si as Si N5 SRAM (1 Mb = 0.0327 mm², usable 0.836)")
    mb = 128/0.0327
    print(f"   {mb:,.0f} Mb = {mb*0.125:.0f} MB raw = {mb*0.125*0.836:.0f} MB usable; C1 tier 590 MB -> {590/(mb*0.125*0.836):.2f}× more than spending the Si directly")
    print("   C3 uses 0 Si: on a reticle-limited die the Si baseline adds 0 MB.")
