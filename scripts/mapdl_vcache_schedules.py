#!/usr/bin/env python3
"""The V-Cache macro model (mapdl_vcache.py) fed the way the literature feeds it, and fed the
decode step's own schedule.

Two questions the one-block transient runs of mapdl_vcache.py leave open.

1. What does the SAME Ansys model answer when its input is a static map? The static decks
   solve three steady states on the production model (logic 349 W/die, sink calibrated to a
   100 C junction): logic only; logic + tier at the duty-averaged power (the static-average
   map: Tasa, DeepStack, Sharda JXCDC'25, imec IEDM'25's Icepak steady state); logic + tier
   at the burst power held on (the static-peak map: Stratum Eq.1, Helios, A3D-MoE's Ansys
   Mechanical at maximum power). Their tier rises, against the transient's, are the 3D
   version of the sota_comparators table.

2. Does burst_shape.py's placement result hold in 3D, where 90% of the tier power sits in the
   28.5% periphery? The schedule decks drive the tier kernel by kernel with burst_shape's
   schedules instead of one block: S1 (the Gate-1 LIP placement, layers 0-9) and S3 (one down
   projection per layer), both with 1.5 us per kernel and the rest of t0 as a host gap.
   s1_verify (tier only, uniform, sink face at 0) must reproduce our 1D model stepped exactly
   as the deck steps, as mapdl_vcache's verify does for one block.

  python3 scripts/mapdl_vcache_schedules.py            # decks + 1D reference
  python3 scripts/mapdl_vcache_schedules.py --push     # copy to the server, run four at a time
  python3 scripts/mapdl_vcache_schedules.py --fetch    # pull results and tabulate
"""
import os, sys, math, json, re, subprocess
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_stack_solver as T
import mapdl_macro as MM
import mapdl_vcache as MV
import burst_shape as BS
import sota_comparators as SC
from mapdl_representative import T_BULK_C

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets', 'mapdl', 'vcache_sched')
SERVER, REMOTE = 'dsil-sy', '~/ectc_thermal/vcache_sched'
NPER = 6
PERI_UNIFORM = MM.PERI_AREA_FRAC        # phi of a uniform tier (the periphery's area share)

def nsub(d, q):
    """Substeps for one schedule segment: <= 2 us while the tier is on, coarser while off."""
    if q > 0: return max(2, math.ceil(d/2e-6 - 1e-9))
    if d <= 20e-6: return max(1, math.ceil(d/5e-6 - 1e-9))
    if d <= 200e-6: return max(4, math.ceil(d/25e-6 - 1e-9))
    return 30

def _prep(mode, phi):
    h = MV.sink_h_vcache()[0]
    body, info = MM.deck(mode=mode, phi=phi, layers=MV.LAYERS, h=h)
    i = body.index('/SOLU')
    zc = MM.zcells(MV.LAYERS)
    t_logic = sum(d for nm, d in zc if nm == 'logic')
    hg_log = MM.P_LOGIC_DIE/(T.DIE_AREA_M2*t_logic) if mode == 'prod' else 0.0
    return body[:i], info, h, hg_log

def _loads(A, qa, qp, ql):
    A(f'CMSEL,S,TIER_ARR $ BFE,ALL,HGEN,,{qa:.9e}')
    A(f'CMSEL,S,TIER_PER $ BFE,ALL,HGEN,,{qp:.9e}')
    A(f'CMSEL,S,LOGIC $ BFE,ALL,HGEN,,{ql:.9e}')
    A('ALLSEL,ALL')

def _grab(A, ls, comp, var, how='MAX'):
    A(f'SET,{ls},LAST')
    A(f'CMSEL,S,{comp} $ NSLE,S $ NSORT,TEMP')
    A(f'*GET,{var},SORT,0,{how}')
    A('ALLSEL,ALL')

