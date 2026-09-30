#!/usr/bin/env python3
"""Temporal x spatial ablation: which resolution does the tier's thermal screening need?

Every comparison so far mixed two things. The static maps were one tier-wide block in space
and nothing in time; the "burst-resolved" answers were 1D (tier-wide) in space when they came
from sota_comparators/burst_shape, and macro-resolved in space when they came from MAPDL. So a
gap between "ours" and a practice could be temporal or spatial. Here the two axes are varied
one at a time on the SAME model:

  temporal   static peak | static average | window-mean traces (10 ms ... 2 us, worst of 8
             alignments, read at window ends as a ptrace row is) | exact schedule
  spatial    tier-uniform (1D, what sota_comparators solves) | C2 macro with the periphery
             share phi = 0.285 (uniform), 0.5, 0.7, 0.9 (what the MAPDL decks solve)

The model is the MAPDL macro unit cell (mapdl_macro: 153 x 518 um, L-shaped periphery, adiabatic
sides, i.e. a mirrored array) on the V-Cache F2B stack, solved without a time step: the lateral
field is expanded in the cell's cosine modes, each lateral mode is the 1D layered network of
sota_comparators with the lateral conduction k_xy kappa^2 added, and each of those is solved
mode by mode (MatEx). Nothing is fitted. It is checked against the 16 MAPDL runs already in
assets/mapdl/vcache_sched (static and one-block transient, lid and production boundary, phi
0.285-0.9) before it is used.

The decision metric needs one threshold for every method, or the spatial axis cancels out
(mapdl_vcache_schedules normalises each map by its own static peak, so a concentrated map
earns a larger allowance). Here the allowance is fixed: the tier may add what the device team's
10 W/die budget adds when spread over the die, dT_lim = 10 W x R_uniform. B_max = 19 TB/s x
dT_lim / (the method's peak rise at 19 TB/s). Absolute kelvin are reported too, since that
allowance itself shrinks with better cooling.

  python3 scripts/temporal_spatial_ablation.py           # check vs MAPDL, sweep, JSON
  python3 scripts/temporal_spatial_ablation.py --check   # the MAPDL check only
"""
import os, sys, math, json, time
import numpy as np
from scipy.linalg import eigh_tridiagonal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_stack_solver as TS
import ectc_thermal_model as M
import hb_stack_check as HB
import mapdl_macro as MM
import burst_shape as BS

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets', 'sweep', 'temporal_spatial_ablation.json')
HB.use_device(HB.SI)
LAYERS = HB.vcache_stack('F2B')
A_DIE = TS.DIE_AREA_M2
PERIOD, DUTY = TS.PERIOD, TS.DUTY
LX, LY = MM.MACRO
AX, AY = MM.ARRAY
A_CELL, A_ARR = LX*LY, AX*AY
A_PER = A_CELL - A_ARR
R_EXT_PROD = json.load(open(os.path.join(HERE, '..', 'assets', 'mapdl', 'vcache',
                                         'reference.json')))['r_conv_K_per_W']
PACKAGES = [('ideal lid', 0.0), ('R_ext/R_stack 2.9', 0.075), ('production deck', R_EXT_PROD)]
PHIS = [MM.PERI_AREA_FRAC, 0.5, 0.7, 0.9]
BUDGET_W_DIE = 10.0                      # 20 W tier budget over two dies
B_R = M.B_R                              # 19 TB/s
E_BITS = (0.217, 0.374, 0.5)             # v3.4 point, literature pessimistic end, first abstract
WINDOWS = (10e-3, 1e-3, 500e-6, 200e-6, 100e-6, 50e-6, 20e-6, 10e-6, 5e-6, 2e-6)
DRIFT_MIN = 500e-6                       # windows this long or longer: global grid, 40 periods
LN_BIN = 2e-3                            # relative width of the decay-rate bins

def p_burst(e_pJ):
    return M.p_burst_W(e_pJ)/2           # W per die at 19 TB/s

