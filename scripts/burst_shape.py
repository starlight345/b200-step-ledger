#!/usr/bin/env python3
"""Does the tier's heat arrive as one 217 us block? The time structure inside a decode step.

Every thermal number in the ECTC case so far (sota_comparators, hotspot_rerun, the MAPDL and
AEDT decks) feeds the tier ONE block per step: burst = f_red D / B_R = 216.7 us at 38 W/die,
then 4.3 ms off. That is the ledger's arithmetic, not a decode step. The tier holds weights
(admission: weight only), a decode step streams weights layer by layer, and attention (KV
from HBM), small kernels and launch gaps sit in between. Which weights the tier holds sets
where its 216.7 us of work lands inside the 4.515 ms step:

  S0  block        one contiguous block (every model so far)
  S1  LIP head     the Gate-1 replay's policy. LIP inserts at the LRU end, so it keeps the
                   first weight bytes it admitted: layers 0..9 in stream order. Each of those
                   layers reads its four matrices at B_R, with HBM attention and gaps between
  S1e tail         the same filled from the end of the step: lm_head (one 55 us read) and the
                   last layers -- the densest contiguous placement
  S2  interleaved  the same ~9.4 layers spread evenly over the 32
  S3  by matrix    every layer's down projection (3.76 GB), then O projections to fill: one
                   short read per layer
  S4  page slice   27.4% of every weight matrix, pages interleaved with HBM: the tier is read
                   alongside HBM through the whole weight stream, at 2.4 TB/s

Same bytes, same energy per step, same 4.515 ms period, so the average power -- and with it the
static-average answer -- is the same for all of them; only the time structure moves. The
step's fixed time t0 = 1.852 ms is split three ways: one host gap (GPU idle between steps),
1.5 us per kernel plus a host gap, or spread evenly over the kernels. Each schedule is solved
exactly (periodic steady state, mode by mode: sota_comparators.Modal), checked against a
0.25 us backward-Euler run, and the published practices are applied to the same schedule.

  python3 scripts/burst_shape.py        # tables + assets/sweep/burst_shape.json
"""
import os, sys, math, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_stack_solver as TS
import ectc_thermal_model as M
import hb_stack_check as HB
import sota_comparators as SC

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets', 'sweep', 'burst_shape.json')

PERIOD, DUTY = TS.PERIOD, TS.DUTY
TP = DUTY*PERIOD                             # 216.72 us
T0 = 1.852e-3                                # s, regression intercept of the step [Gate 3]
B_HBM, B_R = M.BW_HBM*1e12, M.B_R*1e12       # B/s
E_BYTE = 0.5e-12*8                           # J/B at the 0.5 pJ/bit example
P_BURST = M.p_burst_W(0.5)/2                 # 38 W per die at B_R
TIER_BYTES = TP*B_R                          # 4.118 GB = f_red x D_step, the bytes behind the burst
GAP = 1.5e-6                                 # s per kernel, CUDA-graph launch + tail [assumption]

# Llama-3.1-8B decode, B = 8, context 2,048, bf16 (the ledger's design point)
L = 32
QKV = (4096 + 2*1024)*4096*2
O = 4096*4096*2
GU = 2*14336*4096*2
DN = 4096*14336*2
KV = 8*2048*2*1024*2                         # K and V, 8 KV heads x 128, per layer
LM = 128256*4096*2
W_ALL = L*(QKV + O + GU + DN) + LM           # 15.009 GB (canon W_READ 15.010)

def kernels():
    """The step's kernels in execution order: (name, layer, weight bytes, other HBM bytes)."""
    ks = [('embed', -1, 0, 0)]
    for l in range(L):
        ks += [('norm', l, 0, 0), ('qkv', l, QKV, 0), ('rope', l, 0, 0), ('attn', l, 0, KV),
               ('o', l, O, 0), ('norm2', l, 0, 0), ('gate_up', l, GU, 0), ('act', l, 0, 0),
               ('down', l, DN, 0)]
    return ks + [('final_norm', L, 0, 0), ('lm_head', L, LM, 0), ('sample', L, 0, 0)]

def place(policy):
    """Tier-resident bytes of each kernel's weights."""
    ks = kernels(); tb = [0.0]*len(ks)
    wk = [i for i, k in enumerate(ks) if k[2] > 0]
    def fill(order):
        left = TIER_BYTES
        for i in order:
            take = min(ks[i][2], left); tb[i] = take; left -= take
            if left <= 0: return
    if policy == 'S1':
        fill(wk)
    elif policy == 'S1e':
        fill(wk[::-1])
    elif policy == 'S2':
        n = math.ceil(TIER_BYTES/(QKV + O + GU + DN))
        layers = [int((i + 0.5)*L/n) for i in range(n)]
        fill([i for l in layers for i in wk if ks[i][1] == l])
    elif policy == 'S3':
        fill([i for i in wk if ks[i][0] == 'down'] + [i for i in wk if ks[i][0] == 'o'])
    elif policy == 'S4':
        for i in wk: tb[i] = ks[i][2]*TIER_BYTES/W_ALL
    else:
        raise ValueError(policy)
    return tb

