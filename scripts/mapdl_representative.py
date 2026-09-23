#!/usr/bin/env python3
"""The representative model: what the tier actually sits on.

The V-1/V-2 decks deliberately ran the tier ALONE against a perfect sink, because their
job was to verify the 1D solver and a verification model has to match the model it
verifies. That is correct practice and it stays. But it means the published pictures show
a tier floating on an isothermal slab, which is not the thing being proposed.

This model is the other half. Three things the verification model leaves out:

  LOGIC POWER      The tier is stacked on a die dissipating 349 W. Our tier-only rise of
                   a fraction of a kelvin is a rise ON TOP OF a ~100 C junction, and that
                   is the number a device engineer needs.
  BEOL ANISOTROPY  BEOL is not a homogeneous low-k slab. It is copper wiring in low-k, so
                   in-plane conduction is far better than through-plane. The verification
                   model is isotropic, which UNDER-states lateral spreading and therefore
                   over-states any hotspot. Swept here, not assumed.
  FINITE SINK      A Dirichlet face is an infinitely good cooler. Replaced by a convection
                   coefficient calibrated so the logic junction lands on the operating
                   point the package is actually known to run at.

Note on what is NOT here: there are no through-silicon vias, and that is not an omission.
TSVs belong to die-to-die stacking. This tier is monolithic in the back end of line of the
same die, so its vertical path is ordinary BEOL via stack, which is what the BEOL layer
already represents.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_stack_solver as T

T_BULK_C     = 40.0      # coolant / ambient reference [scenario]
T_JUNC_TGT_C = 100.0     # operating junction the sink coefficient is calibrated to [scenario]
P_LOGIC_W    = T.P_LOGIC_DIE          # 349.35 W/die [measured package / 2]
DUTY         = T.DUTY

def sink_h(p_total_W, area_m2=T.DIE_AREA_M2):
    """Convection coefficient that puts the junction at T_JUNC_TGT_C for this power.

    The stack from the logic layer down to the outer face carries part of the rise; the
    convection film carries the rest. Solving for h is what 'calibrated boundary
    condition' means here -- the package's operating point is the input, h is the output.
    """
    r_stack = sum(t/T.MAT[n][0] for n, t in T.build_stack()
                  if n in ('Si', 'TIM'))/area_m2          # K/W, logic -> outer face
    dt_total = T_JUNC_TGT_C - T_BULK_C
    r_conv = dt_total/p_total_W - r_stack
    return 1.0/(r_conv*area_m2), r_stack, r_conv

def deck(n_tiers=2, kxy_over_kz=1.0, half_span_um=2000.0, nlat=40,
         area_m2=T.DIE_AREA_M2, plots=False):
    layers = T.build_stack(n_tiers=n_tiers)
    zc = []
    for name, t in layers:
        n = {'TIM': 4, 'Si': 20, 'logic': 1, 'BEOL': 4, 'SRAM_tier': 1}.get(name, 2)
        for _ in range(n): zc.append((name, t/n))
    nz = len(zc)
    z = [0.0]
    for _, d in zc: z.append(z[-1]+d)
    half = half_span_um*1e-6
    dx = half/nlat
    cell_area = (2*half)**2
    scale = (cell_area/area_m2)/4.0          # watts of the die that live in this quarter

    q_tier_avg = T.M.p_burst_W(0.5)/2*DUTY if hasattr(T, 'M') else None
    import ectc_thermal_model as M
    q_tier_avg = M.p_burst_W(0.5)/2*DUTY     # duty-averaged tier power, per die
    p_total = P_LOGIC_W + q_tier_avg
    h, r_stack, r_conv = sink_h(p_total, area_m2)

    t_logic = sum(d for nm, d in zc if nm == 'logic')
    t_tier  = sum(d for nm, d in zc if nm == 'SRAM_tier')
    hgen_logic = P_LOGIC_W*scale/(half*half*t_logic)
    hgen_tier  = q_tier_avg*scale/(half*half*t_tier)

    # materials: BEOL is orthotropic, everything else isotropic
    props, mat_of = {}, []
    for name, d in zc:
        k, rho, cp = T.MAT[name]
        kz = k
        kxy = k*kxy_over_kz if name == 'BEOL' else k
        key = (kxy, kz, rho*cp)
        if key not in props: props[key] = len(props)+1
        mat_of.append(props[key])

    NPL = nz+1
    NPX = (nlat+1)*NPL
    L = []; A = L.append
    A('/BATCH')
    A(f'/TITLE, ECTC representative model, BEOL kxy/kz={kxy_over_kz:g}')
    A('/PREP7')
    A('ET,1,SOLID70')
    for (kxy, kz, rc), mid in sorted(props.items(), key=lambda x: x[1]):
        A(f'MP,KXX,{mid},{kxy:.6g}')
        A(f'MP,KYY,{mid},{kxy:.6g}')
        A(f'MP,KZZ,{mid},{kz:.6g}')
        A(f'MP,DENS,{mid},1.0')
        A(f'MP,C,{mid},{rc:.9g}')
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
    A(f'TUNIF,{T_BULK_C:.6g}')
    A(f'! convection on the outer face, h calibrated so the junction lands at {T_JUNC_TGT_C:.0f} C')
    A(f'NSEL,S,LOC,Z,-1e-9,{z[1]*0.5:.9e}')
    A(f'SF,ALL,CONV,{h:.9e},{T_BULK_C:.6g}')
    A('ALLSEL,ALL')
    def zrange(tag):
        return [(sum(d for _, d in zc[:i]), sum(d for _, d in zc[:i+1]))
                for i, (nm, d) in enumerate(zc) if nm == tag]
    for tag, hg in (('logic', hgen_logic), ('SRAM_tier', hgen_tier)):
        A('ESEL,NONE')
        for za, zb in zrange(tag):
            A(f'ESEL,A,CENT,Z,{za:.9e},{zb:.9e}')
        A(f'BFE,ALL,HGEN,,{hg:.9e}')
    A('ALLSEL,ALL $ SOLVE $ FINISH')
    A('/POST1')
    A('SET,LAST')
    for tag, var in (('logic', 'TLOG'), ('SRAM_tier', 'TTIER')):
        A('ESEL,NONE')
        for za, zb in zrange(tag):
            A(f'ESEL,A,CENT,Z,{za:.9e},{zb:.9e}')
        A('NSLE,S $ NSORT,TEMP')
        A(f'*GET,{var},SORT,0,MAX')
        A('ALLSEL,ALL')
    A('/OUT,summary,txt')
    A('*VWRITE,TLOG,TTIER')
    A("('RESULT logic_max=',E14.7,'  tier_max=',E14.7)")
    A('/OUT')
    if plots:
        A('/SHOW,PNG')
        A('/GFILE,1600')
        A('/RGB,INDEX,100,100,100,0')
        A('/RGB,INDEX,80,80,80,13')
        A('/RGB,INDEX,60,60,60,14')
        A('/RGB,INDEX,0,0,0,15')
        A('/PLOPTS,INFO,3 $ /PLOPTS,FRAME,0 $ /PLOPTS,LOGO,0 $ /PLOPTS,DATE,0')
        A('/TRIAD,OFF')
        A(f'ESEL,S,CENT,Y,0,{2*dx:.9e}')
        A('/VIEW,1,0,-1,0 $ /ANG,1 $ /AUTO,1')
        A('/PNUM,MAT,1 $ /NUMBER,1')
        A('/TITLE, Section mesh: TIM / Si / logic / BEOL / SRAM tier')
        A('EPLOT')
        A('/PNUM,MAT,0 $ /NUMBER,0')
        A(f'/TITLE, Junction temperature [C], coolant {T_BULK_C:.0f} C, logic {P_LOGIC_W:.0f} W')
        A('PLNSOL,TEMP')
        A('! zoom on the top: the tier and the BEOL it sits in')
        A(f'ESEL,R,CENT,Z,{z[-1]-2.0e-5:.9e},{z[-1]*1.001:.9e}')
        A('/AUTO,1')
        A('/TITLE, Top 20 um: the tier inside the BEOL')
        A('PLNSOL,TEMP')
        A('ALLSEL,ALL')
        A('/SHOW,CLOSE')
    A('FINISH')
    return '\n'.join(L)+'\n', dict(h=h, r_stack=r_stack, r_conv=r_conv,
                                   q_tier_avg=q_tier_avg, p_total=p_total)

if __name__ == '__main__':
    out = os.path.join(os.path.dirname(__file__), '..', 'assets', 'mapdl')
    os.makedirs(out, exist_ok=True)
    for ratio in (1.0, 10.0, 50.0):
        body, info = deck(kxy_over_kz=ratio, plots=(ratio == 10.0))
        tag = f'rep_kxy{int(ratio)}'
        open(os.path.join(out, tag+'.dat'), 'w').write(body)
        print(f'{tag}: h = {info["h"]:.0f} W/m2K  (stack {info["r_stack"]*1e3:.2f} mK/W, '
              f'film {info["r_conv"]*1e3:.2f} mK/W), tier avg {info["q_tier_avg"]:.3f} W, '
              f'total {info["p_total"]:.1f} W')