def static_deck(phi, lid=False):
    """Three steady states: logic only, + tier at the average power, + tier at the burst power.
    lid=True: the ideal-lid boundary of the 1D tables instead -- tier power only, sink face at 0."""
    prep, info, h, hg_log = _prep('verify' if lid else 'prod', phi)
    L = [prep]; A = L.append
    qa, qp = info['hg_arr_on'], info['hg_per_on']
    A('/SOLU'); A('ANTYPE,STATIC')
    A('CMSEL,S,SINK'); A('D,ALL,TEMP,0' if lid else f'SF,ALL,CONV,{h:.9e},{T_BULK_C:.6g}'); A('ALLSEL,ALL')
    for ls, f in ((1, 0.0), (2, T.DUTY), (3, 1.0)):
        _loads(A, qa*f, qp*f, hg_log); A(f'TIME,{ls}'); A('SOLVE')
    A('FINISH'); A('/POST1')
    for ls in (1, 2, 3):
        _grab(A, ls, 'TIER', f'TT{ls}'); _grab(A, ls, 'TIER', f'TN{ls}', 'MIN'); _grab(A, ls, 'LOGIC', f'TL{ls}')
    A('/OUT,summary,txt')
    A('*VWRITE,TT1,TN1,TL1,TT2,TN2,TL2,TT3,TN3,TL3')
    A("('RESULT tier1=',E16.9,' tiermin1=',E16.9,' logic1=',E16.9,' tier2=',E16.9,' tiermin2=',E16.9,"
      "' logic2=',E16.9,' tier3=',E16.9,' tiermin3=',E16.9,' logic3=',E16.9)")
    A('/OUT'); A('FINISH')
    return '\n'.join(L) + '\n', info

def schedule_deck(segs, mode, phi):
    """Periodic transient driven segment by segment (one load step each), from the steady state
    at the average power, NPER periods. The peak is the largest tier value at any segment end
    of the last period (the last substep of each load step is kept)."""
    prep, info, h, hg_log = _prep(mode, phi)
    L = [prep]; A = L.append
    s = 1.0/BS.P_BURST                       # schedule watts -> fraction of the burst heat rates
    qa, qp = info['hg_arr_on'], info['hg_per_on']
    avg = sum(d*q for d, q in segs)/sum(d for d, _ in segs)
    A('/SOLU'); A('ANTYPE,TRANS'); A('TRNOPT,FULL'); A('KBC,1'); A('AUTOTS,OFF')
    A('OUTRES,ERASE'); A('OUTRES,NSOL,LAST')
    A(f'TUNIF,{(T_BULK_C if mode == "prod" else 0.0):.6g}')
    A('CMSEL,S,SINK')
    A(f'SF,ALL,CONV,{h:.9e},{T_BULK_C:.6g}' if mode == 'prod' else 'D,ALL,TEMP,0')
    A('ALLSEL,ALL')
    _loads(A, qa*avg*s, qp*avg*s, hg_log)
    A('TIMINT,OFF'); A('TIME,1e-6'); A('NSUBST,1'); A('SOLVE')
    A('TIMINT,ON')
    t = 1e-6                                 # unrolled: every load step's end time written out
    for _ in range(NPER):
        for d, q in segs:
            t += d
            _loads(A, qa*q*s, qp*q*s, hg_log)
            A(f'TIME,{t:.12e}'); A(f'NSUBST,{nsub(d, q)}'); A('SOLVE')
    A('FINISH')
    nseg = len(segs)
    A('/POST1')
    for tag, p in (('P', NPER), ('Q', NPER - 1)):
        A(f'TPK{tag}=-1e30'); A(f'LPK{tag}=0')
        A(f'*DO,LSI,{2 + (p - 1)*nseg},{1 + p*nseg}')
        A('SET,LSI,LAST'); A('CMSEL,S,TIER $ NSLE,S $ NSORT,TEMP'); A('*GET,TMX_,SORT,0,MAX'); A('ALLSEL,ALL')
        A(f'*IF,TMX_,GT,TPK{tag},THEN'); A(f'TPK{tag}=TMX_'); A(f'LPK{tag}=LSI'); A('*ENDIF')
        A('*ENDDO')
    A('SET,LPKP,LAST'); A('CMSEL,S,LOGIC $ NSLE,S $ NSORT,TEMP'); A('*GET,TLG,SORT,0,MAX'); A('ALLSEL,ALL')
    A('SET,LPKP,LAST'); A('CMSEL,S,TIER $ NSLE,S $ NSORT,TEMP'); A('*GET,TPKMIN,SORT,0,MIN'); A('ALLSEL,ALL')
    _grab(A, 1, 'TIER', 'TMEAN')
    A('LSLAST=LPKP')
    A('/OUT,summary,txt')
    A('*VWRITE,TPKP,TPKQ,TLG,TPKMIN,TMEAN,LSLAST')
    A("('RESULT peak=',E16.9,' prevpeak=',E16.9,' logic=',E16.9,' peakmin=',E16.9,' mean=',E16.9,"
      "' ls=',F8.0)")
    A('/OUT'); A('FINISH')
    return '\n'.join(L) + '\n', info

