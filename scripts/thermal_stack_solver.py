#!/usr/bin/env python3
"""1D transient conduction through a flip-chip stack with BEOL 3D SRAM tiers.

Why not the lumped RC. ectc_thermal_model.pss_peak() treats the tier as a single
first-order node and carries tau = R_th * C_th as a SWEPT axis, because we had no
stack. That is honest but weak: tau is not free, it follows from geometry and material
properties. This solver derives it instead, and reports whether the lumped model was
right. It also gets the ORIENTATION right, which the lumped model could not express:

    heat sink | TIM | Si substrate (backside, faces the sink) | logic devices | BEOL
    (with the SRAM tiers inside it) | bumps -> substrate (high resistance, ~adiabatic)

In a flip-chip part the BEOL faces the board, so a BEOL SRAM tier is DOWNSTREAM of the
logic plane: its heat must climb back up through the logic device layer and the whole
Si die to reach the sink. The tier therefore runs HOTTER than the logic junction, and
the question "can the tier stand the temperature" is about an absolute Tj, not about
the tier's own few watts. That is E5 in ECTC_STORY.md, now with a geometry behind it.

EVERYTHING about the stack is OUR assumption and is labelled as such. The device deck
(3DSRAM_n5a v2.0) contains no cross-section, no material set and no E/bit -- its own
export note says "no power/latency model" and its own audit table says "zero
measurements". So this is a parametric design study, not a model of their device.

Numerics: finite volume, implicit (backward Euler), Dirichlet at the sink through a
TIM resistance, adiabatic at the board side. Verified against two analytic cases in
`selftest()`: steady series resistance, and the semi-infinite-slab step response.
"""
import os, sys, math
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))

# ---- material set -----------------------------------------------------------
# LITERATURE-ANCHORED (2026-09-23). The device team has no measured stack, and their
# direction was to anchor on published values rather than wait, so every entry below is
# either a measured literature value or a clearly labelled effective-medium estimate.
#   name,              k [W/m/K], rho [kg/m3], cp [J/kg/K],  grade
MAT = {
    'TIM':       (5.0,   2500.0,  800.0),   # polymer TIM, datasheet range 3-8 [vendor-class]
    'Si':        (110.0, 2330.0,  700.0),   # doped Si near 90 C (bulk 150 at 300 K) [third-party]
    'logic':     (110.0, 2330.0,  700.0),   # device layer, treated as Si
    'BEOL':      (2.5,   2300.0,  900.0),   # Cu + low-k effective vertical k. Literature is
                                            # explicit that this is ANISOTROPIC and LAYOUT
                                            # DEPENDENT and cannot be taken from the bulk
                                            # dielectric, so it stays a swept axis.
    'SRAM_tier': (1.6,   6100.0,  340.0),   # a-IGZO. MEASURED: 1.4 W/m/K (200 nm film,
                                            # thermoreflectance); 1.65 / 1.76 / 2.58 at O2
                                            # partial pressure 0 / 10 / 65% (three-omega);
                                            # amorphous oxides generally 1.3-3.0. We take the
                                            # 10% value 1.6 as nominal. rho/cp from IGZO
                                            # (~6.1 g/cm3), NOT the SiO2-like values used before.
}
IGZO_K_RANGE = (1.4, 2.6)      # [third-party, measured] swept in the sensitivity runs

