#!/usr/bin/env python3
"""Capacity x bandwidth sweep for a generic on-package SRAM tier (DESIGN_POINT_3DSRAM.md, 2026-09-20).

Question (from the 2026-09-19 advisor meeting): how much capacity and how much
delivered bandwidth must a 3D SRAM tier have before relieving HBM traffic turns
into step-time benefit, and where does the tier itself become the bottleneck?

Semantics of the tier (no object-aware policy unless stated):
  G1  ideal-capacity protected cache, object-agnostic: a fraction f = min(1, C/WS)
      of every byte of per-step traffic is served by the tier (upper bound for
      any replacement policy).
  G2  LRU on the cyclic per-step access pattern: nothing hits unless C >= WS.
  G3  object-aware ledger (rank by traffic/resident byte) with admission
      (no placement when the tier would be slower than HBM). Enhancement only.
Timing bounds, as in the lab: serial sum (pessimistic) and overlapped
max(compute, HBM, tier) (optimistic). Compute floor comes from measured B200
decode medians (assets/model_evidence.json) where the (B, N) anchor exists,
otherwise the nearest anchor is used and flagged. All numbers are model
calculations on structural constants, not measurements.
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import design_point_precheck as d

GB = 1e9; MB = 1e6; HBM = 8.0
ROOT = os.path.join(os.path.dirname(__file__), '..')
MODELS = dict(d.MODELS)
MODELS['qwen'] = dict(name='Qwen3-8B', wres=16.4*GB, wstep=13.9*GB, base=4.7256, groups=[('full',36,4096,None)])
MODELS['mistral'] = dict(name='Mistral-7B', wres=14.5*GB, wstep=14.2*GB, base=4.5825, groups=[('full',32,4096,None)])
ORDER = ['llama','qwen','mistral','llama2','granite','gemma','gptoss','deepseek']
EVIDENCE_KEY = {'llama':'llama31_8b','qwen':'qwen3_8b','mistral':'mistral_7b','llama2':'llama2_7b',
                'granite':'granite_4h','gemma':'gemma3_27b','gptoss':'gptoss_120b','deepseek':'dsv2_lite'}
C_MB  = [0, 64, 128, 256, 278, 422, 512, 590, 1024, 1180, 2048, 2360, 4096, 8192, 16384]
BW_TB = [1, 2, 4, 5, 8, 10, 15, 17.7, 20, 30, 60]
BATCH = [1, 8, 32, 64]; CTX = [2048, 8192]
DEVICE_POINTS = {'C3': 278, 'C2': 422, 'C1': 590}

def load_anchors():
    ev = json.load(open(os.path.join(ROOT, 'assets/model_evidence.json')))
    out = {}
    for m in ev['models']:
        out[m['key']] = {(r['batch'], r['context_tokens']): r['step_ms'] for r in m['decode_grid']}
    return out
ANCHORS = load_anchors()

def anchor(mk, B, N):
    g = ANCHORS[EVIDENCE_KEY[mk]]
    if (B, N) in g: return g[(B, N)], 'measured'
    if (B, 2048) in g: return g[(B, 2048)], 'fallback_context'
    return g[(8, 2048)], 'fallback_batch'

def workload(mk, B, N):
    m = MODELS[mk]; obj = d.objects(m, B, N)
    ws = sum(o['alloc'] for o in obj.values())
    T = sum(o['read']+o['write'] for o in obj.values())
    return obj, ws, T

def evaluate(mk, B, N, C, BW, sem):
    m = MODELS[mk]; obj, ws, T = workload(mk, B, N)
    if sem == 'G1':
        f = min(1.0, C/ws) if C > 0 else 0.0; served = f*T; first = 'all'
    elif sem == 'G2':
        served = T if (C > 0 and C >= ws) else 0.0; first = 'all' if served else None
    else:  # G3 ledger + admission
        if C > 0 and BW > HBM:
            first = d.place(obj, C); served = sum(o['sr']+o['sw'] for o in obj.values())
        else:
            first, served = 'no-admit', 0.0
    hbm_ms = (T-served)/(HBM*1e12)*1e3; tier_ms = served/(BW*1e12)*1e3 if served else 0.0
    raw = T/(HBM*1e12)*1e3
    base_ms, flag = anchor(mk, B, N)
    compute = max(.02, base_ms-raw)
    pred = max(compute, hbm_ms, tier_ms); base_pred = max(compute, raw)
    bott = 'compute' if compute >= max(hbm_ms, tier_ms) else ('HBM' if hbm_ms >= tier_ms else 'SRAM')
    return dict(model=m['name'], key=mk, B=B, N=N, WS_GB=ws/GB, traffic_GB=T/GB, semantics=sem, C_MB=C/MB, BW_TBs=BW,
                served_frac=served/T, hbm_ms=hbm_ms, tier_ms=tier_ms, serial_ms=hbm_ms+tier_ms, serial_change_pct=(hbm_ms+tier_ms-raw)/raw*100,
                overlap_ms=pred, speedup_overlap=base_pred/pred, bottleneck=bott, compute_floor_ms=compute, anchor=flag, first=first)


# ---------------------------------------------------------------------------
# Calibrated timing: per-model two-parameter regression on measured anchors
#   step_ms = t0 + traffic_GB / BW_eff   (memory.html already uses 1.58 ms + Q/6.51 TB/s for Llama)
# With a tier: step_ms = t0 + (T - served)/BW_eff + served/BW_tier.  The tier helps only if BW_tier > BW_eff.
# ---------------------------------------------------------------------------
def calibrate(mk):
    pts = []
    for (B, N), ms in ANCHORS[EVIDENCE_KEY[mk]].items():
        obj, ws, T = workload(mk, B, N); pts.append((T/GB, ms))
    xs = [x for x, _ in pts]; ys = [y for _, y in pts]; n = len(pts)
    mx = sum(xs)/n; my = sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs); sxy = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    slope = sxy/sxx if sxx > 0 else 0.0
    flag = 'fit'
    if slope <= 0:
        slope = 1.0/HBM; flag = 'slope_fallback_peak'
    t0 = my - slope*mx
    if t0 < 0:
        t0 = 0.0; slope = sum(y/x for x, y in zip(xs, ys))/n; flag = 't0_clamped'
    resid = [y - (t0 + slope*x) for x, y in zip(xs, ys)]
    rmse = (sum(r*r for r in resid)/n)**0.5
    return dict(t0_ms=t0, BW_eff_TBs=1.0/slope, n=n, rmse_ms=rmse, max_abs_err_pct=max(abs(r)/y*100 for r, y in zip(resid, ys)), flag=flag)
CAL = {mk: calibrate(mk) for mk in ORDER}

def evaluate_cal(mk, B, N, C, BW, sem='G1'):
    """Calibrated step time with a generic tier (G1) or ledger tier (G3)."""
    obj, ws, T = workload(mk, B, N); c = CAL[mk]
    if sem == 'G1':
        f = min(1.0, C/ws) if C > 0 else 0.0; served = f*T
    elif sem == 'G2':
        served = T if (C > 0 and C >= ws) else 0.0
    else:
        if C > 0 and BW > c['BW_eff_TBs']:
            d.place(obj, C); served = sum(o['sr']+o['sw'] for o in obj.values())
        else: served = 0.0
    base = c['t0_ms'] + T/GB/c['BW_eff_TBs']
    step = c['t0_ms'] + (T-served)/GB/c['BW_eff_TBs'] + (served/GB/BW if served else 0.0)
    return dict(step_ms_cal=step, base_ms_cal=base, speedup_cal=base/step, served_frac=served/T,
                tier_slower=(BW < c['BW_eff_TBs']), t0_ms=c['t0_ms'], BW_eff_TBs=c['BW_eff_TBs'], WS_GB=ws/GB, traffic_GB=T/GB)

def sweep():
    rows = []
    for mk in ORDER:
        for B in BATCH:
            for N in CTX:
                for C in C_MB:
                    for BW in BW_TB:
                        for sem in ('G1','G2','G3'):
                            if C == 0 and BW != BW_TB[0]: continue   # baseline row once
                            e = evaluate(mk, B, N, C*MB, BW, sem); ec = evaluate_cal(mk, B, N, C*MB, BW, sem)
                            e.update(step_ms_cal=ec['step_ms_cal'], base_ms_cal=ec['base_ms_cal'], speedup_cal=ec['speedup_cal'], tier_slower_than_hbm_eff=ec['tier_slower'])
                            rows.append(e)
    return rows

def requirements():
    """Per workload: working set, traffic, capacity for 10/25/50% capture (G1), bandwidth boundary where the tier
    becomes the bottleneck in the overlapped bound at C = 590 MB and at C = WS, and the device points' outcome."""
    out = []
    for mk in ORDER:
        for B in BATCH:
            for N in CTX:
                obj, ws, T = workload(mk, B, N); base_ms, flag = anchor(mk, B, N)
                raw = T/(HBM*1e12)*1e3; compute = max(.02, base_ms-raw)
                def bw_boundary(C):
                    f = min(1.0, C/ws); return (f*T/1e12*1e3) / max(compute, (1-f)*raw) if f > 0 else 0.0
                r = dict(model=MODELS[mk]['name'], B=B, N=N, WS_GB=ws/GB, traffic_GB=T/GB, anchor=flag,
                         hbm_time_ms=raw, compute_floor_ms=compute, memory_bound=(raw > compute),
                         C_for_10pct_MB=0.10*ws/MB, C_for_25pct_MB=0.25*ws/MB, C_for_50pct_MB=0.50*ws/MB,
                         BW_min_pessimistic_TBs=HBM, BW_bottleneck_at_590MB_TBs=bw_boundary(590*MB), BW_bottleneck_at_WS_TBs=bw_boundary(ws))
                for name, C in DEVICE_POINTS.items():
                    e = evaluate(mk, B, N, C*MB, 15.0, 'G1')
                    r[f'{name}_G1_speedup_overlap@15TBs'] = e['speedup_overlap']; r[f'{name}_G1_serial_change_pct@15TBs'] = e['serial_change_pct']
                out.append(r)
    return out