def replica(segs):
    """Our 1D model (tier only, sink at 0) stepped exactly as a schedule deck steps: steady at
    the average power, then NPER periods, each segment in nsub() backward-Euler substeps.
    Returns the largest tier value at segment ends in the last and the previous period (K)."""
    dz, k, rc, tag = T.discretise(MV.LAYERS, 0.5e-6, 80)
    n = len(dz); G = np.zeros(n + 1)
    for i in range(1, n): G[i] = 1.0/(dz[i-1]/(2*k[i-1]) + dz[i]/(2*k[i]))
    G[0] = 1.0/(dz[0]/(2*k[0]))
    A = np.diag(G[:n] + G[1:])
    for i in range(1, n): A[i, i-1] = A[i-1, i] = -G[i]
    C = rc*dz
    tier = [i for i, t in enumerate(tag) if t == 'SRAM_tier']
    src = np.zeros(n); src[tier] = 1.0/T.DIE_AREA_M2/len(tier)
    avg = sum(d*q for d, q in segs)/sum(d for d, _ in segs)
    Tn = np.linalg.solve(A, src*avg)
    inv = {}
    peaks = []
    for _ in range(NPER):
        pk = -1e30
        for d, q in segs:
            m = nsub(d, q); dt = d/m
            key = round(dt, 15)
            if key not in inv: inv[key] = np.linalg.inv(np.diag(C/dt) + A)
            for _ in range(m): Tn = inv[key] @ (C/dt*Tn + src*q)
            pk = max(pk, Tn[tier].max())
        peaks.append(pk)
    return peaks[-1], peaks[-2]

CASES = [('static_phiU', 'static', None, None),
         ('static_phi90', 'static', 0.9, None),
         ('s1_verify', 'verify', None, ('S1', 'mixed')),
         ('s1_phiU', 'prod', None, ('S1', 'mixed')),
         ('s1_phi90', 'prod', 0.9, ('S1', 'mixed')),
         ('s3_phi90', 'prod', 0.9, ('S3', 'mixed'))]
# second batch: the upper corner of burst sensitivity -- ideal lid AND 90% periphery concentration
LID = [('lid_static_phi90', 'static-lid', 0.9, None),
       ('lid_s0_phi90', 'verify', 0.9, ('S0', 'mixed')),
       ('lid_s1_phi90', 'verify', 0.9, ('S1', 'mixed'))]
