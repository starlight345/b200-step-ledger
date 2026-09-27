#!/usr/bin/env python3
"""Reproduce, on our design point, how the state-of-the-art thermal practices treat the tier load.

The question is not which SOLVER is best -- layered compact models (HotSpot, 3D-ICE) and FEM
(Ansys, Celsius) all resolve a thin tier on a thick die, and ours is verified against MAPDL and
Icepak. The question is what POWER INPUT those flows are given, because that is where the bursty
decode load gets lost. So every comparator below runs on the SAME verified layered solver and
differs only in how the tier power enters:

  static-peak      steady state at the burst power            (= the BW <= P/E screening rule)
  static-avg       steady state at duty x burst power         (time-averaged power map)
  trace-dt         transient, power trace averaged over windows of dt, as a HotSpot-style
                   ptrace at sampling interval dt feeds it (each row = mean power in its window),
                   integrated exactly within each window (HotSpot default build, 3D-ICE, CoMeT)
  be1-dt           the same trace, one backward-Euler step per window (HotSpot built with
                   SuperLU; ATLAS's stated update C(T+ - T)/dt + G T+ = P_t)
  zth-datasheet    the power-device datasheet approximation for periodic pulses:
                   dT = P [ D Rth + (1-D) Zth(T+tp) - Zth(T) + Zth(tp) ]
  zth-eq22         onsemi AND8220 eq.22 shortcut, R(t,d) ~ (1-d) Zth(t) + d Rth
  zth-single       one pulse, no history: P Zth(tp) (the Infineon 'pocket calculator')
  zth-exact        superposition of the step response over past pulses (exact for a linear stack)
  lumped           single first-order node with the stack's own step-response tau
  exact            the burst train in closed form, mode by mode (no time step): MatEx, AND8220
                   eq.24 with the exact Foster expansion, an Icepak LTI ROM, a JESD51-34 matrix
  burst            the workload-derived burst train, resolved by time stepping (our answer)

Which published study uses which input is the PRACTICES table at the bottom; the literature
behind it is ECTC_SOTA_THERMAL.md. Stacks: the current BEOL tier, the shipping V-Cache
dimensions, and hybrid-bonded SRAM dies of 10-100 um -- see hb_stack_check.py. The fast solver
pre-inverts the constant backward-Euler matrix (dt fixed); both it and the modal solver are
checked against thermal_stack_solver.solve() before use.
"""
import os, sys, math
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import thermal_stack_solver as TS
import ectc_thermal_model as M
import hb_stack_check as HB

PERIOD, DUTY = TS.PERIOD, TS.DUTY
TP = DUTY*PERIOD

class Fast:
    """Backward-Euler conduction with the matrix inverted once. Tier power is any function."""
    def __init__(self, layers, area_m2, dt, dx_target=0.5e-6, max_cells=80):
        dz, k, rc, tag = TS.discretise(layers, dx_target, max_cells)
        n = len(dz); G = np.zeros(n+1)
        for i in range(1, n):
            G[i] = 1.0/(dz[i-1]/(2*k[i-1]) + dz[i]/(2*k[i]))
        G[0] = 1.0/(dz[0]/(2*k[0])); G[n] = 0.0
        self.vol_rc = rc*dz; self.dt = dt
        A = np.diag(self.vol_rc/dt + G[:n] + G[1:])
        for i in range(1, n):
            A[i, i-1] = A[i-1, i] = -G[i]
        self.Ainv = np.linalg.inv(A)
        self.G0 = G[0]
        self.tier = np.array([i for i, t in enumerate(tag) if t == 'SRAM_tier'])
        self.logic = np.array([i for i, t in enumerate(tag) if t == 'logic'])
        self.src_tier = np.zeros(n); self.src_tier[self.tier] = 1.0/area_m2/len(self.tier)
        self.src_logic = np.zeros(n)
        if len(self.logic): self.src_logic[self.logic] = 1.0/area_m2/len(self.logic)
        self.n = n

    def run(self, q_tier_fn, t_end, q_logic=0.0, T_sink=0.0, T0=None):
        T = np.full(self.n, float(T_sink)) if T0 is None else np.array(T0, float)
        nt = int(round(t_end/self.dt))
        tier_max = np.empty(nt); logic_mean = np.empty(nt); tt = np.arange(nt)*self.dt
        base = self.src_logic*q_logic; base = base.copy(); base[0] += self.G0*T_sink
        for s in range(nt):
            b = self.vol_rc/self.dt*T + base + self.src_tier*q_tier_fn(tt[s])
            T = self.Ainv @ b
            tier_max[s] = T[self.tier].max()
            logic_mean[s] = T[self.logic].mean() if len(self.logic) else np.nan
        return tt, tier_max, logic_mean