def build_stack(n_tiers=2, t_si_um=500.0, t_beol_um=8.0, t_tier_um=0.05, t_ild_um=0.30,
                t_tim_um=50.0):
    """Layer list from the heat sink downward. Returns [(name, thickness_m), ...].

    LITERATURE-ANCHORED GEOMETRY (2026-09-23), replacing the earlier 1 um / 1 um guess:
      t_ild_um  = 0.30  -- monolithic-3D tier stacking uses ~300 nm PECVD SiO2 as the
                          interlayer dielectric between active tiers [third-party]
      t_tier_um = 0.05  -- the active tier itself is nanometres: 6 nm IGZO channel and
                          10 nm HfO2 gate dielectric are reported; 50 nm allows for the
                          electrodes and tier-local wiring [third-party + margin]
    So one tier costs ~0.35 um, not the 2 um assumed before. That is 5.7x thinner and it
    matters: the BEOL between the tier and the silicon is the hotspot bottleneck (E10).
    """
    L = [('TIM', t_tim_um*1e-6), ('Si', t_si_um*1e-6), ('logic', 1.0e-6)]
    L.append(('BEOL', t_beol_um*1e-6))
    for _ in range(n_tiers):
        L.append(('SRAM_tier', t_tier_um*1e-6))
        L.append(('BEOL', t_ild_um*1e-6))
    return L

def discretise(layers, dx_target=0.05e-6, max_cells=80):
    """Graded mesh: thin layers get dx_target, thick layers are capped at max_cells so a
    500 um substrate does not swamp the system. Returns per-cell (dz, k, rho*cp, tag)."""
    z, k, rc, tag = [], [], [], []
    for name, t in layers:
        n = int(min(max_cells, max(2, round(t/dx_target))))
        dz = t/n
        kk, rho, cp = MAT[name]
        z += [dz]*n; k += [kk]*n; rc += [rho*cp]*n; tag += [name]*n
    return np.array(z), np.array(k), np.array(rc), tag

def _thomas(a, b, c, d):
    """Tridiagonal solve (sub a, diag b, super c, rhs d). O(n), no scipy needed."""
    n = len(b); cp = np.empty(n-1); dp = np.empty(n)
    cp[0] = c[0]/b[0]; dp[0] = d[0]/b[0]
    for i in range(1, n):
        m = b[i] - a[i-1]*cp[i-1] if i < n else b[i]
        if i < n-1: cp[i] = c[i]/m
        dp[i] = (d[i] - a[i-1]*dp[i-1])/m
    x = np.empty(n); x[-1] = dp[-1]
    for i in range(n-2, -1, -1): x[i] = dp[i] - cp[i]*x[i+1]
    return x

def solve(layers, q_logic_W, q_tier_W, area_m2, t_end, dt, duty, period,
          T_sink=60.0, dx_target=0.5e-6, max_cells=80, record_every=1):
    """Backward-Euler 1D conduction. q_* are TOTAL watts spread over `area_m2`.
    Tier power is a square wave (duty, period); logic power is steady.
    Returns (t, T_tier_max, T_logic_mean) sampled every `record_every` steps."""
    dz, k, rc, tag = discretise(layers, dx_target, max_cells)
    n = len(dz)
    G = np.zeros(n+1)
    for i in range(1, n):
        G[i] = 1.0/(dz[i-1]/(2*k[i-1]) + dz[i]/(2*k[i]))
    G[0] = 1.0/(dz[0]/(2*k[0]))     # top face tied to the sink
    G[n] = 0.0                       # board side adiabatic [ASSUMPTION]
    tier_idx = [i for i, t in enumerate(tag) if t == 'SRAM_tier']
    logic_idx = [i for i, t in enumerate(tag) if t == 'logic']
    vol_rc = rc*dz
    src = np.zeros(n)
    if logic_idx: src[logic_idx] += (q_logic_W/area_m2)/len(logic_idx)
    src_tier = np.zeros(n)
    if tier_idx: src_tier[tier_idx] += (q_tier_W/area_m2)/len(tier_idx)
    diag = vol_rc/dt + G[:n] + G[1:]
    sub  = -G[1:n]
    sup  = -G[1:n]
    T = np.full(n, float(T_sink))
    nt = int(round(t_end/dt))
    tt, Tt, Tl = [], [], []
    for s_ in range(nt):
        t = s_*dt
        on = (t % period) < duty*period
        b = vol_rc/dt*T + src + (src_tier if on else 0.0)
        b[0] += G[0]*T_sink
        T = _thomas(sub, diag, sup, b)
        if s_ % record_every == 0:
            tt.append(t); Tl.append(T[logic_idx].mean() if logic_idx else np.nan)
            Tt.append(T[tier_idx].max() if tier_idx else np.nan)
    return np.array(tt), np.array(Tt), np.array(Tl)

