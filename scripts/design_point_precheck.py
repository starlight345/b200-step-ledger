#!/usr/bin/env python3
"""Pre-check for DESIGN_POINT_3DSRAM.md §6 (2026-09-20).

Replays scenario-lab.html's whole-model placement calculator with the device
team's 2026-09-20 answers plugged in:
  * capacity cases C3/C2/C1 = 278 / 422 / 590 MB per die (320 mm², 1 layer)
  * delivered tier bandwidth as a function of the aggregate read fraction r,
    from the device team's table (read share 1.0 / 0.8 / 0.6 -> 15.0 / 9.4 / 3.8
    TB/s; 16 banks, scheduling efficiency 0.85). Below r=0.6 the table has no
    point; we use 3.8 TB/s as an optimistic bound and flag it.
  * optional power cap  BW <= P_budget / E_bit.

Everything here is a model calculation on structural constants, not a
measurement. Timing is reported as two bounds, exactly like the lab:
serial sum (HBM time + tier time) and overlapped max(compute, HBM, tier).
"""
GB = 1e9; MB = 1e6; MiB = 2**20; HBM_TBPS = 8.0

MODELS = {
 'llama':   dict(name='Llama-3.1-8B', wres=16.1*GB, wstep=15.1*GB, base=4.5556, groups=[('full',32,4096,None)]),   # canon: workload.llama31_8b_weight_read_per_step_GB (lab rounded constant; exact 15.010, effect <=0.03%p)
 'llama2':  dict(name='Llama-2-7B', wres=13.5*GB, wstep=13.2*GB, base=5.3264, groups=[('full',32,16384,None)]),
 'granite': dict(name='granite-4.0-h-tiny', wres=14*GB, wstep=None, base=4.6995, moe=(1.92,64,6,.00472,40),
                 groups=[('full',4,2048,None),('state',36,806400,None)]),
 'gemma':   dict(name='Gemma-3-27B', wres=54.8*GB, wstep=54.8*GB, base=13.3924, groups=[('full',10,8192,None),('sliding',52,8192,1024)]),
 'gptoss':  dict(name='gpt-oss-120b', wres=61*GB, wstep=None, base=6.7203, moe=(3,128,4,.0133,36), groups=[('full',18,2048,None),('sliding',18,2048,128)]),
 'deepseek':dict(name='DeepSeek-V2-Lite', wres=31.4*GB, wstep=None, base=4.6275, moe=(2,64,6,.0176,26), groups=[('full',27,1152,None)]),
}
CASES = {'C3 278': 278*MB, 'C2 422': 422*MB, 'C1 590': 590*MB}
BW_TABLE = [(1.0,15.0),(0.8,9.4),(0.6,3.8)]   # device team, 2026-09-20 (read share, TB/s)

def bw_delivered(r):
    """Piecewise-linear in r on the device team's three points; below 0.6 -> 3.8 (optimistic bound)."""
    if r >= 1.0: return 15.0, False
    for (r1,b1),(r0,b0) in zip(BW_TABLE, BW_TABLE[1:]):
        if r0 <= r <= r1: return b0 + (b1-b0)*(r-r0)/(r1-r0), False
    return 3.8, True   # off-table

def union(E,k,B): return E*(1-(1-k/E)**B)

def objects(m, B, N):
    kv=kvw=state=0
    for t,n,b,w in m['groups']:
        if t=='state': state += B*n*b
        else:
            tok = min(N,w) if w else N
            kv += B*tok*n*b; kvw += B*n*b
    wstep = m['wstep'] if m['wstep'] else (m['moe'][0] + m['moe'][3]*m['moe'][4]*union(m['moe'][1],m['moe'][2],B))*GB
    return {'weight':dict(alloc=m['wres'],read=wstep,write=0),
            'kv':dict(alloc=kv,read=kv,write=kvw),
            'state':dict(alloc=state,read=state,write=state)}

def place(obj, C, policy='auto'):
    for o in obj.values(): o['score'] = (o['read']+o['write'])/o['alloc'] if o['alloc'] else 0
    order = [k for k in obj if obj[k]['alloc']>0]
    tie = {'state':0,'kv':1,'weight':2}
    if policy=='auto': order.sort(key=lambda k:(-obj[k]['score'], tie[k]))
    else: order.sort(key=lambda k:(0 if k==policy else 1, -obj[k]['score']))
    cap = C
    for k in obj: obj[k]['placed']=obj[k]['sr']=obj[k]['sw']=0
    for k in order:
        p = min(obj[k]['alloc'], cap); f = p/obj[k]['alloc'] if obj[k]['alloc'] else 0
        obj[k].update(placed=p, sr=obj[k]['read']*f, sw=obj[k]['write']*f); cap -= p
    return order[0] if order else None

