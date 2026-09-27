#!/usr/bin/env python3
"""Macro-resolved 3D TRANSIENT model: one C2 SRAM macro, duty-cycled, on a live logic die.

Why this exists. Every 3D MAPDL run so far was steady state, while the paper's claim is
about a duty-cycled transient; only the 1D model had ever been run transient. And the 3D
hotspot study bracketed reality between a uniform tier (1x) and a 100 um patch (502x),
two extremes nobody builds. A real tier is an array of macros, and read power
concentrates in each macro's periphery. This model resolves exactly that, and nothing
it does not have data for.

Geometry comes from the device team, not from us (DESIGN_POINT_3DSRAM.md, table 1):
  C2 macro (periphery in BEOL, uncompensated)   153 x 518 um
  C1 macro (same macro, periphery moved to Si)  133 x 426 um   <- the bare array
so the C2 periphery is an L: a 20 um band along the long edge (row side) and a 92 um
band along the short edge (sense-amp side), 28.5% of macro area. NOTE: the 83.6% "usable"
figure elsewhere in the repo is a CAPACITY fraction (0.88 x 0.95), not periphery area.

The unit cell is one full macro with adiabatic sides, i.e. a mirrored array -- so
neighbouring peripheries abut back to back. That doubles the effective strip width and
is the conservative arrangement. Both tiers carry the same macro, stacked.

Two modes:
  verify   tier power only, uniform over the macro, Dirichlet 0 at the sink face. By
           symmetry this must reproduce the verified 1D transient solver's periodic peak.
           It is the check that the 3D transient machinery is right before it is trusted.
  prod     logic die at the measured 349 W/die, convection sink calibrated to a 100 C
           junction (same h as mapdl_representative.py), periphery power share phi swept.

phi is the share of tier power dissipated in the periphery. phi = 0.285 (its area share)
is the uniform case. Higher phi concentrates power: 0.9 puts 90% of the power in 28.5%
of the area, a 3.2x density. SRAM read energy is commonly periphery-heavy; the sweep
covers that range rather than choosing a value.
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import thermal_stack_solver as T
import ectc_thermal_model as M
from mapdl_representative import sink_h, T_BULK_C

MACRO = (153e-6, 518e-6)
ARRAY = (133e-6, 426e-6)
PERI_AREA_FRAC = 1.0 - (ARRAY[0]*ARRAY[1])/(MACRO[0]*MACRO[1])
Q_BURST_DIE = M.p_burst_W(0.5)/2          # 38 W per die while a burst is in flight
P_LOGIC_DIE = T.P_LOGIC_DIE               # 349.35 W per die [measured / 2]

def _graded(t, n, ratio=1.0, fine_at_top=True):
    """n cell thicknesses summing to t, geometric, finest cell at the top if asked."""
    if n == 1 or ratio == 1.0:
        return [t/n]*n
    w = np.array([ratio**i for i in range(n)])
    w = w/w.sum()*t
    return list(w[::-1] if fine_at_top else w)

def zcells(layers, refine=1.0):
    """Per-layer cell counts. Resolution goes where the transient is: BEOL and the top of
    the silicon, where the burst's heat arrives within one 217 us pulse."""
    base = {'TIM': 3, 'Si': 14, 'logic': 1, 'BEOL': 6, 'SRAM_tier': 1,
            'SRAM_Si': 4, 'bond': 1}          # the last two: hybrid-bond stacks (hb_stack_check)
    out = []
    for i, (name, t) in enumerate(layers):
        n = base.get(name, 1)
        if name == 'BEOL' and t < 1e-6: n = 1          # the 0.3 um inter-tier ILDs
        n = max(1, int(round(n*refine))) if name in ('Si', 'BEOL', 'TIM') and t > 1e-6 else n
        ratio = 1.25 if name == 'Si' else 1.0
        for d in _graded(t, n, ratio, fine_at_top=True):
            out.append((name, d))
    return out