def schedule(policy, t0_split='mixed'):
    """Tier power over one step as [(duration s, W per die)], summing to PERIOD. A kernel with
    tier and HBM bytes reads both at once and lasts as long as the slower of the two."""
    if policy == 'S0':
        return [(TP, P_BURST), (PERIOD - TP, 0.0)]
    ks = kernels(); tb = place(policy)
    durs, pw = [], []
    for (name, l, w, other), t in zip(ks, tb):
        d = max(t/B_R, (w - t + other)/B_HBM)
        durs.append(d); pw.append(t*E_BYTE/d/2 if d > 0 else 0.0)
    busy, n = sum(durs), len(ks)
    g = {'host': 0.0, 'mixed': GAP, 'kernel': (PERIOD - busy)/n}[t0_split]
    host = PERIOD - busy - n*g
    assert host > -1e-12, 'the kernels do not fit in the step'
    segs = [(host, 0.0)] if host > 1e-12 else []
    for d, p in zip(durs, pw):
        if d > 0: segs.append((d, p))
        if g > 0: segs.append((g, 0.0))
    merged = []
    for d, p in segs:
        if merged and merged[-1][1] == p: merged[-1] = (merged[-1][0] + d, p)
        else: merged.append((d, p))
    return merged

TRACE = os.path.join(HERE, '..', 'assets', 'sweep', 'decode_timeline', 'summary.json')