def burst_fn(P, period=PERIOD, tp=TP, phase=0.0):
    return lambda t: P if ((t - phase) % period) < tp else 0.0

def burst_overlap(w0, window, period=PERIOD, tp=TP):
    """Time inside bursts [m*period, m*period+tp) within [w0, w0+window)."""
    tot, m = 0.0, math.floor(w0/period) - 1
    while m*period < w0 + window:
        a, b = max(w0, m*period), min(w0 + window, m*period + tp)
        if b > a: tot += b - a
        m += 1
    return tot

def windowed_fn(P, window, period=PERIOD, tp=TP, phase=0.0):
    """HotSpot-style ptrace: each sampling window carries the MEAN power over it."""
    def f(t):
        # the small offset keeps s*window/window from flooring to s-1
        w0 = math.floor((t - phase)/window + 1e-9)*window + phase
        return P*burst_overlap(w0, window, period, tp)/window
    return f

def periodic_peak(fast, fn, n_periods=12, T0=None):
    """Largest tier value in the last period. From a cold start the package mode (~15 ms on
    the V-Cache stack) has not settled after 12 periods and the peak reads ~0.7% low; pass
    T0 = the average-power steady state (Modal.avg_state) and a few periods suffice."""
    tt, Tt, _ = fast.run(fn, n_periods*PERIOD, T0=T0)
    last = tt >= (n_periods-1)*PERIOD
    return Tt[last].max()

def step_response(fast, P, t_end):
    tt, Tt, _ = fast.run(lambda t: P, t_end)
    return tt, Tt