def lateral(refine=1.0):
    nx = (max(2, int(round(14*refine))), max(2, int(round(4*refine))))
    ny = (max(2, int(round(40*refine))), max(2, int(round(10*refine))))
    xs = list(np.linspace(0, ARRAY[0], nx[0]+1)) + list(np.linspace(ARRAY[0], MACRO[0], nx[1]+1)[1:])
    ys = list(np.linspace(0, ARRAY[1], ny[0]+1)) + list(np.linspace(ARRAY[1], MACRO[1], ny[1]+1)[1:])
    return xs, ys

def deck(mode='prod', phi=None, kxy_over_kz=1.0, refine_xy=1.0, refine_z=1.0,
         nper=6, sub_on=16, sub_off=30, plots=False, cdb=False, tag='macro',
         layers=None, h=None):
    """layers: any stack whose heat sources are tagged 'SRAM_tier' and 'logic' (default the
    BEOL two-tier stack). h: sink convection coefficient; the default is sink_h's
    calibration, which is for the BEOL stack's Si + TIM -- pass h for another stack."""
    phi = PERI_AREA_FRAC if phi is None else phi
    layers = T.build_stack(n_tiers=2) if layers is None else layers
    zc = zcells(layers, refine_z)
    z = [0.0]
    for _, d in zc: z.append(z[-1]+d)
    xs, ys = lateral(refine_xy)
    nx, ny, nz = len(xs)-1, len(ys)-1, len(zc)
    A_die = T.DIE_AREA_M2
    A_cell = MACRO[0]*MACRO[1]
    A_arr = ARRAY[0]*ARRAY[1]; A_per = A_cell - A_arr
    t_tier = sum(d for nm, d in zc if nm == 'SRAM_tier')
    t_logic = sum(d for nm, d in zc if nm == 'logic')
    q_cell_on = Q_BURST_DIE*A_cell/A_die                 # watts in this macro during a burst
    hg_arr_on = (1-phi)*q_cell_on/(A_arr*t_tier)
    hg_per_on = phi*q_cell_on/(A_per*t_tier)
    duty, per = T.DUTY, T.PERIOD
    hg_log = (P_LOGIC_DIE/(A_die*t_logic)) if mode == 'prod' else 0.0
    if h is None:
        h, _, _ = sink_h(P_LOGIC_DIE + Q_BURST_DIE*duty, A_die)

    props, mat_of = {}, []
    for name, d in zc:
        k, rho, cp = T.MAT[name]
        kxy = k*kxy_over_kz if name == 'BEOL' else k
        key = (kxy, k, rho*cp)
        if key not in props: props[key] = len(props)+1
        mat_of.append(props[key])

    NZ1, NX1 = nz+1, nx+1
    nid = lambda i, j, k: 1 + k + NZ1*(i + NX1*j)
    L = []; A = L.append
    A('/BATCH')
    A(f'/TITLE, C2 macro {MACRO[0]*1e6:.0f}x{MACRO[1]*1e6:.0f} um, {mode}, phi={phi:.3f}, BEOL kxy/kz={kxy_over_kz:g}')
    A('/PREP7')
    A('ET,1,SOLID70')
    for (kxy, kz, rc), mid in sorted(props.items(), key=lambda x: x[1]):
        A(f'MP,KXX,{mid},{kxy:.6g}'); A(f'MP,KYY,{mid},{kxy:.6g}'); A(f'MP,KZZ,{mid},{kz:.6g}')
        A(f'MP,DENS,{mid},1.0'); A(f'MP,C,{mid},{rc:.9g}')
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            for k, zz in enumerate(z):
                A(f'N,{nid(i,j,k)},{x:.9e},{y:.9e},{zz:.9e}')
    A('TYPE,1')
    for k in range(nz):
        A(f'MAT,{mat_of[k]}')
        for j in range(ny):
            for i in range(nx):
                a, b, c, d = nid(i,j,k), nid(i+1,j,k), nid(i+1,j+1,k), nid(i,j+1,k)
                A(f'E,{a},{b},{c},{d},{a+1},{b+1},{c+1},{d+1}')
    nel = nx*ny*nz
    A(f'! {nel} elements, {NX1*(ny+1)*NZ1} nodes')
    # components: tier array / tier periphery / logic / sink face
    def zr(tag_):
        acc, out = 0.0, []
        for nm, d in zc:
            if nm == tag_: out.append((acc, acc+d))
            acc += d
        return out
    A('ESEL,NONE')
    for za, zb in zr('SRAM_tier'): A(f'ESEL,A,CENT,Z,{za:.9e},{zb:.9e}')
    A('CM,TIER,ELEM')
    A(f'ESEL,R,CENT,X,0,{ARRAY[0]:.9e}'); A(f'ESEL,R,CENT,Y,0,{ARRAY[1]:.9e}')
    A('CM,TIER_ARR,ELEM')
    A('CMSEL,S,TIER'); A('CMSEL,U,TIER_ARR'); A('CM,TIER_PER,ELEM')
    A('ESEL,NONE')
    for za, zb in zr('logic'): A(f'ESEL,A,CENT,Z,{za:.9e},{zb:.9e}')
    A('CM,LOGIC,ELEM')
    A(f'NSEL,S,LOC,Z,-1e-12,{z[1]*0.5:.9e}'); A('CM,SINK,NODE')
    A('ALLSEL,ALL')
    if cdb:
        A(f'CDWRITE,DB,{tag},cdb')
    A('FINISH')

    A('/SOLU')
    A('ANTYPE,TRANS'); A('TRNOPT,FULL'); A('KBC,1'); A('AUTOTS,OFF')
    A('OUTRES,ERASE'); A('OUTRES,NSOL,LAST')
    A(f'TUNIF,{(T_BULK_C if mode=="prod" else 0.0):.6g}')
    A('CMSEL,S,SINK')
    if mode == 'prod': A(f'SF,ALL,CONV,{h:.9e},{T_BULK_C:.6g}')
    else:              A('D,ALL,TEMP,0')
    A('ALLSEL,ALL')
    def loads(qa, qp, ql):
        A(f'CMSEL,S,TIER_ARR $ BFE,ALL,HGEN,,{qa:.9e}')
        A(f'CMSEL,S,TIER_PER $ BFE,ALL,HGEN,,{qp:.9e}')
        A(f'CMSEL,S,LOGIC $ BFE,ALL,HGEN,,{ql:.9e}')
        A('ALLSEL,ALL')
    # load step 1: steady state at the duty-averaged power, the periodic cycle's mean
    loads(hg_arr_on*duty, hg_per_on*duty, hg_log)
    A('TIMINT,OFF'); A('TIME,1e-6'); A('NSUBST,1'); A('SOLVE')
    A('TIMINT,ON')
    A(f'PER={per:.9e}'); A(f'DON={duty*per:.9e}'); A('T0=1e-6')
    A(f'*DO,IP,1,{nper}')
    loads(hg_arr_on, hg_per_on, hg_log)
    A('TB_=T0+(IP-1)*PER+DON'); A('TIME,TB_'); A(f'NSUBST,{sub_on}'); A('SOLVE')
    loads(0.0, 0.0, hg_log)
    A('TE_=T0+IP*PER'); A('TIME,TE_'); A(f'NSUBST,{sub_off}'); A('SOLVE')
    A('*ENDDO')
    A('FINISH')

    A('/POST1')
    lsb = 2*nper                      # load step of the last burst end (LS1 is the steady start)
    def grab(ls, comp, var, how='MAX'):
        A(f'SET,{ls},LAST')
        A(f'CMSEL,S,{comp} $ NSLE,S $ NSORT,TEMP')
        A(f'*GET,{var},SORT,0,{how}')
        A('ALLSEL,ALL')
    grab(lsb,   'TIER',  'TPK')         # periodic peak, anywhere on the tier
    grab(lsb,   'TIER',  'TPKMIN', 'MIN')   # coolest tier point at the same instant
    grab(lsb,   'LOGIC', 'TLG')         # logic plane at the same instant
    grab(lsb-2, 'TIER',  'TPKP')        # previous period's peak -> convergence
    grab(lsb+1, 'TIER',  'TTR')         # end of the last off-phase -> trough
    grab(1,     'TIER',  'TMEAN')       # mean-power steady state
    A('/OUT,summary,txt')
    A('*VWRITE,TPK,TPKMIN,TLG,TPKP,TTR,TMEAN')
    A("('RESULT peak=',E15.8,' peakmin=',E15.8,' logic=',E15.8,' prevpeak=',E15.8,"
      "' trough=',E15.8,' mean=',E15.8)")
    A('/OUT')
    if plots:
        A(f'SET,{lsb},LAST')
        A('/SHOW,PNG'); A('/GFILE,1600')
        A('/RGB,INDEX,100,100,100,0'); A('/RGB,INDEX,80,80,80,13')
        A('/RGB,INDEX,60,60,60,14'); A('/RGB,INDEX,0,0,0,15')
        A('/PLOPTS,INFO,3 $ /PLOPTS,FRAME,0 $ /PLOPTS,LOGO,0 $ /PLOPTS,DATE,0'); A('/TRIAD,OFF')
        A('/VIEW,1,0,0,1 $ /ANG,1 $ /AUTO,1')
        A('CMSEL,S,TIER $ NSLE,S $ /PNUM,MAT,0 $ /NUMBER,0')
        A('/TITLE, Tier plane at the end of a burst [C]')
        A('PLNSOL,TEMP')
        A('ESEL,S,CENT,Y,0,{:.9e}'.format(ys[1]))
        A(f'ESEL,R,CENT,Z,{z[-1]-2.0e-5:.9e},{z[-1]*1.001:.9e}')
        A('NSLE,S')
        A('/VIEW,1,0,-1,0 $ /AUTO,1')
        A('/TITLE, Top 20 um section through the macro [C]')
        A('PLNSOL,TEMP')
        A('ALLSEL,ALL'); A('/SHOW,CLOSE')
    A('FINISH')
    info = dict(nel=nel, nnode=NX1*(ny+1)*NZ1, nz=nz, nx=nx, ny=ny, phi=phi,
                hg_arr_on=hg_arr_on, hg_per_on=hg_per_on, h=h, q_cell_on=q_cell_on)
    return '\n'.join(L)+'\n', info

