#!/usr/bin/env python3
"""V-1: correlate the 1D stack solver against Ansys MAPDL transient thermal.

The ECTC Thermal/Mechanical subcommittee asks for "measurements & characterization,
correlations ... and model verification". Our 1D solver is verified against two analytic
solutions, which shows it solves the equation it claims to solve. It does not show that
the equation is the right one for a layered package. An independent commercial solver on
the same stack does.

Setup. MAPDL 26.1 is bundled inside the lab's RedHawk-SC Electrothermal install and runs
on Rocky 9.8 with the site license. The deck below mirrors thermal_stack_solver.py exactly:
same layer sequence, same material set, same sink boundary, same adiabatic board side,
same burst power and duty. A single column of SOLID70 with adiabatic sides reproduces the
1D case, so any difference is solver behaviour rather than a different physical problem.

Writes the deck; run it on the server with run_on_server().
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(__file__))
import thermal_stack_solver as T

SERVER  = 'dsil-sy'
RH      = '/TOOLS/SYNOPSYS/RedHawk-SC_Electrothermal_Linux64e8_Y-2026.03-SP2'
MAPDL   = f'{RH}/solver/Mechanical_Engine/v261/ansys/bin/mapdl'
REMOTE  = '~/ectc_thermal'

def deck(n_tiers=2, q_tier_W=38.0, q_logic_W=T.P_LOGIC_DIE, area_m2=T.DIE_AREA_M2,
         n_periods=12, steps_per_burst=10, steps_per_gap=20, a_col_m2=1e-8, mode='periodic'):
    """MAPDL transient-thermal deck mirroring thermal_stack_solver.py cell for cell.

    Built from explicit nodes and LINK33 conduction bars rather than solid modelling.
    Solid modelling here is fragile: the first attempt meshed 12 elements because a
    line-selection filter missed the through-thickness lines, and a 500 um layer carried
    by one element is not a transient model. LINK33 with one element per finite volume
    maps exactly onto the 1D discretisation, so any difference between the two codes is
    solver behaviour, not a different mesh.

    HGEN on LINK33 is per unit volume; volume = a_col_m2 * element length.
    """
    layers = T.build_stack(n_tiers=n_tiers)
    dz, k, rc, tag = T.discretise(layers)
    n = len(dz)
    scale = a_col_m2/area_m2
    tier_i  = [i for i, t in enumerate(tag) if t == 'SRAM_tier']
    logic_i = [i for i, t in enumerate(tag) if t == 'logic']
    t_tier  = sum(dz[i] for i in tier_i)
    t_logic = sum(dz[i] for i in logic_i)
    hg_tier  = (q_tier_W*scale)/(a_col_m2*t_tier) if t_tier else 0.0
    hg_logic = (q_logic_W*scale)/(a_col_m2*t_logic) if t_logic else 0.0

    # unique (k, rho, cp) triples -> material ids
    props, mat_of = {}, []
    for i in range(n):
        key = (float(k[i]), float(rc[i]))
        if key not in props: props[key] = len(props)+1
        mat_of.append(props[key])

    z = [0.0]
    for d in dz: z.append(z[-1]+d)

    L = []; A = L.append
    A('/BATCH')
    A('/TITLE, ECTC BEOL SRAM tier transient thermal - LINK33 1D column')
    A('/PREP7')
    A('ET,1,LINK33            ! 3-D conduction bar')
    A(f'R,1,{a_col_m2:.9e}     ! cross-sectional area [m2]')
    for (kk, rcc), mid in sorted(props.items(), key=lambda x: x[1]):
        A(f'MP,KXX,{mid},{kk:.6g}')
        A(f'MP,DENS,{mid},1.0            ! DENS*C folded into C so rho*c = {rcc:.6g}')
        A(f'MP,C,{mid},{rcc:.9g}')
    for i, zz in enumerate(z, start=1):
        A(f'N,{i},0,0,{zz:.9e}')
    A('TYPE,1 $ REAL,1')
    for i in range(n):
        A(f'MAT,{mat_of[i]} $ E,{i+1},{i+2}')
    A(f'! {n} elements, {n+1} nodes, total thickness {z[-1]*1e6:.2f} um')
    A('FINISH')
    A('/SOLU')
    A('ANTYPE,TRANS $ TRNOPT,FULL')
    A('TUNIF,0 $ OUTRES,ALL,ALL $ KBC,1')
    A('D,1,TEMP,0             ! sink face; node n+1 is the board side, left adiabatic')
    tier_e  = ','.join(str(i+1) for i in tier_i)
    logic_e = ','.join(str(i+1) for i in logic_i)
    A(f'! tier elements {tier_e}')
    A(f'! logic elements {logic_e}')
    for e in logic_i:
        A(f'BFE,{e+1},HGEN,,{hg_logic:.9e}')
    if mode == 'step':
        # constant tier power to 40 ms: gives the steady rise and the time constant,
        # the two things the lumped model needs and the 1D solver reports as tau.
        for e in tier_i: A(f'BFE,{e+1},HGEN,,{hg_tier:.9e}')
        A('! step response, log-ish sampling via successive load steps')
        for tend, nsub in ((2e-4, 20), (1e-3, 20), (5e-3, 20), (2e-2, 30), (4e-2, 20)):
            A(f'TIME,{tend:.9e} $ NSUBST,{nsub} $ SOLVE')
    else:
        burst = T.DUTY*T.PERIOD; gap = T.PERIOD-burst; t_now = 0.0
        A(f'! {n_periods} periods of {T.PERIOD*1e3:.4f} ms; burst {burst*1e6:.1f} us, gap {gap*1e6:.1f} us')
        for _ in range(n_periods):
            for e in tier_i: A(f'BFE,{e+1},HGEN,,{hg_tier:.9e}')
            t_now += burst
            A(f'TIME,{t_now:.9e} $ NSUBST,{steps_per_burst} $ SOLVE')
            for e in tier_i: A(f'BFE,{e+1},HGEN,,0')
            t_now += gap
            A(f'TIME,{t_now:.9e} $ NSUBST,{steps_per_gap} $ SOLVE')
    A('FINISH')
    A('/POST26')
    A('NUMVAR,10')
    A(f'NSOL,2,{tier_i[-1]+1},TEMP,,TIER     ! deepest tier node')
    A(f'NSOL,3,{logic_i[0]+1},TEMP,,LOGIC')
    A('/OUT,hist,txt')
    A('PRVAR,2,3')
    A('/OUT')
    A('*GET,TMAXT,VARI,2,EXTREM,VMAX')
    A('*GET,TMINT,VARI,2,EXTREM,VMIN')
    A('*GET,TMAXL,VARI,3,EXTREM,VMAX')
    A('/OUT,summary,txt')
    A("*VWRITE,TMAXT,TMINT,TMAXL")
    A("('RESULT tier_max=',E14.7,' tier_min=',E14.7,' logic_max=',E14.7)")
    A('/OUT')
    A('FINISH')
    return '\n'.join(L) + '\n'

if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    mode = sys.argv[2] if len(sys.argv) > 2 else 'periodic'
    q_logic = 0.0 if len(sys.argv) > 3 and sys.argv[3] == 'tieronly' else T.P_LOGIC_DIE
    out = os.path.join(os.path.dirname(__file__), '..', 'assets', 'mapdl')
    os.makedirs(out, exist_ok=True)
    tag = f'{n}tier_{mode}' + ('_tieronly' if q_logic == 0.0 else '')
    path = os.path.join(out, f'stack_{tag}.dat')
    open(path, 'w').write(deck(n_tiers=n, mode=mode, q_logic_W=q_logic))
    print(f'wrote {os.path.relpath(path)}  ({sum(1 for _ in open(path))} lines)')
    print(f'\nrun on the server:')
    print(f'  scp {os.path.relpath(path)} {SERVER}:{REMOTE}/')
    print(f'  ssh {SERVER} "cd {REMOTE} && {MAPDL} -b -np 8 -i stack_{n}tier.dat -o stack_{n}tier.out"')
