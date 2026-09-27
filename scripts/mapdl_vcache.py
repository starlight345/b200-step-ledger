#!/usr/bin/env python3
"""The macro-resolved MAPDL transient (mapdl_macro.py) on the shipping V-Cache stack.

Same C2 macro unit cell, same duty-cycled load, same six periods from the duty-averaged steady
state; only the stack changes, to hb_stack_check.vcache_stack('F2B'): the SRAM die hybrid-
bonded face-to-back under the logic die, 6 um of SRAM silicon, 750 um of dummy silicon on
top. The periphery-concentration sweep is what the abstract's "heat is not the limit" claim
rests on, so it is repeated here for the new stack.

  verify          tier power only, uniform, sink face held at 0: must reproduce the 1D
                  solver. The reference is our 1D model stepped EXACTLY as the deck steps
                  (duty-averaged steady start, 16 backward-Euler substeps per burst, 30 per
                  off-phase, six periods), so the comparison isolates the 3D mesh.
  prod_phiU       logic at 349.35 W/die, tier bursts uniform over the macro
  prod_phi90      90% of the tier power in the 28.5%-area L-shaped periphery
  prod_k10_phi90  the same with BEOL kxy/kz = 10

The sink film coefficient is recalibrated so the logic junction sits at 100 C with this
stack (sink_h in mapdl_representative is calibrated on the BEOL stack's Si + TIM).

  python3 scripts/mapdl_vcache.py            # writes decks + run script, prints the reference
  python3 scripts/mapdl_vcache.py --push     # also copies them to the server and starts the run
  python3 scripts/mapdl_vcache.py --fetch    # pulls results.txt and tabulates
"""
import os, sys, subprocess, re, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_stack_solver as T
import hb_stack_check as HB
import mapdl_macro as MM
from mapdl_representative import T_BULK_C, T_JUNC_TGT_C

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets', 'mapdl', 'vcache')
SERVER, REMOTE = 'dsil-sy', '~/ectc_thermal/vcache'
NPER, SUB_ON, SUB_OFF = 6, 16, 30          # mapdl_macro.deck defaults

HB.use_device(HB.SI)
LAYERS = HB.vcache_stack('F2B')

def sink_h_vcache():
    """h that puts the logic junction at T_JUNC_TGT_C: everything between the logic layer and
    the outer face (logic-die Si, bond, dummy Si, TIM) carries part of the rise."""
    below = []
    for name, t in LAYERS:
        if name == 'logic': break
        below.append((name, t))
    r_stack = sum(t/T.MAT[n][0] for n, t in below)/T.DIE_AREA_M2
    p_total = MM.P_LOGIC_DIE + MM.Q_BURST_DIE*T.DUTY
    r_conv = (T_JUNC_TGT_C - T_BULK_C)/p_total - r_stack
    return 1.0/(r_conv*T.DIE_AREA_M2), r_stack, r_conv

CASES = [('verify', dict(mode='verify')),
         ('prod_phiU', dict(mode='prod')),
         ('prod_phi90', dict(mode='prod', phi=0.9)),
         ('prod_k10_phi90', dict(mode='prod', phi=0.9, kxy_over_kz=10.0))]

def replica_verify():
    """Our 1D model stepped as the verify deck steps: steady at the duty-averaged tier power,
    then NPER periods of SUB_ON backward-Euler steps over each burst and SUB_OFF over each
    off-phase; the tier maximum at the end of the last burst (the deck's TPK) and at the end
    of the previous one (TPKP). Sink face at 0, tier power only, W per die."""
    dz, k, rc, tag = T.discretise(LAYERS, 0.5e-6, 80)
    n = len(dz); G = np.zeros(n+1)
    for i in range(1, n):
        G[i] = 1.0/(dz[i-1]/(2*k[i-1]) + dz[i]/(2*k[i]))
    G[0] = 1.0/(dz[0]/(2*k[0]))
    A = np.diag(G[:n] + G[1:])
    for i in range(1, n):
        A[i, i-1] = A[i-1, i] = -G[i]
    C = rc*dz
    tier = [i for i, t in enumerate(tag) if t == 'SRAM_tier']
    s = np.zeros(n); s[tier] = MM.Q_BURST_DIE/T.DIE_AREA_M2/len(tier)
    Tn = np.linalg.solve(A, s*T.DUTY)
    tp, P = T.DUTY*T.PERIOD, T.PERIOD
    steps = {}
    for dt in (tp/SUB_ON, (P - tp)/SUB_OFF):
        steps[dt] = np.linalg.inv(np.diag(C/dt) + A)
    peaks = []
    for _ in range(NPER):
        dt = tp/SUB_ON
        for _ in range(SUB_ON): Tn = steps[dt] @ (C/dt*Tn + s)
        peaks.append(Tn[tier].max())
        dt = (P - tp)/SUB_OFF
        for _ in range(SUB_OFF): Tn = steps[dt] @ (C/dt*Tn)
    return peaks[-1], peaks[-2]