def reference_1d():
    """Verified 1D solver: periodic peak of the tier alone, same power density and duty."""
    lay = T.build_stack(n_tiers=2)
    pf, pk, tr, Rf = T.periodic_peak_frac(lay, T.DIE_AREA_M2, Q_BURST_DIE)
    return pk, tr

if __name__ == '__main__':
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'mapdl', 'macro')
    os.makedirs(out, exist_ok=True)
    print(f'periphery area share {PERI_AREA_FRAC:.4f}  (C1 array {ARRAY[0]*1e6:.0f}x{ARRAY[1]*1e6:.0f} '
          f'inside C2 macro {MACRO[0]*1e6:.0f}x{MACRO[1]*1e6:.0f} um)')
    cases = [('verify', dict(mode='verify'))]
    for k in (1.0, 10.0):
        for ph in (None, 0.5, 0.7, 0.9):
            nm = f"prod_k{int(k)}_phi{('U' if ph is None else int(round(ph*100)))}"
            cases.append((nm, dict(mode='prod', phi=ph, kxy_over_kz=k,
                                   plots=(ph == 0.9 and k == 1.0), cdb=(ph == 0.9 and k == 1.0))))
    cases.append(('conv_fine', dict(mode='prod', phi=0.9, kxy_over_kz=1.0, refine_xy=2.0, refine_z=1.5,
                                    sub_on=24, sub_off=40)))
    for nm, kw in cases:
        body, info = deck(tag=nm, **kw)
        open(os.path.join(out, nm+'.dat'), 'w').write(body)
        print(f"{nm:<16} {info['nel']:>7} el {info['nnode']:>7} nodes  phi={info['phi']:.3f}  "
              f"periphery density x{info['hg_per_on']/max(info['hg_arr_on'],1e-30)*(1-PERI_AREA_FRAC)/PERI_AREA_FRAC if info['hg_arr_on']>0 else float('inf'):.2f} vs array")
    pk, tr = reference_1d()
    print(f'\n1D reference (verified solver): periodic peak {pk:.6f} K, trough {tr:.6f} K')