if __name__ == '__main__':
    print('Per-model calibration on measured B200 anchors: step_ms = t0 + traffic/BW_eff')
    for mk in ORDER:
        c = CAL[mk]; print(f"  {MODELS[mk]['name']:18s} t0 {c['t0_ms']:5.2f} ms  BW_eff {c['BW_eff_TBs']:5.2f} TB/s  n={c['n']}  rmse {c['rmse_ms']:.2f} ms  max err {c['max_abs_err_pct']:.1f}%  {c['flag']}")
    rows = sweep()
    os.makedirs(os.path.join(ROOT, 'assets/sweep'), exist_ok=True)
    p = os.path.join(ROOT, 'assets/sweep/sram_capacity_bandwidth_sweep.csv')
    with open(p, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    req = requirements()
    q = os.path.join(ROOT, 'assets/sweep/sram_requirements.csv')
    with open(q, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(req[0].keys())); w.writeheader(); w.writerows(req)
    print(f'wrote {len(rows)} sweep rows -> {os.path.relpath(p, ROOT)}; {len(req)} requirement rows -> {os.path.relpath(q, ROOT)}')
    # headline summary
    heads = [('llama',8,2048),('granite',32,8192),('granite',64,8192),('deepseek',8,2048),('gptoss',8,8192),('llama2',8,2048)]
    print('\nCALIBRATED model, G1 generic tier: speedup by capacity at BW = 5 / 8 / 15 / 60 TB/s (x = tier slower than HBM_eff)')
    for mk,B,N in heads:
        obj, ws, T = workload(mk,B,N); c = CAL[mk]
        print(f"\n{MODELS[mk]['name']} B={B} N={N}: WS {ws/GB:.1f} GB, traffic {T/GB:.1f} GB/step, base {c['t0_ms']+T/GB/c['BW_eff_TBs']:.2f} ms (t0 {c['t0_ms']:.2f} + {T/GB/c['BW_eff_TBs']:.2f}), max speedup at C=WS, BW=inf: {(c['t0_ms']+T/GB/c['BW_eff_TBs'])/c['t0_ms'] if c['t0_ms']>0 else float('inf'):.2f}x")
        print(f"  {'C [MB]':>8s} " + ' '.join(f"{'BW '+str(bw):>9s}" for bw in (5,8,15,60)))
        for C in (128, 278, 590, 1180, 2360, 4096, 8192, 16384):
            cells = []
            for bw in (5,8,15,60):
                ec = evaluate_cal(mk,B,N,C*MB,bw,'G1'); cells.append(f"{ec['speedup_cal']:.3f}{'x' if ec['tier_slower'] else ' '}")
            print(f"  {C:8d} " + ' '.join(f"{cc:>9s}" for cc in cells))
    print('\nG1 generic tier: overlapped speedup (and serial change %) by capacity at BW = 8 / 15 / 60 TB/s')
    for mk,B,N in heads:
        obj, ws, T = workload(mk,B,N); base_ms, flag = anchor(mk,B,N)
        print(f"\n{MODELS[mk]['name']} B={B} N={N}: WS {ws/GB:.1f} GB, traffic {T/GB:.1f} GB/step, HBM time {T/8e12*1e3:.2f} ms, compute floor {max(.02, base_ms-T/8e12*1e3):.2f} ms ({flag})")
        print(f"  {'C [MB]':>8s} " + ' '.join(f"{'BW '+str(bw):>18s}" for bw in (8,15,60)))
        for C in (128, 278, 590, 1180, 2360, 4096, 16384):
            cells = []
            for bw in (8,15,60):
                e = evaluate(mk,B,N,C*MB,bw,'G1'); cells.append(f"{e['speedup_overlap']:.3f}x {e['serial_change_pct']:+6.1f}% {e['bottleneck'][:3]}")
            print(f"  {C:8d} " + ' '.join(f"{c:>18s}" for c in cells))
    print('\nBandwidth boundary (overlapped bound) where the tier becomes the bottleneck, TB/s:')
    for r in req:
        if (r['model'], r['B'], r['N']) in [(MODELS[m]['name'],b,n) for m,b,n in heads]:
            print(f"  {r['model']:18s} B={r['B']:<3d} N={r['N']:<5d} WS {r['WS_GB']:5.1f} GB | at 590 MB: {r['BW_bottleneck_at_590MB_TBs']:5.2f} | at full WS: {r['BW_bottleneck_at_WS_TBs']:5.1f} | C for 10/25/50%: {r['C_for_10pct_MB']:,.0f} / {r['C_for_25pct_MB']:,.0f} / {r['C_for_50pct_MB']:,.0f} MB")
