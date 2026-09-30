#!/usr/bin/env python3
"""MAPDL decks that feed the macro model the practices' inputs, to cross-check the ablation.

temporal_spatial_ablation.py computes every rung of the temporal ladder on a cosine-mode model
that matches the existing MAPDL V-Cache runs to 0.15% (static, one block and kernel-by-kernel
S1/S3). The rungs themselves -- a window-mean trace on the macro-resolved model -- were never
put through MAPDL. These decks do that for the two comparisons the regime map rests on:

  S1 (Gate-1, 1.5 us per kernel), phi 0.9: window-mean traces of 1 ms, 200 us and 20 us.
     MAPDL already has the exact schedule (lid_s1_phi90, s1_phi90) and the uniform one.
  S4 (page slice), phi 0.9 and uniform: the exact schedule, and phi 0.9 with 1 ms windows.
     This is the "spatial beats temporal" case: macro + 1 ms against 1D (uniform) + exact.

Each for the ideal lid ('verify' mode: tier only, sink face at 0) and the production film.
The window grid restarts every period at the phase this model finds worst, and the deck steps
it with mapdl_vcache_schedules.nsub(); the prediction next to each deck is this model stepped
the same way, so the comparison isolates the solver.

  python3 scripts/mapdl_trace_decks.py            # decks + run script + predictions
  python3 scripts/mapdl_trace_decks.py --push     # copy to the server and start (4 in parallel)
  python3 scripts/mapdl_trace_decks.py --fetch    # pull results and compare
"""
import os, sys, json, subprocess
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import temporal_spatial_ablation as TA
import mapdl_vcache_schedules as MS
import burst_shape as BS

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets', 'mapdl', 'vcache_trace')
SERVER, REMOTE = MS.SERVER, '~/ectc_thermal/vcache_trace'
PKG = {'lid': ('ideal lid', 'verify', 0.0), 'prod': ('production deck', 'prod', TA.R_EXT_PROD)}

def cases():
    out = []
    for b in ('lid', 'prod'):
        for w in (1e-3, 200e-6, 20e-6):
            out.append((f'{b}_s1_phi90_w{w*1e6:g}us', b, 0.9, 'S1', w))
        out.append((f'{b}_s4_phi90_exact', b, 0.9, 'S4', None))
        out.append((f'{b}_s4_phiU_exact', b, None, 'S4', None))
        out.append((f'{b}_s4_phi90_w1000us', b, 0.9, 'S4', 1e-3))
    return out

def segments(cell, phi, sch, w):
    """The deck's schedule in W per die, and the model's cell rows for the prediction."""
    segs = BS.schedule(sch, 'mixed')
    S = cell.uniform(1.0) if phi is None else cell.source(phi, 1.0)
    mod = TA.Mod(cell.lam, S)
    red = TA.reduce_rows(mod, np.argsort(-mod.phi.sum(axis=1))[:6])
    if w is None:
        return segs, red, None
    s = [(d, q/BS.P_BURST) for d, q in segs]
    phases = np.arange(8)*w/8
    worst = max(phases, key=lambda ph: TA.window_end_peak(red, TA.binned(s, w, ph)))
    return [(d, q*BS.P_BURST) for d, q in TA.binned(s, w, worst)], red, float(worst)