def write():
    os.makedirs(OUT, exist_ok=True)
    h, r_stack, r_conv = sink_h_vcache()
    names = []
    for name, kw in CASES:
        body, info = MM.deck(tag=name, layers=LAYERS, h=h, **kw)
        open(os.path.join(OUT, name + '.dat'), 'w').write(body)
        names.append(name)
        print(f"{name:<16} {info['nel']:>7} el  phi={info['phi']:.3f}")
    run = ['#!/bin/bash',
           'B=/TOOLS/SYNOPSYS/RedHawk-SC_Electrothermal_Linux64e8_Y-2026.03-SP2',
           'export AWP_ROOT261=$B/solver/Mechanical_Engine/v261; export ANSYS261_DIR=$AWP_ROOT261/ansys',
           'export ANSYSLIC_DIR=$B/shared_files/licensing; export ANSYS_SYSDIR=linx64',
           f'cd {REMOTE}', ': > results.txt',
           f'for f in {" ".join(names)}; do',
           '  rm -rf run_$f; mkdir run_$f; cd run_$f; cp ../$f.dat .',
           '  S=$(date +%s); $ANSYS261_DIR/bin/mapdl -b -np 1 -j $f -i $f.dat -o $f.out >/dev/null 2>&1; E=$(date +%s)',
           '  echo "$f $((E-S))s $(grep -h RESULT summary.txt 2>/dev/null) errors=$(grep -c "\\*\\*\\* ERROR" $f.out)" >> ../results.txt',
           '  cd ..', 'done', 'echo DONE >> results.txt']
    open(os.path.join(OUT, 'run_all.sh'), 'w').write('\n'.join(run) + '\n')
    pk, prev = replica_verify()
    ref = dict(h_W_per_m2K=h, r_stack_K_per_W=r_stack, r_conv_K_per_W=r_conv,
               verify_replica_peak_K=pk, verify_replica_prevpeak_K=prev)
    json.dump(ref, open(os.path.join(OUT, 'reference.json'), 'w'), indent=1)
    print(f'sink h {h:.1f} W/m2K (stack below logic {r_stack*1e3:.3f} mK/W, film {r_conv*1e3:.2f} mK/W)')
    print(f'verify reference (our 1D, stepped as the deck): peak {pk:.6f} K, previous period {prev:.6f} K')
    return names

def push():
    subprocess.run(['ssh', SERVER, f'mkdir -p {REMOTE}'], check=True)
    files = [os.path.join(OUT, f) for f in os.listdir(OUT) if f.endswith(('.dat', '.sh'))]
    subprocess.run(['scp', '-q'] + files + [f'{SERVER}:{REMOTE}/'], check=True)
    subprocess.run(['ssh', SERVER, f'cd {REMOTE} && chmod +x run_all.sh && nohup ./run_all.sh > run_all.log 2>&1 &'],
                   check=True)
    print(f'started on {SERVER}:{REMOTE}')

def fetch():
    dst = os.path.join(OUT, 'results.txt')
    subprocess.run(['scp', '-q', f'{SERVER}:{REMOTE}/results.txt', dst], check=True)
    ref = json.load(open(os.path.join(OUT, 'reference.json')))
    rows = {}
    for line in open(dst):
        if not line.startswith(('prod_', 'verify')): continue
        rows[line.split()[0]] = dict((k, float(v)) for k, v in re.findall(r'(\w+)=\s*([-+0-9.E]+)', line))
    if 'verify' in rows:
        v = rows['verify']
        print(f"verify: MAPDL peak {v['peak']:.6f} K vs our 1D stepped the same way {ref['verify_replica_peak_K']:.6f} K "
              f"({(v['peak']/ref['verify_replica_peak_K'] - 1)*100:+.2f}%)")
    for name in ('prod_phiU', 'prod_phi90', 'prod_k10_phi90'):
        if name in rows:
            r = rows[name]
            print(f"{name:<16} tier peak {r['peak']:.4f} C, logic {r['logic']:.4f} C, tier - logic {r['peak'] - r['logic']:.4f} K, "
                  f"swing {r['peak'] - r['trough']:.4f} K, last-period change {abs(r['peak'] - r['prevpeak'])*1e3:.2f} mK")
    return rows

if __name__ == '__main__':
    if '--fetch' in sys.argv:
        fetch()
    else:
        write()
        if '--push' in sys.argv:
            push()