class Modal:
    """The same discretised stack solved in closed form, mode by mode (no time step).

    C dT/dt = -G T + s q(t), C diagonal: symmetrise with C^-1/2, diagonalise once, and each mode
    is a first-order node that integrates any piecewise-constant q exactly. This is MatEx
    (Pagani et al., DATE 2015) on our network; for a square wave it is AND8220 eq.24 with the
    network's exact Foster expansion, and what an Icepak LTI ROM or a JESD51-34 Zth matrix
    computes for a linear stack. Everything is per watt of tier power."""
    def __init__(self, layers, area_m2, dx_target=0.5e-6, max_cells=80):
        dz, k, rc, tag = TS.discretise(layers, dx_target, max_cells)
        n = len(dz); G = np.zeros(n+1)
        for i in range(1, n):
            G[i] = 1.0/(dz[i-1]/(2*k[i-1]) + dz[i]/(2*k[i]))
        G[0] = 1.0/(dz[0]/(2*k[0]))
        A = np.diag(G[:n] + G[1:])
        for i in range(1, n):
            A[i, i-1] = A[i-1, i] = -G[i]
        self._diagonalise(A, rc*dz, [i for i, t in enumerate(tag) if t == 'SRAM_tier'], area_m2)

    @classmethod
    def network(cls, A, C, tier, area_m2):
        """Any 1D RC network per unit area: conductance matrix A (W/m2K), heat capacities C
        (J/m2K), source nodes `tier`. Used to replicate HotSpot's own network exactly."""
        m = cls.__new__(cls)
        m._diagonalise(A, C, tier, area_m2)
        return m

    def _diagonalise(self, A, C, tier, area_m2):
        c = 1.0/np.sqrt(C)
        self.lam, U = np.linalg.eigh(c[:, None]*A*c[None, :])
        s = np.zeros(len(C)); s[tier] = 1.0/area_m2/len(tier)
        self.w = U.T @ (c*s)                     # modal input per watt
        self.shapes = c[:, None]*U               # mode shapes, every cell
        self.phi = self.shapes[tier]             # mode shapes at the tier cells
        self.R = (self.phi @ (self.w/self.lam)).max()

    def avg_state(self, q, duty=DUTY):
        """Every cell's temperature at the average tier power: the start state for a transient.
        It is NOT the periodic state at a burst's start -- every slow mode sits w q D (P-a)/2
        above it there, whatever its tau -- so a run started here reads high for many periods
        (+1% after 4 on the V-Cache stack; the package mode is ~16 ms)."""
        return self.shapes @ (self.w/self.lam*duty*q)

    def pss_state(self, q, duty=DUTY, period=PERIOD):
        """Every cell's temperature at the start of a burst, periodic steady state."""
        lam, a = self.lam, duty*period
        y_a = self.w/lam*(-np.expm1(-lam*a))/(-np.expm1(-lam*period))
        return self.shapes @ (y_a*np.exp(-lam*(period - a))*q)

    def trace_series(self, window, n, y0, phase=0.0):
        """Tier maximum (per watt) at the end of each of n windows of mean power, integrated
        exactly inside each window, from modal state y0. Window m covers
        [phase + m*window, phase + (m+1)*window)."""
        lam, w = self.lam, self.w
        dec, gain = np.exp(-lam*window), w/lam*(-np.expm1(-lam*window))
        y, out = np.array(y0, float), np.empty(n)
        for m in range(n):
            y = y*dec + gain*burst_overlap(phase + m*window, window)/window
            out[m] = (self.phi @ y).max()
        return out

    def Z(self, t):
        """Step response of the hottest tier cell, K/W (exact Zth)."""
        t = np.atleast_1d(np.asarray(t, float))
        y = (self.w/self.lam)[None, :]*(-np.expm1(-np.outer(t, self.lam)))
        return (y @ self.phi.T).max(axis=1)

    def square_pss(self, duty=DUTY, period=PERIOD, n_t=4000):
        """Periodic-steady-state peak under the burst train, as a fraction of the burst-power
        steady rise. The period is scanned so the maximum is not assumed to sit at burst end."""
        lam, w = self.lam, self.w
        a = duty*period
        y_a = w/lam*(-np.expm1(-lam*a))/(-np.expm1(-lam*period))    # end of burst
        y_0 = y_a*np.exp(-lam*(period - a))                           # start of burst
        t_on = np.linspace(0.0, a, n_t//4)
        t_off = np.linspace(a, period, n_t)
        on = y_0*np.exp(-np.outer(t_on, lam)) + (w/lam)*(-np.expm1(-np.outer(t_on, lam)))
        off = y_a*np.exp(-np.outer(t_off - a, lam))
        return (np.vstack([on, off]) @ self.phi.T).max()/self.R

    def trace_peak(self, window, n_phase=8):
        """Tier power entered as window means (a ptrace row, an epoch, a 3D-ICE slot) and
        integrated exactly inside each window, starting from the average-power steady state.
        The peak is the largest window-end value over the second half of a 40-period run,
        maximised over n_phase offsets of the window grid: a long trace meets every
        burst/window alignment, and which ones one run happens to contain moves a coarse-row
        peak by a few tenths of a percent (seen against HotSpot, hotspot_rerun.py)."""
        n = max(200, int(math.ceil(40*PERIOD/window)))
        y0 = self.w/self.lam*DUTY
        return max(self.trace_series(window, n, y0, ph)[n//2:].max()
                   for ph in np.arange(n_phase)*min(window, PERIOD)/n_phase)/self.R

def be1_peak(layers, window, q, T0):
    """The same trace with ONE backward-Euler step per window, from the average-power steady
    state; the peak is taken over the second half, as in Modal.trace_peak."""
    fast = Fast(layers, TS.DIE_AREA_M2, window)
    n = max(200, int(math.ceil(40*PERIOD/window)))
    tt, Tt, _ = fast.run(windowed_fn(q, window), n*window, T0=T0)
    return Tt[n//2:].max()

TRACE_WINDOWS = (10e-6, 50e-6, 100e-6, 200e-6, 217e-6, 500e-6, 1e-3, PERIOD, 10e-3, 200e-3, 333e-3)
BE1_WINDOWS = (10e-6, 100e-6, 1e-3, 10e-3)

def wkey(prefix, w):
    return f'{prefix}-{w*1e6:.0f}us'

def comparators(layers, device, dt=2e-6):
    HB.use_device(device)
    q = M.p_burst_W(0.5)/2
    mod = Modal(layers, TS.DIE_AREA_M2)
    R = mod.R
    out = {'R_K_per_W': R}
    out['static-peak'] = 1.0
    out['static-avg'] = DUTY
    out['exact'] = mod.square_pss()
    T0 = mod.avg_state(q)
    fast = Fast(layers, TS.DIE_AREA_M2, dt)
    out['burst'] = periodic_peak(fast, burst_fn(q), n_periods=2, T0=mod.pss_state(q))/(q*R)
    for w in TRACE_WINDOWS:
        out[wkey('trace', w)] = mod.trace_peak(w)
    for w in BE1_WINDOWS:
        out[wkey('be1', w)] = be1_peak(layers, w, q, T0)/(q*R)
    D, T, tp = DUTY, PERIOD, TP
    Z = lambda t: float(mod.Z(t)[0])
    out['zth-datasheet'] = (D*R + (1-D)*Z(T+tp) - Z(T) + Z(tp))/R
    out['zth-eq22'] = (1-D)*Z(tp)/R + D
    out['zth-single'] = Z(tp)/R
    tau, _ = TS.tier_tau(layers, TS.DIE_AREA_M2, q)
    n_hist = int(math.ceil(20*tau/T)) + 50
    zz = mod.Z(np.concatenate([np.arange(n_hist)*T + tp, np.arange(n_hist)*T]))
    out['zth-exact'] = float(np.sum(zz[:n_hist] - zz[n_hist:]))/R
    out['lumped'] = M.pss_peak(DUTY, tau, PERIOD)
    return out

# Who does what. Each practice is mapped to the comparator that reproduces its power input on
# our stack. 'grade' is how the practice was established (ECTC_SOTA_THERMAL.md has the sources):
#   V = read in the primary source (paper text or released code), independently re-checked
#   P = read in the primary source, one reader
#   S = secondary coverage only
PRACTICES = [
    ('static peak map (BW x E_bit at full bandwidth)',
     'Stratum MICRO25 Eq.1 [V]; Helios 2026 [V]; Ai et al. 2026 [V]; A3D-MoE 2025, FEM [V]; '
     'FGDRAM MICRO17 Fig.1a [P]; Keckler IEEE Micro 2011 [P]; Eckert/Jayasena/Loh 2014 [P]; '
     'Arm ECTC20 maxpower map [V]; MFIT steady mode [V]', 'static-peak'),
    ('instantaneous power-density cap (burst counted in full)',
     'VOXEL MICRO26 paper DSE 0.7 W/mm2 [P]; d-Matrix Hot Chips 26 0.5 W/mm2 [S]; MPU 2021 [P]',
     'static-peak'),
    ('static average map / trace averaged to steady state',
     'Tasa ICCAD25, HotSpot 6 steady [V]; DeepStack MICRO26, T=Tamb+R(m)P on run-average power [V]; '
     'HotSpot steady_file and DRAMsim3 steady output average the trace [V, source code]',
     'static-avg'),
    ('trace, 10 ms rows', 'HotSpot template.config and 5 of 6 examples [V]; MFIT TODAES25, 10 ms sampling [V]',
     'trace-10000us'),
    ('trace, 1 ms epochs', 'CoMeT TACO22 [V]; DRAMsim3 HBM2 config [V]', 'trace-1000us'),
    ('trace, 200 us steps', 'HotGauge IISWC21 (3D-ICE) [V]', 'trace-200us'),
    ('trace, ~10 us event bins, one implicit step per bin', 'VOXEL released code, 3D-ICE backend [P, code]',
     'be1-10us'),
    ('implicit Euler, one step per 1 ms interval', 'ATLAS 2026 (dt not stated) [V]; HotSpot SuperLU build [V]',
     'be1-1000us'),
    ('trace, 0.2 s slots / 333 ms rows', '3D-ICE example [V]; PACT example [V]', 'trace-200000us'),
    ('lumped RC node', 'Computational sprinting HPCA12 [P]; HeatCache 2026 [P]', 'lumped'),
    ('datasheet duty-cycle Zth, two-pulse', 'Motorola AN569 / Philips Ch.7 [P]', 'zth-datasheet'),
    ('datasheet duty-cycle Zth, eq.22', 'onsemi AND8220 [P]', 'zth-eq22'),
    ('single-pulse Zth, no history', 'Infineon MOSFET note [P]', 'zth-single'),
    ('exact Zth superposition / LTI ROM, fed the burst train',
     'Schweitzer TCAPT09 [P]; JESD51-34 [S]; Icepak LTI ROM [P]; Flotherm BCI-ROM [P]; MatEx DATE15 [V]',
     'exact'),
    ('burst-resolved layered transient (ours)', 'this work; MAPDL and Icepak verified', 'burst'),
]

def selfcheck():
    """Fast solver vs thermal_stack_solver.solve on the BEOL baseline, same dt; then the modal
    solver against a fine-step Fast run on the shipping V-Cache stack."""
    HB.use_device(HB.IGZO)
    lay = TS.build_stack(n_tiers=2); q = M.p_burst_W(0.5)/2
    tt, Tt, _ = TS.solve(lay, 0.0, q, TS.DIE_AREA_M2, 3*PERIOD, 5e-6, DUTY, PERIOD, T_sink=0.0)
    fast = Fast(lay, TS.DIE_AREA_M2, 5e-6)
    t2, T2, _ = fast.run(burst_fn(q), 3*PERIOD)
    n = min(len(Tt), len(T2))
    err = np.max(np.abs(Tt[:n] - T2[:n]))/np.max(np.abs(Tt[:n]))
    print(f'self-check vs thermal_stack_solver.solve: max relative difference {err:.2e}')
    # modal (no time step) vs backward Euler converging in dt, both from the periodic state
    HB.use_device(HB.SI)
    lay = HB.vcache_stack('F2B'); mod = Modal(lay, TS.DIE_AREA_M2); ex = mod.square_pss()
    for dt in (2e-6, 1e-6, 0.5e-6):
        f = Fast(lay, TS.DIE_AREA_M2, dt)
        pf = periodic_peak(f, burst_fn(q), n_periods=2, T0=mod.pss_state(q))/(q*mod.R)
        print(f'  burst train: modal exact {ex:.5f}, backward Euler dt {dt*1e6:.1f} us {pf:.5f} '
              f'({(pf/ex - 1)*100:+.2f}%)')
    ok_modal = abs(pf/ex - 1) < 3e-3
    # a 1 ms trace, one phase, cold start: both solvers read at the same window ends
    f = Fast(lay, TS.DIE_AREA_M2, 1e-6)
    tt, Tt, _ = f.run(windowed_fn(q, 1e-3), 108e-3)
    fe = Tt[999::1000][-5:]/(q*mod.R)                 # states at 104..108 ms
    me = (mod.trace_series(1e-3, 108, np.zeros_like(mod.lam))/mod.R)[-5:]
    dev = np.max(np.abs(fe/me - 1))
    print(f'  1 ms trace, same window ends: modal {me.max():.5f}, backward Euler dt 1 us '
          f'{fe.max():.5f} (max deviation {dev*100:.2f}%)')
    return err < 1e-6 and ok_modal and dev < 5e-3

if __name__ == '__main__':
    if not selfcheck(): sys.exit('a fast solver disagrees with the reference solver')
    stacks = [('BEOL tier (current)', TS.build_stack(n_tiers=2), HB.IGZO)]
    stacks.append(('V-Cache dims, F2B (6 um)', HB.vcache_stack('F2B'), HB.SI))
    stacks.append(('V-Cache dims, F2F (6 um)', HB.vcache_stack('F2F'), HB.SI))
    for t in (10.0, 20.0, 50.0, 100.0):
        stacks.append((f'hybrid-bond F2F {t:g} um', HB.hb_stack('F2F', t), HB.SI))
    keys = None; rows = []
    for name, lay, dev in stacks:
        r = comparators(lay, dev); rows.append((name, r))
        keys = [k for k in r if k != 'R_K_per_W']
    print(f'\npeak fraction (tier peak / burst-power steady rise); cap = 5.0 TB/s / peak fraction at 20 W, 0.5 pJ/bit')
    print(f"{'comparator':>16} " + ' '.join(f'{n[:22]:>23}' for n, _ in rows))
    for k in keys:
        print(f'{k:>16} ' + ' '.join(f"{r[k]:>8.4f} ({M.bw_cap_TBs(20, 0.5, r[k]):>6.1f} TB/s)" for _, r in rows))
    main = dict(rows)
    print('\npublished practice -> TB/s at 20 W, 0.5 pJ/bit, and error vs the exact burst answer')
    print(f"{'practice':>58} {'BEOL tier':>18} {'V-Cache F2B 6 um':>18}")
    for label, who, key in PRACTICES:
        cells = []
        for nm in ('BEOL tier (current)', 'V-Cache dims, F2B (6 um)'):
            r = main[nm]; cap = M.bw_cap_TBs(20, 0.5, r[key]); ref = M.bw_cap_TBs(20, 0.5, r['exact'])
            cells.append(f'{cap:>7.1f} ({cap/ref:>5.2f}x)')
        print(f'{label[:58]:>58} {cells[0]:>18} {cells[1]:>18}')
    import json
    out = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sweep', 'sota_comparators.json')
    json.dump({'stacks': {n: r for n, r in rows},
               'practices': [dict(practice=l, studies=w, comparator=k) for l, w, k in PRACTICES],
               'design_point': dict(duty=DUTY, period_s=PERIOD, burst_W_per_die=M.p_burst_W(0.5)/2,
                                    budget_W=20.0, e_pJ_per_bit=0.5)},
              open(out, 'w'), indent=1)
    print(f'\nwrote {os.path.relpath(out)}')