def points():
    """Where the tier maximum is looked for: the macro's corners and edges (mirror planes, where
    neighbouring peripheries meet), across the periphery, and the array centre."""
    xs = [0.0, AX/2, AX, AX + (LX - AX)/2, LX]
    ys = [0.0, AY/2, AY, AY + (LY - AY)/4, AY + (LY - AY)/2, AY + 3*(LY - AY)/4, LY]
    return [(x, y) for x in xs for y in ys]

class Cell:
    """Tier response of the unit cell to (a) uniform areal power and (b) power on the array
    rectangle only, at every evaluation point, as sums of decaying exponentials whose rates are
    pooled into narrow bins (each bin keeps its exact steady contribution)."""
    def __init__(self, r_ext, nm=(32, 108), dx=0.25e-6, kxy_over_kz=1.0, pts=None):
        dz, k, rc, tag = TS.discretise(LAYERS, dx, 80)
        n = len(dz); G = np.zeros(n + 1)
        for i in range(1, n): G[i] = 1.0/(dz[i-1]/(2*k[i-1]) + dz[i]/(2*k[i]))
        G[0] = 1.0/(dz[0]/(2*k[0]) + r_ext*A_DIE)
        A0 = np.diag(G[:n] + G[1:])
        for i in range(1, n): A0[i, i-1] = A0[i-1, i] = -G[i]
        kxy = np.array([kk*(kxy_over_kz if t == 'BEOL' else 1.0) for kk, t in zip(k, tag)])
        C = rc*dz; c = 1.0/np.sqrt(C)
        tier = [i for i, t in enumerate(tag) if t == 'SRAM_tier']
        rows_z = [tier[0], tier[-1]]                  # the tier's two faces, as MAPDL's nodes
        s = np.zeros(n); s[tier] = 1.0/len(tier)      # unit areal power spread over the tier
        self.pts = points() if pts is None else pts
        M_, N_ = nm
        ms, ns = np.arange(M_ + 1), np.arange(N_ + 1)
        # cosine coefficients of the array indicator on [0,LX] x [0,LY]
        gx = np.where(ms == 0, AX/LX, 2*np.sin(ms*np.pi*AX/LX)/(np.maximum(ms, 1)*np.pi))
        gy = np.where(ns == 0, AY/LY, 2*np.sin(ns*np.pi*AY/LY)/(np.maximum(ns, 1)*np.pi))
        px = np.array([p[0] for p in self.pts]); py = np.array([p[1] for p in self.pts])
        cx = np.cos(np.outer(px, ms)*np.pi/LX); cy = np.cos(np.outer(py, ns)*np.pi/LY)
        nrow = len(self.pts)*len(rows_z)
        self.nbin = int(40/LN_BIN)
        accU = np.zeros((nrow, self.nbin)); accP = np.zeros((nrow, self.nbin))
        pairs = [(m, q) for m in ms for q in ns]
        d0 = c*c*np.diag(A0); off = c[:-1]*c[1:]*np.diag(A0, 1)   # symmetrised, tridiagonal
        lat_d = c*c*kxy*dz
        for c0 in range(0, len(pairs), 400):
            chunk = pairs[c0:c0 + 400]
            kap2 = np.array([(m*np.pi/LX)**2 + (q*np.pi/LY)**2 for m, q in chunk])
            lam = np.empty((len(chunk), n)); Ut = np.empty((len(chunk), len(tier), n))
            for b, k2 in enumerate(kap2):
                lam[b], U = eigh_tridiagonal(d0 + k2*lat_d, off)
                Ut[b] = U[tier, :]
            w = np.einsum('bik,i->bk', Ut, (c*s)[tier])            # modal input per unit areal W
            iz = [tier.index(r) for r in rows_z]
            shp = c[None, rows_z, None]*Ut[:, iz, :]               # (b, 2, n)
            steady = shp*(w/lam)[:, None, :]                       # K per unit areal W, per mode
            lat = np.array([cx[:, m]*cy[:, q] for m, q in chunk])  # (b, npts)
            g = np.array([gx[m]*gy[q] for m, q in chunk])
            bins = np.clip(np.floor(np.log(lam)/LN_BIN).astype(int), 0, self.nbin - 1).ravel()
            is00 = np.array([m == 0 and q == 0 for m, q in chunk])
            for zr in range(len(rows_z)):
                st = steady[:, zr, :]
                vP = (lat*g[:, None])[:, :, None]*st[:, None, :]           # (b, npts, n)
                for p in range(len(self.pts)):
                    r = p*len(rows_z) + zr
                    accP[r] += np.bincount(bins, vP[:, p, :].ravel(), self.nbin)
                    if is00.any():
                        vU = st[is00][:, None, :]*lat[is00][:, p][:, None, None]
                        b00 = np.clip(np.floor(np.log(lam[is00])/LN_BIN).astype(int), 0, self.nbin - 1).ravel()
                        accU[r] += np.bincount(b00, vU.ravel(), self.nbin)
        keep = np.flatnonzero((np.abs(accU) + np.abs(accP)).max(axis=0) > 0)
        self.lam = np.exp((keep + 0.5)*LN_BIN)
        # store steady contributions S (K per unit areal W); a mode's response is S (1 - e^-lam t)
        self.SU, self.SP = accU[:, keep], accP[:, keep]
        self.nz = len(rows_z)

    def source(self, phi, P_die=1.0):
        """Steady contributions for a macro with periphery share phi at P_die watts per die."""
        q_cell = P_die*A_CELL/A_DIE
        q_per, q_arr = phi*q_cell/A_PER, (1 - phi)*q_cell/A_ARR
        return q_per*self.SU + (q_arr - q_per)*self.SP

    def uniform(self, P_die=1.0):
        """The tier-uniform (1D) model: the (0,0) mode alone."""
        return (P_die/A_DIE)*self.SU