def export_deck(tag='macro_c2_for_mechanical', kxy_over_kz=1.0, refine_xy=1.0, refine_z=1.0):
    """Model-only deck for opening in Ansys Mechanical (Workbench) via External Model.

    Same mesh and components as the solved decks, but with REAL density and specific
    heat. The solve decks store DENS=1 and C=rho*cp, which is exact for conduction (only
    the product enters) but would display as 'density 1 kg/m3' in Mechanical's material
    view -- not something to put on a slide. No loads and no solve here: the CDB carries
    geometry, mesh, materials and named components; loads are applied in Mechanical by
    named selection (see MAPDL_TO_MECHANICAL.md)."""
    body, info = deck(mode='prod', kxy_over_kz=kxy_over_kz, refine_xy=refine_xy,
                      refine_z=refine_z, cdb=False, tag=tag)
    pre = body[:body.index('FINISH\n')]              # everything up to the end of /PREP7
    # rewrite the material block with real rho and cp, one material per physical layer
    lines = [l for l in pre.split('\n') if not l.startswith('MP,')]
    mats, out, used = {}, [], set()
    for name, (k, rho, cp) in T.MAT.items():
        mats[name] = (k*kxy_over_kz if name == 'BEOL' else k, k, rho, cp)
    layers = T.build_stack(n_tiers=2)
    zc = zcells(layers, refine_z)
    # map the solve deck's material ids (by first appearance per layer) to layer names
    seen = {}
    for name, _ in zc:
        if name not in seen: seen[name] = len(seen)+1
    mp = []
    for name, mid in seen.items():
        kxy, kz, rho, cp = mats[name]
        mp += [f'MP,KXX,{mid},{kxy:.6g}', f'MP,KYY,{mid},{kxy:.6g}', f'MP,KZZ,{mid},{kz:.6g}',
               f'MP,DENS,{mid},{rho:.6g}', f'MP,C,{mid},{cp:.6g}']
    # the element block uses MAT ids assigned per (k, rho*cp); rebuild them by layer name
    new_lines, k_layer = [], -1
    for l in lines:
        if l.startswith('MAT,'):
            k_layer += 1
            new_lines.append(f'MAT,{seen[zc[k_layer][0]]}')
        else:
            new_lines.append(l)
    i_et = next(i for i, l in enumerate(new_lines) if l.startswith('ET,1,SOLID70'))
    new_lines = new_lines[:i_et+1] + mp + new_lines[i_et+1:]
    new_lines.append(f'CDWRITE,DB,{tag},cdb')
    new_lines.append('FINISH')
    names = {v: k for k, v in seen.items()}
    return '\n'.join(new_lines)+'\n', info, names