# third batch: where between uniform and 90% does the ideal-lid corner cross the 19 TB/s fabric cap?
# One-block runs are repeated here at uniform and 90% so every S0 row uses the same substeps.
PHI = ([(f'static_phi{int(p*100)}', 'static', p, None) for p in (0.5, 0.7)] +
       [(f'lid_static_phi{int(p*100)}', 'static-lid', p, None) for p in (0.5, 0.7)] +
       [('lid_static_phiU', 'static-lid', None, None)] +
       [(f'{b}_{s.lower()}_phi{"U" if p is None else int(p*100)}', 'verify' if b == 'lid' else 'prod', p, (s, 'mixed'))
        for b in ('lid', 'prod') for s in ('S0', 'S1') for p in (None, 0.5, 0.7, 0.9)
        if not (b == 'lid' and s == 'S1' and p in (None, 0.9)) and not (b == 'prod' and s == 'S1' and p in (None, 0.9))
        and not (b == 'lid' and s == 'S0' and p == 0.9)])

def write(cases=CASES, script='run_all.sh', par=4):
    os.makedirs(OUT, exist_ok=True)
    rp = os.path.join(OUT, 'reference.json')
    ref = json.load(open(rp)) if os.path.exists(rp) else {}
    for name, mode, phi, sch in cases:
        if mode.startswith('static'):
            body, info = static_deck(phi, lid=(mode == 'static-lid'))
        else:
            segs = BS.schedule(*sch)
            body, info = schedule_deck(segs, mode, phi)
            nsubs = sum(nsub(d, q) for d, q in segs)
            print(f'{name:<14} {len(segs):>4} segments/period, {nsubs} substeps/period')
            if mode == 'verify' and phi is None:
                pk, prev = replica(segs)
                ref[name] = dict(replica_peak_K=pk, replica_prevpeak_K=prev)
                print(f'  1D stepped as the deck: peak {pk:.6f} K, previous period {prev:.6f} K')
        open(os.path.join(OUT, name + '.dat'), 'w').write(body)
        print(f"{name:<14} {info['nel']:>7} el  phi={info['phi']:.3f}")
    # the exact 1D answers for the same schedules, per watt of burst -> peak fraction
    HBm = BS.HB; HBm.use_device(HBm.SI)
    mod = SC.Modal(MV.LAYERS, T.DIE_AREA_M2)
    for key in (('S0', 'mixed'), ('S1', 'mixed'), ('S3', 'mixed')):
        ref['exact_pf_' + key[0]] = BS.periodic_peak(mod, BS.schedule(*key))[0]/(mod.R*BS.P_BURST)
    ref['R_K_per_W'] = mod.R
    json.dump(ref, open(rp, 'w'), indent=1)
    res = 'results.txt' if script == 'run_all.sh' else script.replace('.sh', '.txt')
    run = ['#!/bin/bash',
           'B=/TOOLS/SYNOPSYS/RedHawk-SC_Electrothermal_Linux64e8_Y-2026.03-SP2',
           'export AWP_ROOT261=$B/solver/Mechanical_Engine/v261; export ANSYS261_DIR=$AWP_ROOT261/ansys',
           'export ANSYSLIC_DIR=$B/shared_files/licensing; export ANSYS_SYSDIR=linx64',
           f'cd {REMOTE}', f': > {res}',
           'one() { f=$1; rm -rf run_$f; mkdir run_$f; cd run_$f; cp ../$f.dat .;',
           '  S=$(date +%s); $ANSYS261_DIR/bin/mapdl -b -np 1 -j $f -i $f.dat -o $f.out >/dev/null 2>&1; E=$(date +%s)',
           f'  echo "$f $((E-S))s $(grep -h RESULT summary.txt 2>/dev/null) errors=$(grep -c "\\*\\*\\* ERROR" $f.out)" >> ../{res}; }}',
           f'export -f one; export ANSYS261_DIR',
           f'printf "%s\\n" {" ".join(n for n, *_ in cases)} | xargs -P {par} -I{{}} bash -c "one {{}}"',
           f'echo DONE >> {res}']
    open(os.path.join(OUT, script), 'w').write('\n'.join(run) + '\n')
    return ref