class Mod:
    """Exponential sum in the form burst_shape.periodic_peak expects: w/lam per mode = steady."""
    def __init__(self, lam, S):
        self.lam, self.w, self.phi = lam, lam.copy(), S

def reduce_rows(mod, S_rows):
    return Mod(mod.lam, mod.phi[S_rows])

def steady_max(mod):
    return (mod.phi.sum(axis=1)).max()

def exact_peak(mod, segs, n_sub=6):
    """Continuous periodic-steady-state maximum of the schedule (segments in W per die,
    normalised by P_BURST so the burst is 1)."""
    return BS.periodic_peak(mod, [(d, q/BS.P_BURST) for d, q in segs], n_sub)[0]

def binned(segs, window, phase):
    """The schedule's window means on a grid restarted every period at `phase`."""
    E = BS.energy_fn(segs)
    edges = [0.0] + [phase + j*window for j in range(int(math.ceil(PERIOD/window)) + 1)
                     if 0 < phase + j*window < PERIOD] + [PERIOD]
    edges = sorted(set(edges))
    return [(b - a, (E(b) - E(a))/(b - a)) for a, b in zip(edges[:-1], edges[1:])]

def window_end_peak(mod, segs):
    """Periodic steady state read at segment ends only (a ptrace row is reported at its end)."""
    lam = mod.lam
    F = np.zeros_like(lam)
    for d, q in segs: F = F*np.exp(-lam*d) + (-np.expm1(-lam*d))*q
    y = F/(-np.expm1(-lam*PERIOD))
    best = -np.inf
    for d, q in segs:
        y = y*np.exp(-lam*d) + (-np.expm1(-lam*d))*q
        best = max(best, (mod.phi @ y).max())
    return best

def trace_peak(mod, segs, window, n_phase=8):
    """Window-mean trace, worst of n_phase alignments. Windows >= DRIFT_MIN use a global grid
    over a 40-period run from the average state (burst_shape.trace_peak, which lets the grid
    drift against the step); shorter windows restart the grid every period, which differs only
    in the host gap, where the tier is idle."""
    s = [(d, q/BS.P_BURST) for d, q in segs]
    if window >= DRIFT_MIN:
        return _drift(mod, s, window, n_phase)
    return max(window_end_peak(mod, binned(s, window, ph))
               for ph in np.arange(n_phase)*window/n_phase)