def write():
    os.makedirs(OUT, exist_ok=True)
    cells = {b: TA.Cell(r) for b, (_, _, r) in PKG.items()}
    ref = {}
    for name, b, phi, sch, w in cases():
        segs, red, ph = segments(cells[b], phi, sch, w)
        body, info = MS.schedule_deck(segs, PKG[b][1], phi)
        open(os.path.join(OUT, name + '.dat'), 'w').write(body)
        pred = TA.stepped_schedule(red, segs)*MS.MM.Q_BURST_DIE        # K at 38 W/die, as the decks
        ref[name] = dict(model_stepped_K=pred, phase_s=ph, n_segments=len(segs),
                         substeps=sum(MS.nsub(d, q) for d, q in segs))
        print(f'{name:<24} {len(segs):>4} segs {ref[name]["substeps"]:>5} substeps/period  '
              f'model (stepped as the deck) {pred:.5f} K')
    json.dump(ref, open(os.path.join(OUT, 'reference.json'), 'w'), indent=1)
    names = [c[0] for c in cases()]
    run = ['#!/bin/bash',
           'B=/TOOLS/SYNOPSYS/RedHawk-SC_Electrothermal_Linux64e8_Y-2026.03-SP2',
           'export AWP_ROOT261=$B/solver/Mechanical_Engine/v261; export ANSYS261_DIR=$AWP_ROOT261/ansys',
           'export ANSYSLIC_DIR=$B/shared_files/licensing; export ANSYS_SYSDIR=linx64',
           f'cd {REMOTE}', ': > results.txt',
           'one() { f=$1; rm -rf run_$f; mkdir run_$f; cd run_$f; cp ../$f.dat .;',
           '  S=$(date +%s); $ANSYS261_DIR/bin/mapdl -b -np 1 -j $f -i $f.dat -o $f.out >/dev/null 2>&1; E=$(date +%s)',
           '  echo "$f $((E-S))s $(grep -h RESULT summary.txt 2>/dev/null) errors=$(grep -c "\\*\\*\\* ERROR" $f.out)" >> ../results.txt; }',
           'export -f one; export ANSYS261_DIR',
           f'printf "%s\\n" {" ".join(names)} | xargs -P 4 -I{{}} bash -c "one {{}}"',
           'echo DONE >> results.txt']
    open(os.path.join(OUT, 'run_all.sh'), 'w').write('\n'.join(run) + '\n')
    print(f'wrote {len(names)} decks and run_all.sh to {os.path.relpath(OUT)}')

def push():
    subprocess.run(['ssh', SERVER, f'mkdir -p {REMOTE}'], check=True)
    files = [os.path.join(OUT, c[0] + '.dat') for c in cases()] + [os.path.join(OUT, 'run_all.sh')]
    subprocess.run(['scp', '-q'] + files + [f'{SERVER}:{REMOTE}/'], check=True)
    subprocess.run(['ssh', SERVER, f'cd {REMOTE} && chmod +x run_all.sh && '
                    '(nohup ./run_all.sh > run_all.log 2>&1 < /dev/null &)'], check=True)
    print(f'started on {SERVER}:{REMOTE}')

def fetch():
    dst = os.path.join(OUT, 'results.txt')
    if '--local' not in sys.argv:
        subprocess.run(['scp', '-q', f'{SERVER}:{REMOTE}/results.txt', dst], check=True)
    rows = MS.parse(dst)
    old = TA.mapdl_rows()
    ref = json.load(open(os.path.join(OUT, 'reference.json')))
    base = old['static_phiU']['tier1']                    # logic-only tier temperature, prod
    rise = lambda b, r: r['peak'] - (0.0 if b == 'lid' else base)
    print(f"{'deck':>24} {'MAPDL K':>9} {'model K':>9} {'diff':>7}")
    for name, b, *_ in cases():
        if name in rows:
            m = rise(b, rows[name]); p = ref[name]['model_stepped_K']
            print(f'{name:>24} {m:>9.5f} {p:>9.5f} {(p/m - 1)*100:>+6.2f}%')
    # the comparisons themselves, all in MAPDL: B_max(method)/B_max(reference) = rise_ref / rise_method
    print('\nMAPDL-only ratios (>1: the method is optimistic about the allowable E/bit)')
    for b, ex_s1 in (('lid', 'lid_s1_phi90'), ('prod', 's1_phi90')):
        exact = rise(b, old[ex_s1]) if ex_s1 in old else None
        for w in ('1000', '200', '20'):
            n = f'{b}_s1_phi90_w{w}us'
            if exact and n in rows:
                print(f'  {b:<5} S1 phi 0.9, {w:>5} us trace vs exact: {exact/rise(b, rows[n]):.3f}')
        e4, u4, t4 = (rows.get(f'{b}_s4_phi90_exact'), rows.get(f'{b}_s4_phiU_exact'),
                      rows.get(f'{b}_s4_phi90_w1000us'))
        if e4 and t4:
            print(f'  {b:<5} S4 phi 0.9, macro + 1 ms trace vs exact: {rise(b, e4)/rise(b, t4):.3f}')
        if e4 and u4:
            print(f'  {b:<5} S4 phi 0.9, uniform (1D-equivalent) + exact vs exact: {rise(b, e4)/rise(b, u4):.3f}')
    return rows

if __name__ == '__main__':
    if '--fetch' in sys.argv:
        fetch()
    else:
        write()
        if '--push' in sys.argv:
            push()