def push(cases=CASES, script='run_all.sh'):
    subprocess.run(['ssh', SERVER, f'mkdir -p {REMOTE}'], check=True)
    files = [os.path.join(OUT, n + '.dat') for n, *_ in cases] + [os.path.join(OUT, script)]
    subprocess.run(['scp', '-q'] + files + [f'{SERVER}:{REMOTE}/'], check=True)
    subprocess.run(['ssh', SERVER, f'cd {REMOTE} && chmod +x {script} && '
                    f'(nohup ./{script} > {script}.log 2>&1 < /dev/null &)'], check=True)
    print(f'started on {SERVER}:{REMOTE}')

def parse(path):
    rows = {}
    for line in open(path):
        if 'RESULT' not in line: continue
        rows[line.split()[0]] = dict((k, float(v)) for k, v in re.findall(r'(\w+)=\s*([-+0-9.E]+)', line))
    return rows

def fetch():
    dst = os.path.join(OUT, 'results.txt')
    subprocess.run(['scp', '-q', f'{SERVER}:{REMOTE}/results.txt', dst], check=True)
    ref = json.load(open(os.path.join(OUT, 'reference.json')))
    rows = parse(dst)
    one = parse(os.path.join(HERE, '..', 'assets', 'mapdl', 'vcache', 'results.txt'))
    if 's1_verify' in rows:
        v, r = rows['s1_verify'], ref['s1_verify']
        print(f"s1_verify: MAPDL peak {v['peak']:.6f} K vs our 1D stepped the same way {r['replica_peak_K']:.6f} K "
              f"({(v['peak']/r['replica_peak_K'] - 1)*100:+.2f}%); last-period change "
              f"{abs(v['peak'] - v['prevpeak'])*1e3:.3f} mK")
    out = {}
    for ph in ('U', '90'):
        st = rows.get(f'static_phi{ph}')
        if not st: continue
        base, avg, peak = st['tier1'], st['tier2'], st['tier3']
        d_peak, d_avg = peak - base, avg - base
        print(f"\nphi {ph}: steady tier max, logic only {base:.4f} C | + average power {avg:.4f} C "
              f"(tier rise {d_avg*1e3:.2f} mK) | + burst power held {peak:.4f} C (tier rise {d_peak*1e3:.1f} mK)")
        tab = [('static-peak map (Stratum Eq.1, A3D-MoE Ansys at max)', d_peak),
               ('static-average map (Tasa, DeepStack, imec Icepak steady)', d_avg)]
        tr = {'one block (all models so far)': one.get(f'prod_phi{ph}'),
              'S1 Gate-1 placement, kernel by kernel': rows.get(f's1_phi{ph}'),
              'S3 one down projection per layer': rows.get(f's3_phi{ph}')}
        for lab, r in tr.items():
            if r: tab.append((f'transient, {lab}', r['peak'] - base))
        res = {}
        for lab, d in tab:
            pf = d/d_peak
            res[lab] = dict(tier_rise_K=d, peak_fraction=pf, TBs=5.0/pf)
            print(f'  {lab:<58} tier rise {d*1e3:>7.2f} mK  peak fraction {pf:.4f}  -> {5.0/pf:>6.1f} TB/s')
        out[f'phi{ph}'] = res
    lid_path = os.path.join(OUT, 'run_lid.txt')
    subprocess.run(['scp', '-q', f'{SERVER}:{REMOTE}/run_lid.txt', lid_path])
    if os.path.exists(lid_path):
        lid = parse(lid_path); rows.update(lid)
        st = lid.get('lid_static_phi90')
        if st:
            d_peak = st['tier3']
            print(f"\nideal lid (sink face at 0, tier power only), phi 90: burst power held -> tier rise {d_peak*1e3:.1f} mK")
            res = {}
            for lab, key in (('static-average map', None), ('transient, one block', 'lid_s0_phi90'),
                             ('transient, S1 Gate-1 placement', 'lid_s1_phi90')):
                d = st['tier2'] if key is None else lid.get(key, {}).get('peak')
                if d is None: continue
                pf = d/d_peak; res[lab] = dict(tier_rise_K=d, peak_fraction=pf, TBs=5.0/pf)
                print(f'  {lab:<58} tier rise {d*1e3:>7.2f} mK  peak fraction {pf:.4f}  -> {5.0/pf:>6.1f} TB/s')
            out['lid_phi90'] = res
    print('\n1D exact peak fractions for the same schedules (burst_shape.py): ' +
          ', '.join(f"{k[9:]} {v:.4f}" for k, v in ref.items() if k.startswith('exact_pf_')))
    json.dump(dict(rows=rows, table=out, reference=ref), open(os.path.join(OUT, 'summary.json'), 'w'), indent=1)
    return rows