def _drift(mod, s, window, n_phase):
    E = BS.energy_fn(s); lam = mod.lam
    n = max(200, int(math.ceil(40*PERIOD/window)))
    dec, gain = np.exp(-lam*window), -np.expm1(-lam*window)
    best = -np.inf
    for ph in np.arange(n_phase)*min(window, PERIOD)/n_phase:
        a = ph + np.arange(n + 1)*window
        q = np.diff(np.array([E(x) for x in a]))/window
        y = np.full_like(lam, E(PERIOD)/PERIOD)
        for m in range(n):
            y = y*dec + gain*q[m]
            if m >= n//2: best = max(best, (mod.phi @ y).max())
    return best

def lumped_peak(R, tau, segs):
    """One first-order node with the stack's own R and tau (the lumped-RC practice)."""
    m = Mod(np.array([1.0/tau]), np.array([[R]]))
    return exact_peak(m, segs)

def stepped_one_block(mod, sub_on=109, sub_off=30, nper=6):
    """One block stepped exactly as the vcache_sched decks step it (mapdl_vcache_schedules.nsub:
    <= 2 us per substep while on, 30 over the off-phase): backward Euler, average-state start."""
    lam = mod.lam; tp = DUTY*PERIOD
    y = np.full_like(lam, DUTY)
    peaks = []
    for _ in range(nper):
        dt = tp/sub_on
        for _ in range(sub_on): y = (y + dt*lam*1.0)/(1 + lam*dt)
        peaks.append((mod.phi @ y).max())
        dt = (PERIOD - tp)/sub_off
        for _ in range(sub_off): y = y/(1 + lam*dt)
    return peaks[-1]

def stepped_schedule(mod, segs, nper=6):
    """A schedule stepped as mapdl_vcache_schedules steps it: nsub() backward-Euler substeps per
    segment, from the average-power state, nper periods; the peak is the largest value at any
    segment end of the last period (the deck keeps the last substep of each load step)."""
    import mapdl_vcache_schedules as MS
    lam = mod.lam
    avg = sum(d*q for d, q in segs)/sum(d for d, _ in segs)/BS.P_BURST
    y = np.full_like(lam, avg); best = -np.inf
    for k in range(nper):
        for d, q in segs:
            m = MS.nsub(d, q); dt = d/m; f = q/BS.P_BURST
            den = 1 + lam*dt
            for _ in range(m): y = (y + dt*lam*f)/den
            if k == nper - 1: best = max(best, (mod.phi @ y).max())
    return best

def check_schedules(cells):
    """This model against the kernel-by-kernel MAPDL decks (S1 and S3, mapdl_vcache_schedules)."""
    mp = mapdl_rows(); P = MM.Q_BURST_DIE; out = []
    base_prod = mp['static_phiU']['tier1']
    runs = [('ideal lid', None, 'S1', 's1_verify'), ('ideal lid', 0.5, 'S1', 'lid_s1_phi50'),
            ('ideal lid', 0.7, 'S1', 'lid_s1_phi70'), ('ideal lid', 0.9, 'S1', 'lid_s1_phi90'),
            ('production deck', None, 'S1', 's1_phiU'), ('production deck', 0.5, 'S1', 'prod_s1_phi50'),
            ('production deck', 0.7, 'S1', 'prod_s1_phi70'), ('production deck', 0.9, 'S1', 's1_phi90'),
            ('production deck', 0.9, 'S3', 's3_phi90')]
    for pkg, phi, sch, name in runs:
        if name not in mp: continue
        cell = cells[pkg]
        S = cell.uniform(P) if phi is None else cell.source(phi, P)
        mod = Mod(cell.lam, S)
        red = reduce_rows(mod, np.argsort(-mod.phi.sum(axis=1))[:6])
        ours = stepped_schedule(red, BS.schedule(sch, 'mixed'))
        ref = mp[name]['peak'] - (0.0 if pkg == 'ideal lid' else base_prod)
        out.append((f'{pkg:>15} {sch} kernel by kernel, phi {"U" if phi is None else phi}', ours, ref))
    print(f"{'case':>52} {'this model K':>13} {'MAPDL K':>10} {'diff':>8}")
    worst = 0.0
    for name, a, b in out:
        worst = max(worst, abs(a/b - 1))
        print(f'{name:>52} {a:>13.5f} {b:>10.5f} {(a/b - 1)*100:>+7.2f}%')
    print(f'worst |difference| {worst*100:.2f}%')
    return out, worst

