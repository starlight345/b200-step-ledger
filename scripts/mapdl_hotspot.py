#!/usr/bin/env python3
"""V-2: how wrong can the 1D model be if the tier's power is NOT uniform?

thermal_stack_solver.py spreads the tier power evenly over a reticle and solves in one
dimension. That is a real limitation and it is stated as one. This closes it by building
a 3D structured model in MAPDL and concentrating the SAME total tier power into a square
patch of side L, sweeping L from a single macro up to the full quarter-die.

Why the uniform case is not merely convenient here. Decode streams the resident weight
set every step, and the resident set is spread across every macro of the tier, so in this
workload the tier really is close to uniformly active. The sweep therefore does two jobs:
it shows the 1D assumption is workload-justified at large L, and it bounds what a
different (non-streaming) workload could do.

Mesh is built from explicit nodes and EGEN rather than solid modelling, for the same
reason as mapdl_correlation.py: solid-model selection filters silently produced a
12-element mesh on the first attempt.

Quarter symmetry: the patch is centred at the origin and all four lateral faces are
adiabatic (two are symmetry planes, two are far enough away to be adiabatic).
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(__file__))
import thermal_stack_solver as T

def deck(n_tiers=2, q_tier_W=38.0, patch_um=None, half_span_um=2000.0, nlat=40,
         area_m2=T.DIE_AREA_M2):
    """Steady-state 3D conduction. patch_um = side of the ACTIVE square (full width,
    centred); None means the whole quarter-domain is active (the 1D-equivalent case).
    The total tier watts are held fixed, so a smaller patch means a hotter patch."""
    layers = T.build_stack(n_tiers=n_tiers)
    # z discretisation: coarser than the 1D run (steady state does not need the fine grid)
    zc = []
    for name, t in layers:
        n = {'TIM': 4, 'Si': 20, 'logic': 1, 'BEOL': 4, 'SRAM_tier': 1}.get(name, 2)
        for _ in range(n): zc.append((name, t/n))
    nz = len(zc)
    z = [0.0]
    for _, d in zc: z.append(z[-1]+d)
    half = half_span_um*1e-6
    dx = half/nlat
    # The domain is a REPEATING UNIT CELL of the die, not a quarter of it. Adiabatic
    # lateral faces make it one cell of a periodic array of identical hotspots, so the
    # die-average power density is preserved no matter how small the patch gets.
    cell_area = (2*half)**2                       # full cell (the model is one quarter of it)
    q_quarter = q_tier_W*(cell_area/area_m2)/4.0  # watts in the modelled quarter
    patch = (patch_um*1e-6/2) if patch_um else half        # half-width of the active square
    t_tier = sum(d for nm, d in zc if nm == 'SRAM_tier')
    active_area = patch*patch                              # quarter of the full patch
    # sanity: at patch == half this reproduces the 1D volumetric source exactly
    hgen = q_quarter/(active_area*t_tier)

    props, mat_of = {}, []
    for name, d in zc:
        k, rho, cp = T.MAT[name]
        key = (k, rho*cp)
        if key not in props: props[key] = len(props)+1
        mat_of.append(props[key])

    NPL = nz+1                       # nodes per z column
    NPX = (nlat+1)*NPL               # node increment per y row
    L = []; A = L.append
    A('/BATCH')
    A(f'/TITLE, ECTC V-2 hotspot spreading, patch={patch_um if patch_um else "full"} um')
    A('/PREP7')
    A('ET,1,SOLID70')
    for (k, rc), mid in sorted(props.items(), key=lambda x: x[1]):
        A(f'MP,KXX,{mid},{k:.6g}')
        A(f'MP,DENS,{mid},1.0')
        A(f'MP,C,{mid},{rc:.9g}')
    A('! z column of nodes at (0,0), then replicate in x and y')
    for kk, zz in enumerate(z, start=1):
        A(f'N,{kk},0,0,{zz:.9e}')
    A(f'NGEN,{nlat+1},{NPL},1,{NPL},1,{dx:.9e},0,0')
    A(f'NGEN,{nlat+1},{NPX},1,{(nlat+1)*NPL},1,0,{dx:.9e},0')
    A('TYPE,1')
    for kk in range(nz):
        n1 = kk+1; n2 = n1+NPL; n3 = n2+NPX; n4 = n1+NPX
        A(f'MAT,{mat_of[kk]}')
        A(f'E,{n1},{n2},{n3},{n4},{n1+1},{n2+1},{n3+1},{n4+1}')
        A(f'EGEN,{nlat},{NPL},-1')
        A(f'EGEN,{nlat},{NPX},-{nlat}')
    A(f'! {nz*nlat*nlat} elements')
    A('FINISH')
    A('/SOLU')
    A('ANTYPE,STATIC')
    # Layer order runs sink-side first (TIM at z=0) down to the tiers at z_max, matching
    # thermal_stack_solver's index 0 == sink convention. The Dirichlet face is therefore
    # z=0, NOT z_max. Getting this backwards puts the sink on the tier and under-reports
    # the rise by ~19x, which is how it was caught.
    A(f'NSEL,S,LOC,Z,-1e-9,{z[1]*0.5:.9e}')
    A('D,ALL,TEMP,0')
    A('ALLSEL,ALL')
    ztier = [(sum(d for _, d in zc[:i]), sum(d for _, d in zc[:i+1]))
             for i, (nm, d) in enumerate(zc) if nm == 'SRAM_tier']
    A('ESEL,NONE')
    for za, zb in ztier:
        A(f'ESEL,A,CENT,Z,{za:.9e},{zb:.9e}')
    A(f'ESEL,R,CENT,X,0,{patch:.9e}')
    A(f'ESEL,R,CENT,Y,0,{patch:.9e}')
    A(f'BFE,ALL,HGEN,,{hgen:.9e}')
    A('ALLSEL,ALL $ SOLVE $ FINISH')
    A('/POST1')
    A('SET,LAST')
    A('ESEL,NONE')
    for za, zb in ztier:
        A(f'ESEL,A,CENT,Z,{za:.9e},{zb:.9e}')
    A('NSLE,S')
    A('NSORT,TEMP')
    A('*GET,TPK,SORT,0,MAX')
    A('ALLSEL,ALL')
    A('/OUT,summary,txt')
    A("*VWRITE,TPK")
    A("('RESULT tier_peak=',E14.7)")
    A('/OUT')
    A('FINISH')
    return '\n'.join(L)+'\n'

if __name__ == '__main__':
    out = os.path.join(os.path.dirname(__file__), '..', 'assets', 'mapdl')
    os.makedirs(out, exist_ok=True)
    cases = [None, 2000, 1000, 500, 200, 100]
    for pu in cases:
        tag = 'full' if pu is None else f'{pu}um'
        path = os.path.join(out, f'hotspot_{tag}.dat')
        open(path, 'w').write(deck(patch_um=pu))
        print(f'  wrote hotspot_{tag}.dat')
    print('\nrun: ssh dsil-sy "cd ~/ectc_thermal && for f in hotspot_*.dat; do mapdl -b -np 1 -i $f ...; done"')