def schedule_measured(policy='S1', mode='graph', trace=TRACE):
    """The same placement on a MEASURED kernel sequence: one Llama-3.1-8B B=8 decode step captured
    under nsys (gpu/decode_timeline.py, RTX PRO 5000, HF modules in a CUDA graph). Its 7 weight
    GEMMs per layer (q k v o gate up down) and lm_head are re-timed at B_R / B_HBM, its two
    attention matmuls per layer at B_HBM (half the layer's KV each); everything else -- norms,
    rotary, softmax, copies, split-K reductions and the 0.42 us launch gaps -- keeps its measured
    proportions and is scaled so the step lasts PERIOD with no host gap. HF launches ~35 small
    kernels per layer where vLLM's fused path launches ~6, so this is the spread-out end."""
    import json
    st = json.load(open(trace))[mode]['step']
    W = [QKV*4//6, QKV//6, QKV//6, O, GU//2, GU//2, DN]        # q k v o gate up down, bytes
    wi = [i for i, k in enumerate(st) if k['cls'] == 'weight']
    assert len(wi) == 7*L + 1, len(wi)
    wbytes = {i: (W[n % 7] if n < 7*L else LM) for n, i in enumerate(wi)}
    left = TIER_BYTES; tb = {}
    order = wi if policy == 'S1' else wi[::-1] if policy == 'S1e' else None
    if order is None: raise ValueError(policy)
    for i in order:
        tb[i] = min(wbytes[i], left); left -= tb[i]
    fixed, rest = [], 0.0                                 # (duration, W) for streaming kernels
    for n, k in enumerate(st):
        if k['cls'] == 'weight':
            t, w = tb.get(n, 0.0), wbytes[n]
            d = max(t/B_R, (w - t)/B_HBM); fixed.append((n, d, t*E_BYTE/d/2 if d > 0 else 0.0))
        elif k['cls'] == 'attn':
            fixed.append((n, KV/2/B_HBM, 0.0))
    gaps = [st[n]['start_us'] - st[n-1]['start_us'] - st[n-1]['dur_us'] for n in range(1, len(st))]
    other = sum(k['dur_us'] for k in st if k['cls'] == 'other')*1e-6 + sum(gaps)*1e-6
    s = (PERIOD - sum(d for _, d, _ in fixed))/other
    assert s > 0, 'streaming alone overruns the step'
    fx = {n: (d, q) for n, d, q in fixed}
    segs = []
    for n, k in enumerate(st):
        if n > 0: segs.append((gaps[n-1]*1e-6*s, 0.0))
        segs.append(fx[n] if n in fx else (k['dur_us']*1e-6*s, 0.0))
    merged = []
    for d, q in segs:
        if d <= 0: continue
        if merged and merged[-1][1] == q: merged[-1] = (merged[-1][0] + d, q)
        else: merged.append((d, q))
    return merged, s

def spread(n, window):
    """n equal sub-bursts (total on-time TP at P_BURST), evenly spaced over `window`."""
    on, pitch = TP/n, window/n
    segs = [(on, P_BURST), (pitch - on, 0.0)]*n if pitch > on else [(TP, P_BURST)]
    return segs + [(PERIOD - window, 0.0)] if PERIOD > window else segs

def check_energy(segs):
    e = sum(d*q for d, q in segs); t = sum(d for d, _ in segs)
    assert abs(t/PERIOD - 1) < 1e-9 and abs(e/(TP*P_BURST) - 1) < 1e-6, (t, e)

def periodic_peak(mod, segs, n_sub=6):
    """Largest tier temperature (K) over one period of the periodic steady state, exact per mode:
    each segment is integrated in closed form, sampled n_sub times inside and at its end."""
    lam, w = mod.lam, mod.w
    F = np.zeros_like(lam)
    for d, q in segs:
        F = F*np.exp(-lam*d) + w/lam*(-np.expm1(-lam*d))*q
    y = F/(-np.expm1(-lam*sum(d for d, _ in segs)))
    best = (mod.phi @ y).max()
    for d, q in segs:
        if q > 0:
            s = np.linspace(d/n_sub, d, n_sub)[:, None]
            ys = y*np.exp(-lam*s) + w/lam*(-np.expm1(-lam*s))*q
            best = max(best, (ys @ mod.phi.T).max())
        y = y*np.exp(-lam*d) + w/lam*(-np.expm1(-lam*d))*q
    return best, F, y

def energy_fn(segs):
    t = np.concatenate([[0.0], np.cumsum([d for d, _ in segs])])
    e = np.concatenate([[0.0], np.cumsum([d*q for d, q in segs])])
    def E(x):
        m, r = divmod(x, t[-1])
        return m*e[-1] + np.interp(r, t, e)
    return E

def trace_peak(mod, segs, window, n_phase=8):
    """The practice's view: a power trace of window means (a HotSpot ptrace row, a CoMeT epoch),
    integrated exactly inside each window from the average-power steady state; the answer is
    the largest window-end value over the second half of a 40-period run, worst alignment."""
    E = energy_fn(segs); lam, w = mod.lam, mod.w
    n = max(200, int(math.ceil(40*PERIOD/window)))
    dec, gain = np.exp(-lam*window), w/lam*(-np.expm1(-lam*window))
    best = 0.0
    for ph in np.arange(n_phase)*min(window, PERIOD)/n_phase:
        a = ph + np.arange(n + 1)*window
        q = np.diff(np.array([E(x) for x in a]))/window
        y = w/lam*(E(PERIOD)/PERIOD)
        for m in range(n):
            y = y*dec + gain*q[m]
            if m >= n//2: best = max(best, (mod.phi @ y).max())
    return best

def stepped_check(layers, mod, segs, dt=0.25e-6):
    """Backward Euler at dt through two periods from the exact periodic state: independent of
    the modal sums, it must land on the same peak."""
    t_edges = np.concatenate([[0.0], np.cumsum([d for d, _ in segs])])
    qs = np.array([q for _, q in segs] + [0.0])
    fn = lambda t: qs[np.searchsorted(t_edges, t % PERIOD, side='right') - 1]
    _, _, y0 = periodic_peak(mod, segs)
    fast = SC.Fast(layers, TS.DIE_AREA_M2, dt)
    T0_cells = mod.shapes @ y0
    tt, Tt, _ = fast.run(fn, 2*PERIOD, T0=T0_cells)
    return Tt.max()

STACKS = [('V-Cache F2B 6 um', lambda: HB.vcache_stack('F2B'), 'SI'),
          ('BEOL tier', lambda: TS.build_stack(n_tiers=2), 'IGZO'),
          ('hybrid-bond F2F 50 um', lambda: HB.hb_stack('F2F', 50.0), 'SI')]
POLICIES = ['S0', 'S1', 'S1e', 'S2', 'S3', 'S4']
LABEL = {'S0': 'one block (all models so far)', 'S1': 'LIP head: layers 0-9 (Gate-1 replay)',
         'S1e': 'tail: lm_head + last layers', 'S2': '~9.4 layers spread over 32',
         'S3': 'down proj. of every layer + O', 'S4': 'page slice of every matrix'}
WINDOWS = (200e-6, 1e-3, 10e-3)

def cap(pf):
    return M.bw_cap_TBs(20.0, 0.5, pf)

def main():
    res = {'design': dict(period_s=PERIOD, duty=DUTY, burst_s=TP, P_burst_W_die=P_BURST,
                          tier_bytes=TIER_BYTES, t0_s=T0, gap_s=GAP, B_R=B_R, B_HBM=B_HBM),
           'stacks': {}}
    for sname, mk, dev in STACKS:
        HB.use_device(getattr(HB, dev))
        lay = mk(); mod = SC.Modal(lay, TS.DIE_AREA_M2)
        R = mod.R; ref = R*P_BURST
        s0 = mod.square_pss()
        pk0 = periodic_peak(mod, schedule('S0'))[0]/ref
        print(f'\n=== {sname}: R {R*1e3:.3f} mK/W per die; one-block check: this solver {pk0:.5f}, '
              f'Modal.square_pss {s0:.5f} ({(pk0/s0 - 1)*100:+.3f}%)')
        st = {'R_K_per_W': R, 'S0_check': [pk0, s0], 'schedules': {}, 'spread': {}}
        print(f"{'schedule':>38} {'t0':>6} {'P_max W':>8} {'tier on':>8} {'span':>7} {'exact pf':>9} "
              f"{'TB/s':>6} {'s-avg':>6} {'s-peak':>7} {'200us':>6} {'1ms':>6} {'10ms':>6}")
        for pol in POLICIES:
            for split in (('host', 'mixed', 'kernel') if pol != 'S0' else ('-',)):
                segs = schedule(pol, split if split != '-' else 'mixed'); check_energy(segs)
                pf = periodic_peak(mod, segs)[0]/ref
                on = [(sum(d for d, _ in segs[:i]), d) for i, (d, q) in enumerate(segs) if q > 0]
                span = on[-1][0] + on[-1][1] - on[0][0]
                pmax = max(q for _, q in segs)
                row = dict(exact=pf, static_avg=DUTY, static_peak=1.0, schedule_max_W=pmax,
                           on_time_s=sum(d for _, d in on), span_s=span, n_segments=len(segs))
                for wdw in WINDOWS:
                    row[f'trace_{wdw*1e6:.0f}us'] = trace_peak(mod, segs, wdw)/ref
                st['schedules'][f'{pol}/{split}'] = row
                print(f"{LABEL[pol]:>38} {split:>6} {pmax:>8.1f} {row['on_time_s']*1e6:>6.0f}us "
                      f"{span*1e3:>5.2f}ms {pf:>9.4f} {cap(pf):>6.1f} "
                      f"{pf/DUTY:>5.2f}x {pf:>6.2f}x " +
                      ' '.join(f"{pf/row[f'trace_{wdw*1e6:.0f}us']:>5.2f}x" for wdw in WINDOWS))
        if os.path.exists(TRACE):
            segs, s = schedule_measured('S1'); check_energy(segs)
            pf = periodic_peak(mod, segs)[0]/ref
            st['schedules']['S1/measured-trace'] = dict(exact=pf, nonstreaming_scale=s, n_segments=len(segs))
            print(f"{'LIP head on the MEASURED kernel sequence':>38} {'trace':>6} {P_BURST:>8.1f} {'':>8} {'':>7} "
                  f"{pf:>9.4f} {cap(pf):>6.1f} {pf/DUTY:>5.2f}x {pf:>6.2f}x   (HF modules, non-streaming x{s:.2f})")
        # independent check of the multi-segment solver on the realistic schedule
        segs = schedule('S1', 'mixed')
        pk_m = periodic_peak(mod, segs)[0]; pk_s = stepped_check(lay, mod, segs)
        st['S1_mixed_stepped_check'] = [pk_m/ref, pk_s/ref]
        print(f'  check S1/mixed: exact {pk_m/ref:.5f}, backward Euler 0.25 us {pk_s/ref:.5f} '
              f'({(pk_s/pk_m - 1)*100:+.2f}%)')
        # the general picture: n sub-bursts spread over a window
        for n in (1, 2, 4, 8, 16, 32, 64):
            for wdw in (0.5e-3, 1e-3, 2e-3, 2.7e-3, PERIOD):
                if n == 1 and wdw > 0.5e-3: continue
                segs = spread(n, wdw); check_energy(segs)
                st['spread'][f'{n}/{wdw*1e6:.0f}us'] = periodic_peak(mod, segs)[0]/ref
        res['stacks'][sname] = st
    json.dump(res, open(OUT, 'w'), indent=1)
    print(f'\nwrote {os.path.relpath(OUT)}')
    print('columns s-avg / s-peak / 200us / 1ms / 10ms: that practice\'s TB/s over the exact TB/s for the'
          ' same schedule (>1 = the practice is optimistic, <1 = pessimistic).')
    v = res['stacks']['V-Cache F2B 6 um']['spread']
    print('\nV-Cache F2B, exact peak fraction for n equal sub-bursts spread over a window:')
    print(f"{'n':>4} " + ' '.join(f'{w:>9}' for w in ('0.5 ms', '1 ms', '2 ms', '2.7 ms', '4.515 ms')))
    for n in (1, 2, 4, 8, 16, 32, 64):
        cells = [v.get(f'{n}/{w:.0f}us') for w in (500, 1000, 2000, 2700, PERIOD*1e6)]
        print(f'{n:>4} ' + ' '.join(f'{c:>9.4f}' if c is not None else f"{'':>9}" for c in cells))

if __name__ == '__main__':
    main()