def mapdl_rows():
    rows = {}
    for fn in ('results.txt', 'run_lid.txt', 'run_phi.txt'):
        for line in open(os.path.join(HERE, '..', 'assets', 'mapdl', 'vcache_sched', fn)):
            if 'RESULT' not in line: continue
            name = line.split()[0]
            rows[name] = {k: float(v) for k, v in
                          __import__('re').findall(r'(\w+)=\s*([-+0-9.E]+)', line)}
    return rows

PHI_TAG = {MM.PERI_AREA_FRAC: 'phiU', 0.5: 'phi50', 0.7: 'phi70', 0.9: 'phi90'}

def check(cells):
    """This model against every MAPDL V-Cache run: steady maps exactly, one-block transients
    stepped as the decks step. MAPDL values are at 38 W/die; rises are over logic-only."""
    mp = mapdl_rows(); P = MM.Q_BURST_DIE; out = []
    for pkg, cell in cells.items():
        lid = pkg == 'ideal lid'
        if pkg not in ('ideal lid', 'production deck'): continue
        for phi, tag in PHI_TAG.items():
            st = mp.get(('lid_' if lid else '') + f'static_{tag}')
            S = cell.source(phi, P); mod = Mod(cell.lam, S)
            ours = steady_max(mod)
            if st:
                ref = st['tier3'] - st['tier1']
                out.append((f'{pkg:>15} steady at burst power, {tag}', ours, ref))
                ref2 = st['tier2'] - st['tier1']
                out.append((f'{pkg:>15} steady at average power, {tag}', DUTY*ours, ref2))
            tr = mp.get(('lid_' if lid else 'prod_') + f's0_{tag}')
            if tr:
                base = 0.0 if lid else mp[f'static_{tag}']['tier1']
                out.append((f'{pkg:>15} one block, BE as the deck, {tag}', stepped_one_block(Mod(cell.lam, S)),
                            tr['peak'] - base))
    print(f"{'case':>52} {'this model K':>13} {'MAPDL K':>10} {'diff':>8}")
    worst = 0.0
    for name, a, b in out:
        worst = max(worst, abs(a/b - 1))
        print(f'{name:>52} {a:>13.5f} {b:>10.5f} {(a/b - 1)*100:>+7.2f}%')
    print(f'worst |difference| {worst*100:.2f}%')
    return out, worst

def schedules():
    s = {'S0 one block': BS.schedule('S0')}
    for pol, lab in (('S1', 'S1 layers 0-9 (Gate-1)'), ('S2', 'S2 interleaved over 32 layers'),
                     ('S3', 'S3 down proj. every layer'), ('S4', 'S4 page slice')):
        s[lab] = BS.schedule(pol, 'mixed')
    if os.path.exists(BS.TRACE):
        s['S1 on the measured kernel trace'] = BS.schedule_measured('S1')[0]
    for v in s.values(): BS.check_energy(v)
    return s

def tau_of(mod_uniform):
    """Time for the tier-uniform step response to reach 1 - 1/e of its final value."""
    t = np.logspace(-8, 1, 4000)
    z = ((-np.expm1(-np.outer(t, mod_uniform.lam))) @ mod_uniform.phi.T).max(axis=1)
    return float(np.interp(1 - math.exp(-1), z/z[-1], t))