def phi_table():
    """The periphery-concentration sweep (PHI batch plus the matching runs of the first two batches):
    peak fraction and TB/s for the ideal lid and the production film, one block and the Gate-1
    schedule, and where the ideal-lid one-block corner crosses the 19 TB/s fabric cap."""
    dst = os.path.join(OUT, 'run_phi.txt')
    subprocess.run(['scp', '-q', f'{SERVER}:{REMOTE}/run_phi.txt', dst], check=True)
    R = parse(dst)
    for f in ('results.txt', 'run_lid.txt'):
        R.update(parse(os.path.join(OUT, f)))
    tab = {}
    for ph, tag in ((PERI_UNIFORM, 'U'), (0.5, '50'), (0.7, '70'), (0.9, '90')):
        ls, ps, row = R.get(f'lid_static_phi{tag}'), R.get(f'static_phi{tag}'), {}
        if ls:
            for sch, key in (('S0', f'lid_s0_phi{tag}'), ('S1', 's1_verify' if tag == 'U' else f'lid_s1_phi{tag}')):
                if key in R: row[f'lid/{sch}'] = R[key]['peak']/ls['tier3']
        if ps:
            d = ps['tier3'] - ps['tier1']
            for sch, key in (('S0', f'prod_s0_phi{tag}'), ('S1', {'U': 's1_phiU', '90': 's1_phi90'}.get(tag, f'prod_s1_phi{tag}'))):
                if key in R: row[f'prod/{sch}'] = (R[key]['peak'] - ps['tier1'])/d
        tab[ph] = row
    cols = ['lid/S0', 'lid/S1', 'prod/S0', 'prod/S1']
    print(f"{'phi':>6} " + ' '.join(f'{c:>18}' for c in cols))
    for ph, row in tab.items():
        print(f'{ph:>6.3f} ' + ' '.join((f'{row[c]:>7.4f} ({5/row[c]:>5.1f} TB/s)' if c in row else f"{'':>18}")
                                        for c in cols))
    xs = sorted(tab); ys = [tab[x].get('lid/S0') for x in xs]
    cross = float(np.interp(5/19, ys, xs)) if None not in ys and min(ys) < 5/19 < max(ys) else None
    if cross: print(f'ideal lid, one block: below the 19 TB/s fabric cap once the periphery takes > {cross:.2f} of the power')
    json.dump(dict(peak_fraction={f'{k:.3f}': v for k, v in tab.items()}, lid_one_block_crosses_19TBs_at_phi=cross),
              open(os.path.join(OUT, 'phi_sweep.json'), 'w'), indent=1)
    return tab

if __name__ == '__main__':
    if '--fetch' in sys.argv:
        fetch()
    elif '--phi-table' in sys.argv:
        phi_table()
    else:
        batch = ((LID, 'run_lid.sh') if '--lid' in sys.argv else
                 (PHI, 'run_phi.sh') if '--phi' in sys.argv else (CASES, 'run_all.sh'))
        write(*batch, par=8 if '--phi' in sys.argv else 4)
        if '--push' in sys.argv:
            push(*batch)