def selftest():
    """Two analytic checks. Fails loudly rather than reporting a wrong tau."""
    ok = True
    A = 1e-4
    # 1. steady state = series thermal resistance of the Si layer
    layers = [('Si', 500e-6), ('logic', 1e-6)]
    R_expect = 500e-6/(MAT['Si'][0]*A)
    tt, Tt, Tl = solve(layers, 10.0, 0.0, A, t_end=2.0, dt=2e-4, duty=0.0, period=1.0,
                       T_sink=0.0, record_every=500)
    R_num = Tl[-1]/10.0
    err = abs(R_num-R_expect)/R_expect
    print(f'  [1] series R: analytic {R_expect*1e3:.4f} mK/W, solver {R_num*1e3:.4f} mK/W  -> {err*100:5.2f}% err')
    ok &= err < 0.05
    # 2. semi-infinite slab, constant surface flux: T(0,t) = q/k * sqrt(4*alpha*t/pi)
    k_, rho, cp = MAT['Si']; alpha = k_/(rho*cp)
    q = 1e4; t_probe = 5e-4
    layers = [('Si', 5000e-6), ('logic', 1e-6)]
    tt, Tt, Tl = solve(layers, q*A, 0.0, A, t_end=t_probe, dt=2e-7, duty=0.0, period=1.0,
                       T_sink=0.0, dx_target=5e-6, max_cells=1200, record_every=100)
    T_an = q/k_*math.sqrt(4*alpha*t_probe/math.pi)
    err2 = abs(Tl[-1]-T_an)/T_an
    print(f'  [2] semi-infinite step at {t_probe*1e3:.1f} ms: analytic {T_an:.4f} K, solver {Tl[-1]:.4f} K  -> {err2*100:5.2f}% err')
    ok &= err2 < 0.10
    return ok

# ---------------------------------------------------------------- design point
DIE_AREA_M2 = 800e-6            # one reticle die [scenario]
P_LOGIC_DIE = 698.7/2           # measured package power, two dies [measured]
PERIOD      = 4.515e-3          # decode step [regression-derived]
DUTY        = 0.0480            # tier duty at the C2 2-layer 800 mm2 point

def tier_tau(layers, area_m2, q_tier_W, dt=2e-6, t_end=40e-3):
    """Step-response time constant of the tier node: time to reach 1-1/e of the final
    rise. This is what the lumped model carried as a free axis."""
    tt, Tt, Tl = solve(layers, 0.0, q_tier_W, area_m2, t_end, dt, duty=1.0,
                       period=1.0, T_sink=0.0, record_every=5)
    final = Tt[-1]
    if final <= 0: return float('nan'), 0.0
    thr = final*(1-1/math.e)
    i = int(np.argmax(Tt >= thr))
    return tt[i], final

def periodic_peak_frac(layers, area_m2, q_tier_W, duty=DUTY, period=PERIOD,
                       n_periods=12, dt=5e-6):
    """Solver's own peak/(P_burst*R_th): run to periodic steady state, take the last period."""
    tt, Tt, Tl = solve(layers, 0.0, q_tier_W, area_m2, n_periods*period, dt, duty, period,
                       T_sink=0.0, record_every=1)
    last = tt >= (n_periods-1)*period
    _, R_final = tier_tau(layers, area_m2, q_tier_W)
    return Tt[last].max()/R_final, Tt[last].max(), Tt[last].min(), R_final