def main():
    t0 = time.time()
    if '--convergence' in sys.argv:
        for nm, dx in (((24, 80), 0.25e-6), ((48, 160), 0.25e-6), ((72, 240), 0.25e-6), ((48, 160), 0.125e-6)):
            c = Cell(0.0, nm=nm, dx=dx, pts=[(LX, LY), (LX, 0.0), (0.0, LY)])
            print(nm, f'dx {dx*1e6:g} um', f'[{time.time() - t0:.0f}s]',
                  [f'{steady_max(Mod(c.lam, c.source(ph, 38.0))):.5f}' for ph in PHIS],
                  [f'{stepped_one_block(Mod(c.lam, c.source(ph, 38.0))):.5f}' for ph in PHIS])
        return
    cells = {}
    for name, r in (PACKAGES if '--check' not in sys.argv else [p for p in PACKAGES if p[0] != 'R_ext/R_stack 2.9']):
        cells[name] = Cell(r)
        print(f'[{time.time() - t0:5.0f}s] built {name}: {len(cells[name].lam)} rate bins')
    chk, worst = check(cells)
    chk2, worst2 = check_schedules(cells)
    if '--check' in sys.argv: return
    sch = schedules()
    res = dict(design=dict(period_s=PERIOD, duty=DUTY, budget_W_die=BUDGET_W_DIE, B_R_TBs=B_R,
                           E_bits_pJ=E_BITS, P_burst_W_die={str(e): p_burst(e) for e in E_BITS},
                           windows_s=WINDOWS, macro_um=[LX*1e6, LY*1e6], array_um=[AX*1e6, AY*1e6],
                           threshold='dT_lim = budget x R_uniform (fixed across methods)'),
               mapdl_check=[dict(case=n, model_K=a, mapdl_K=b) for n, a, b in chk],
               mapdl_check_worst=worst,
               mapdl_schedule_check=[dict(case=n, model_K=a, mapdl_K=b) for n, a, b in chk2],
               mapdl_schedule_check_worst=worst2, cases={})
    for pkg, cell in cells.items():
        U = Mod(cell.lam, cell.uniform(1.0))
        R_u = steady_max(U)
        tau = tau_of(U)
        spatial = {'tier-uniform (1D)': U}
        for phi in PHIS:
            spatial[f'macro phi={phi:.3f}'] = Mod(cell.lam, cell.source(phi, 1.0))
        for sp_name, mod in spatial.items():
            st = steady_max(mod)
            # rows where this map can peak: its static maximum and the few next hottest points
            order = np.argsort(-mod.phi.sum(axis=1))[:6]
            red = reduce_rows(mod, order)
            for s_name, segs in sch.items():
                key = f'{pkg} | {sp_name} | {s_name}'
                r = dict(package=pkg, spatial=sp_name, schedule=s_name, R_uniform_K_per_W=R_u,
                         tau_uniform_s=tau)
                r['static-peak'] = st
                r['static-avg'] = DUTY*st
                r['exact'] = exact_peak(mod, segs)
                r['one block (217 us)'] = exact_peak(mod, sch['S0 one block'])
                for w in WINDOWS:
                    r[f'trace-{w*1e6:g}us'] = trace_peak(red, segs, w)
                r['lumped RC (die node)'] = lumped_peak(R_u, tau, segs)
                res['cases'][key] = r
            print(f'[{time.time() - t0:5.0f}s] {pkg} | {sp_name}: static {st/R_u:.3f} R_u, '
                  f'exact S0 {res["cases"][f"{pkg} | {sp_name} | S0 one block"]["exact"]/R_u:.4f} R_u')
        json.dump(res, open(OUT, 'w'), indent=1)
    json.dump(res, open(OUT, 'w'), indent=1)
    print(f'wrote {os.path.relpath(OUT)} in {time.time() - t0:.0f}s')

if __name__ == '__main__':
    main()