def evaluate(mkey, B, N, C, policy='auto', cap_tbps=None, fabric_tbps=None):
    m = MODELS[mkey]; obj = objects(m,B,N); first = place(obj,C,policy)
    total = sum(o['read']+o['write'] for o in obj.values())
    served = sum(o['sr']+o['sw'] for o in obj.values()); sread = sum(o['sr'] for o in obj.values())
    r = sread/served if served else 1.0
    bw, off = bw_delivered(r)
    if cap_tbps: bw = min(bw, cap_tbps)
    if fabric_tbps: bw = min(bw, fabric_tbps)
    hbm = total - served
    hbm_ms = hbm/(HBM_TBPS*1e12)*1e3; tier_ms = served/(bw*1e12)*1e3; raw = total/(HBM_TBPS*1e12)*1e3
    serial_gain = raw - (hbm_ms+tier_ms)                    # >0 means the tier helps in the serial-sum bound
    compute = max(.02, m['base']-raw); pred = max(compute,hbm_ms,tier_ms); base_pred = max(compute,raw)
    return dict(first=first, r=r, bw=bw, off=off, served_MB=served/MB, hbm_saved_ms=served/(HBM_TBPS*1e12)*1e3,
                tier_ms=tier_ms, serial_gain_ms=serial_gain, overlap_speedup=base_pred/pred, raw_ms=raw, hbm_ms=hbm_ms)

SCEN = [('short  Llama-3.1-8B B=8 N=512','llama',8,512), ('long   Llama-2-7B B=8 N=32768','llama2',8,32768),
        ('state  Granite B=8 N=8192','granite',8,8192), ('state  Granite B=16 N=8192','granite',16,8192),
        ('slide  Gemma-3-27B B=8 N=32768','gemma',8,32768), ('moe    gpt-oss-120b B=16 N=8192','gptoss',16,8192),
        ('mla    DeepSeek-V2-Lite B=8 N=2048','deepseek',8,2048), ('mla    DeepSeek-V2-Lite B=8 N=32768','deepseek',8,32768)]

if __name__ == '__main__':
    print("A. auto policy (score = traffic/resident byte), BW_tier = device-team BW(r), no power cap, fabric = inf")
    print(f"{'scenario':38s} {'case':7s} {'1st':6s} {'r':>5s} {'BW':>6s} {'served':>8s} {'HBMsave':>8s} {'tier':>7s} {'serial':>8s} {'overlap':>7s}")
    for label,mk,B,N in SCEN:
        for ck,C in CASES.items():
            e = evaluate(mk,B,N,C)
            flag = '*' if e['off'] else ' '
            print(f"{label:38s} {ck:7s} {e['first']:6s} {e['r']:5.2f} {e['bw']:5.1f}{flag} {e['served_MB']:7.0f}MB {e['hbm_saved_ms']:7.3f}ms {e['tier_ms']:6.3f}ms {e['serial_gain_ms']:+7.3f}ms {e['overlap_speedup']:6.3f}×")
    print("  * = r below the device table (0.6); 3.8 TB/s used as optimistic bound\n")

    print("B. Granite B=8, C3 278 MB: forced first object (policy) comparison")
    for pol in ('state','weight','kv'):
        e = evaluate('granite',8,8192,CASES['C3 278'],policy=pol)
        print(f"  first={pol:6s} r={e['r']:.2f} BW={e['bw']:.1f}{'*' if e['off'] else ''} served={e['served_MB']:.0f}MB HBM saved={e['hbm_saved_ms']:.3f}ms tier={e['tier_ms']:.3f}ms serial={e['serial_gain_ms']:+.3f}ms overlap={e['overlap_speedup']:.3f}× (HBM time {e['hbm_ms']:.2f} ms)")

    print("\nC. Power cap BW <= P/E_bit (device-team table) applied on top of BW(r); Llama short C1 590 (KV, r~1) and Granite B=8 C3 (state)")
    for P in (10,20,50):
        for E in (0.1,0.5):
            cap = P/E/8  # W / (pJ/bit) -> Tbit/s /8 -> TB/s
            a = evaluate('llama',8,512,CASES['C1 590'],cap_tbps=cap); g = evaluate('granite',8,8192,CASES['C3 278'],cap_tbps=cap)
            print(f"  P={P:2d}W E={E:.1f}pJ cap={cap:5.1f}TB/s | Llama KV: BW={a['bw']:5.1f} serial={a['serial_gain_ms']:+.3f}ms | Granite state: BW={g['bw']:4.1f} serial={g['serial_gain_ms']:+.3f}ms")

    print("\nD. Two-layer C3 (2 x 278 = 556 MB) coverage flips vs one layer")
    for label,mk,B,N in SCEN:
        o = objects(MODELS[mk],B,N); place(o,278*MB); f1 = {k:min(1,278*MB/o[k]['alloc']) for k in o if o[k]['alloc']}
        f2 = {k:min(1,556*MB/o[k]['alloc']) for k in o if o[k]['alloc']}
        k = max(f1, key=lambda k:o[k]['score']); print(f"  {label:38s} 1st={k:6s} alloc={o[k]['alloc']/MB:7.0f}MB  cov 1-layer {f1[k]*100:5.1f}%  2-layer {f2[k]*100:5.1f}%")
