#!/usr/bin/env python3
"""How many nodes does a reduced thermal model of this stack actually need?

The CFP subcommittee we are submitting to names model order reduction explicitly, and we
already have one result in that direction: a single-node lumped RC is 4.16x optimistic on
this stack's periodic peak. That is a statement about ONE reduced model. This turns it
into a curve -- error against model order -- so the answer is "use at least N nodes, put
them here", not "the lumped model is wrong".

The experiment holds everything fixed except the mesh. Same solver, same boundary
conditions, same power waveform, same time step: only the number of control volumes and
where they are placed changes. `thermal_stack_solver.discretise` is swapped for an
explicit allocation, so the numerics under test are byte-for-byte the verified ones.

Metric is theta = T_tier_peak / P_burst [K/W] at periodic steady state, because that is
the quantity the bandwidth cap divides by. peak_frac would hide error: it normalises by
R_th computed on the same mesh, so a coarse mesh's errors partly cancel.
"""
import os, sys, csv
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_stack_solver as TS

N_PERIODS, DT = 12, 5e-6
Q_TIER, AREA = 20.0, TS.DIE_AREA_M2

_alloc = None
_orig_discretise = TS.discretise

def _mesh(layers, dx_target=None, max_cells=None):
    """Explicit allocation: `_alloc[i]` control volumes inside layer i, uniform within."""
    if _alloc is None:
        return _orig_discretise(layers, dx_target, max_cells)
    z, k, rc, tag = [], [], [], []
    for (name, t), cnt in zip(layers, _alloc):
        dz = t/cnt
        kk, rho, cp = TS.MAT[name]
        z += [dz]*cnt; k += [kk]*cnt; rc += [rho*cp]*cnt; tag += [name]*cnt
    return np.array(z), np.array(k), np.array(rc), tag
TS.discretise = _mesh

def allocate(layers, N):
    """Spread N nodes over the layers in proportion to t/sqrt(alpha), the transient
    penetration scale -- a layer the heat pulse barely enters does not need resolving."""
    w = np.array([t/np.sqrt(TS.MAT[n][0]/(TS.MAT[n][1]*TS.MAT[n][2])) for n, t in layers])
    w = w/w.sum()
    n = np.maximum(1, np.floor(w*N).astype(int))
    while n.sum() < N:                      # hand the leftovers to the hungriest layer
        n[np.argmax(w/n)] += 1
    while n.sum() > N and (n > 1).any():
        cand = np.where(n > 1)[0]
        n[cand[np.argmin((w/n)[cand])]] -= 1
    return n

def theta(layers, alloc=None):
    """K/W at periodic steady state for a given node allocation (None = verified mesh)."""
    global _alloc
    _alloc = alloc
    tt, Tt, _ = TS.solve(layers, 0.0, Q_TIER, AREA, N_PERIODS*TS.PERIOD, DT,
                         TS.DUTY, TS.PERIOD, T_sink=0.0, record_every=1)
    _alloc = None
    last = tt >= (N_PERIODS-1)*TS.PERIOD
    return Tt[last].max()/Q_TIER

def _pss(R, tau):
    """Periodic steady state of a single pole under a duty-cycled square wave."""
    d, P = TS.DUTY, TS.PERIOD
    a, b = np.exp(-d*P/tau), np.exp(-(1-d)*P/tau)
    return R*(1-a)/(1-a*b)

def single_node(layers):
    """Two ways to build the one-node model, because the choice of tau is not obvious.

    FITTED   hand the lumped model the time constant and resistance measured from the real
             stack. This is the charitable version and the one the paper's 4.16x quotes:
             the model is given the right answer for tau and still misses the peak.
    NAIVE    build it from the geometry the way a screening spreadsheet would -- series
             conduction resistance, total heat capacity. No knowledge of the stack's
             internal response at all.
    """
    # tier_tau's second return is the steady-state tier RISE in K (periodic_peak_frac
    # divides by it to get a dimensionless fraction), so convert to K/W before use.
    tau_f, dT_ss = TS.tier_tau(layers, AREA, Q_TIER)
    R_f = dT_ss/Q_TIER
    R_n = sum(t/(TS.MAT[n][0]*AREA) for n, t in layers)
    C_n = sum(t*AREA*TS.MAT[n][1]*TS.MAT[n][2] for n, t in layers)
    return (_pss(R_f, tau_f), tau_f), (_pss(R_n, R_n*C_n), R_n*C_n)