if __name__ == '__main__':
    print('self-tests (analytic):')
    ok = selftest(); print('  PASS\n' if ok else '  FAIL\n')
    if not ok: sys.exit(1)

    import ectc_thermal_model as M
    print('=== design point: one 800 mm2 die, BEOL SRAM tiers, flip-chip ===')
    print(f'  logic {P_LOGIC_DIE:.1f} W/die [measured], duty {DUTY*100:.2f}%, period {PERIOD*1e3:.3f} ms')
    print(f'  stack: TIM 50 um | Si 500 um | logic | BEOL 8 um | (tier 1 um + ILD 1 um) x N')
    print('  ALL stack geometry and materials are OUR assumption; the deck has no cross-section.\n')

    print(f"{'N tiers':>8} {'tau [us]':>10} {'lumped pk':>10} {'solver pk':>10} {'ratio':>7} "
          f"{'dT tier-logic [K]':>18}")
    rows = []
    for N in (1, 2, 4, 8):
        lay = build_stack(n_tiers=N)
        q_burst = M.p_burst_W(0.5)/2                      # 0.5 pJ/bit, per die
        tau, R_fin = tier_tau(lay, DIE_AREA_M2, q_burst)
        pf_solver, tmax, tmin, _ = periodic_peak_frac(lay, DIE_AREA_M2, q_burst)
        pf_lumped = M.pss_peak(DUTY, tau, PERIOD)
        # absolute: logic steady + tier periodic, together
        tt, Tt, Tl = solve(lay, P_LOGIC_DIE, q_burst, DIE_AREA_M2, 12*PERIOD, 5e-6,
                           DUTY, PERIOD, T_sink=60.0, record_every=1)
        last = tt >= 11*PERIOD
        d_excess = Tt[last].max() - Tl[last].mean()
        rows.append((N, tau, pf_lumped, pf_solver, d_excess))
        print(f'{N:>8} {tau*1e6:>9.0f} {pf_lumped:>10.4f} {pf_solver:>10.4f} '
              f'{pf_solver/pf_lumped:>7.2f} {d_excess:>17.2f}')
    print(f'\n  perfect averaging would be {DUTY:.4f}; tracking the burst would be 1.0000')
    print('  "dT tier-logic" is the tier peak MINUS the logic junction, which is the part')
    print('  the stack geometry sets and the cooling boundary does not.')

    print('\n=== what this does to the ECTC headline ===')
    N2 = build_stack(n_tiers=2); q = M.p_burst_W(0.5)/2
    tau2, _ = tier_tau(N2, DIE_AREA_M2, q)
    pf_s = periodic_peak_frac(N2, DIE_AREA_M2, q)[0]
    pf_l = M.pss_peak(DUTY, tau2, PERIOD)
    print(f"{'model':>34} {'peak_frac':>10} {'cap @20 W, 0.5 pJ/bit':>23}")
    for lab, pf in (('steady-state relation (device deck)', 1.0),
                    ('lumped RC, ECTC_STORY v1', pf_l),
                    ('THIS SOLVER (1D, verified)', pf_s),
                    ('perfect averaging (floor)', DUTY)):
        print(f'{lab:>34} {pf:>10.4f} {M.bw_cap_TBs(20, 0.5, pf):>19.1f} TB/s')
    print(f'\n  The lumped model was optimistic by {pf_s/pf_l:.1f}x on the peak. A thin, low-k tier on a')
    print('  thick slow substrate is NOT one first-order node: the tier heats locally inside a')
    print(f'  {PERIOD*1e3:.1f} ms period even though the stack tau is {tau2*1e3:.1f} ms.')
    print(f'  Relief is {M.bw_cap_TBs(20,0.5,pf_s)/5.0:.1f}x, not {M.bw_cap_TBs(20,0.5,pf_l)/5.0:.1f}x -- '
          f'still clears the {M.BW_HBM:.2f} TB/s floor, with far less margin.')
    print('\n  LIMITATION: 1D. Uniform tier power over a full reticle, no lateral spreading,')
    print('  so this bounds the AVERAGE tier temperature, not a hotspot. Hotspots need 3D.')