def viz_deck(phi=0.9, kxy_over_kz=1.0, tag='viz_phi90'):
    """The same solved case as prod_k1_phi90, re-run with every substep stored so MAPDL
    itself can draw the time history (POST26) -- the duty-cycle sawtooth -- alongside the
    field plots. All pictures are the solver's own graphics output, not re-plots."""
    body, info = deck(mode='prod', phi=phi, kxy_over_kz=kxy_over_kz, tag=tag)
    body = body.replace('OUTRES,NSOL,LAST', 'OUTRES,NSOL,ALL')
    body = body[:body.rindex('FINISH')]            # drop the final FINISH; POST1 is open
    xs, ys = lateral(1.0)
    layers = T.build_stack(n_tiers=2)
    zc = zcells(layers, 1.0)
    acc, ztier, zlog = 0.0, [], None
    for nm, d in zc:
        if nm == 'SRAM_tier': ztier.append(acc + d/2)
        if nm == 'logic': zlog = acc + d/2
        acc += d
    zt = ztier[-1]                                  # upper tier mid-plane
    lsb = 2*6
    L = []; A = L.append
    A('! ---------------- visualisation: all output is MAPDL graphics ----------------')
    A('*GET,NSETS,ACTIVE,0,SET,NSET')
    A(f'SET,{lsb},LAST')
    A('CMSEL,S,TIER $ NSLE,S $ NSORT,TEMP $ *GET,NHOT,SORT,0,IMAX $ ALLSEL,ALL')
    A(f'NARR=NODE({ARRAY[0]/2:.9e},{ARRAY[1]/2:.9e},{zt:.9e})')
    A(f'NLOG=NODE(NX(NHOT),NY(NHOT),{zlog:.9e})')
    A('/SHOW,PNG'); A('/GFILE,1800')
    A('/RGB,INDEX,100,100,100,0'); A('/RGB,INDEX,80,80,80,13')
    A('/RGB,INDEX,60,60,60,14'); A('/RGB,INDEX,0,0,0,15')
    A('/PLOPTS,INFO,3 $ /PLOPTS,FRAME,0 $ /PLOPTS,LOGO,1 $ /PLOPTS,DATE,0'); A('/TRIAD,LTOP')
    # 1. whole unit cell, isometric, mesh edges visible
    A('/VIEW,1,1,-1.6,0.9 $ /ANG,1 $ /AUTO,1 $ /EDGE,1,1')
    A('/TITLE, C2 macro unit cell 153 x 518 um: temperature at the end of a burst [C]')
    A('PLNSOL,TEMP')
    # 2. the tier plane from above: the L-shaped periphery hotspot
    A('/EDGE,1,0 $ /VIEW,1,0,0,1 $ /ANG,1 $ /AUTO,1')
    A('CMSEL,S,TIER $ NSLE,S')
    A('/TITLE, Tier plane from above: periphery (L) versus array [C]')
    A('PLNSOL,TEMP')
    A('ALLSEL,ALL')
    # 3. top 20 um, isometric, mesh visible -- tier inside the BEOL
    A(f'ESEL,S,CENT,Z,{acc-2.0e-5:.9e},{acc*1.001:.9e}')
    A('NSLE,S')
    A('/VIEW,1,1,-1.6,0.9 $ /ANG,1 $ /AUTO,1 $ /EDGE,1,1')
    A('/TITLE, Top 20 um: tiers in the BEOL above the logic [C]')
    A('PLNSOL,TEMP')
    A('ALLSEL,ALL')
    A('/SHOW,CLOSE')
    A('FINISH')
    # 4. time history, drawn by POST26
    A('/POST26')
    A('NUMVAR,20')
    A('NSOL,2,NHOT,TEMP,,T_PERI')
    A('NSOL,3,NARR,TEMP,,T_ARRAY')
    A('NSOL,4,NLOG,TEMP,,T_LOGIC')
    A('/SHOW,PNG'); A('/GFILE,1800')
    A('/RGB,INDEX,100,100,100,0'); A('/RGB,INDEX,0,0,0,15')
    A('/PLOPTS,INFO,3 $ /PLOPTS,LOGO,1 $ /PLOPTS,DATE,0')
    A('/AXLAB,X,Time  (s)'); A('/AXLAB,Y,Temperature  (C)')
    A('/GRID,1')
    A('/TITLE, Duty-cycled transient: 6 periods of 4.515 ms, burst 216.7 us (4.80%)')
    A('PLVAR,2,3,4')
    A('/SHOW,CLOSE')
    A('*DIM,TT,ARRAY,NSETS $ *DIM,TP,ARRAY,NSETS $ *DIM,TA,ARRAY,NSETS $ *DIM,TL,ARRAY,NSETS')
    A('VGET,TT(1),1 $ VGET,TP(1),2 $ VGET,TA(1),3 $ VGET,TL(1),4')
    A('*CFOPEN,history,txt')
    A('*VWRITE,TT(1),TP(1),TA(1),TL(1)')
    A('(4E18.9)')
    A('*CFCLOS')
    A('FINISH')
    return body + '\n'.join(L) + '\n', info