if __name__ == '__main__':
    layers = TS.build_stack()
    nL = len(layers)
    ref = theta(layers)                      # verified graded mesh
    ref_n = len(_orig_discretise(layers, 0.5e-6, 80)[0])
    print(f'reference: verified mesh, {ref_n} nodes, theta = {ref:.5f} K/W\n')

    (th_f, tau_f), (th_n, tau_n) = single_node(layers)
    print(f'N = 1  lumped, tau FITTED to the stack   theta = {th_f:.5f} K/W  '
          f'({ref/th_f:.2f}x optimistic, tau = {tau_f*1e3:.2f} ms)')
    print(f'N = 1  lumped, tau from geometry (naive) theta = {th_n:.5f} K/W  '
          f'({ref/th_n:.2f}x optimistic, tau = {tau_n*1e3:.2f} ms)\n')
    th1 = th_f

    print(f"{'N':>5} {'theta [K/W]':>13} {'error':>9}   node allocation")
    rows = [dict(N=1, nodes='lumped, tau fitted', theta_K_W=round(th_f, 6),
                 rel_error=round(abs(th_f-ref)/ref, 6)),
            dict(N=1, nodes='lumped, tau naive', theta_K_W=round(th_n, 6),
                 rel_error=round(abs(th_n-ref)/ref, 6))]
    orders = [nL, 10, 12, 16, 20, 24, 32, 40, 56, 80, 120]
    for N in orders:
        a = allocate(layers, N)
        th = theta(layers, a)
        err = abs(th-ref)/ref
        rows.append(dict(N=int(a.sum()), nodes='+'.join(map(str, a)),
                         theta_K_W=round(th, 6), rel_error=round(err, 6)))
        print(f'{a.sum():>5d} {th:>13.5f} {err*100:>8.2f}%   {"+".join(map(str,a))}')

    body = [r for r in rows if not r['nodes'].startswith('lumped')]
    def first_under(tol):
        ok = [r for r in body if r['rel_error'] <= tol]
        return min(ok, key=lambda r: r['N']) if ok else None
    print()
    for tol in (0.05, 0.02, 0.01):
        r = first_under(tol)
        if r: print(f'  within {tol*100:>4.0f}%  at N = {r["N"]:>3d} nodes   ({r["nodes"]})')
        else: print(f'  within {tol*100:>4.0f}%  not reached below N = {max(b["N"] for b in body)}')

    r5 = first_under(0.05)
    n8 = next(r for r in body if r['N'] == nL)
    print(f'\n  The one-node model is {ref/th_f:.2f}x optimistic even when tau is handed to it,')
    print(f'  and {ref/th_n:.2f}x when built from geometry. But the cure is not resolution:')
    print(f'  keeping the {nL} physical layers as {nL} separate nodes already lands at '
          f'{n8["rel_error"]*100:.0f}%,')
    if r5:
        print(f'  and {r5["N"]} nodes reach 5%. What the one-node model gets wrong is TOPOLOGY --')
        print(f'  it merges a 50 nm tier with 500 um of silicon, so the burst energy is spread')
        print(f'  over the whole stack heat capacity, while the real peak is set by the thin')
        print(f'  BEOL right beside the tier. (Heat does reach the substrate within a step --')
        print(f'  the Si diffusion length over {TS.PERIOD*1e3:.3f} ms is ~0.55 mm -- so the error is')
        print(f'  not that the substrate is unreachable, it is that it is lumped with the tier.)')
        print(f'\n  Practical statement: a reduced model of this stack needs ~{r5["N"]} nodes, and')
        print(f'  the binding requirement is that the tier and the substrate stay separate.')

    out = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sweep', 'model_order.csv')
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f'\nwrote {os.path.relpath(out)}')
