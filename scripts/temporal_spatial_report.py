#!/usr/bin/env python3
"""Tables for temporal_spatial_ablation.json: what each abstraction does to B_max and the verdict.

  B_max(method) = 19 TB/s x dT_lim / (method's peak rise at 19 TB/s),  dT_lim = 10 W x R_uniform
  ratio         = B_max(method) / B_max(reference)      > 1 optimistic, < 1 pessimistic
  verdict       = pass if B_max >= 19 TB/s (the fabric limit), at each E/bit

Reference = the exact schedule on the macro-resolved model with the same phi (the model is
checked against MAPDL in the JSON's mapdl_check). Experiment A varies only the temporal input
at a fixed spatial model; B varies only the spatial model with the exact schedule; C asks
whether a temporal factor (from the uniform model) times a spatial factor (from the static
maps) reproduces the joint answer.

  python3 scripts/temporal_spatial_report.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ectc_thermal_model as M

HERE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(HERE, '..', 'assets', 'sweep', 'temporal_spatial_ablation.json')
R = json.load(open(IN))
D = R['design']
B_R, BUD = D['B_R_TBs'], D['budget_W_die']
PB = {float(k): v for k, v in D['P_burst_W_die'].items()}
PKGS = ['ideal lid', 'R_ext/R_stack 2.9', 'production deck']
SPS = ['tier-uniform (1D)'] + [f'macro phi={p:.3f}' for p in (0.285, 0.5, 0.7, 0.9)]
SPS = [s for s in SPS if any(c['spatial'] == s for c in R['cases'].values())] or \
      sorted({c['spatial'] for c in R['cases'].values()})
SCHS = list(dict.fromkeys(c['schedule'] for c in R['cases'].values()))
TEMPORAL = ['static-peak', 'static-avg'] + [f'trace-{w*1e6:g}us' for w in D['windows_s']] + \
           ['one block (217 us)', 'lumped RC (die node)', 'exact']

def case(pkg, sp, sch):
    return R['cases'][f'{pkg} | {sp} | {sch}']

def bmax(rise, Ru, e):
    return B_R*BUD*Ru/(PB[e]*rise)

def ratio(pkg, sp, sch, meth, ref_sp=None):
    c = case(pkg, sp, sch); ref = case(pkg, ref_sp or sp, sch)
    return ref['exact']/c[meth]

def fmt(r):
    return f'{r:5.2f}x' if r < 99.5 else f'{r:5.0f}x'

def main():
    print(f"MAPDL check: worst |difference| {R['mapdl_check_worst']*100:.2f}% over {len(R['mapdl_check'])} runs\n")
    phis = [s for s in SPS if s.startswith('macro')]
    # A: temporal ladder at fixed spatial model
    print('A. Temporal ladder, spatial model fixed. B_max(method)/B_max(exact, same model); >1 optimistic')
    for pkg in PKGS:
        for sp in ('tier-uniform (1D)', phis[0], phis[-1]):
            print(f'\n  {pkg} | {sp}')
            print(f"  {'method':>22} " + ' '.join(f'{s[:14]:>14}' for s in SCHS))
            for m in TEMPORAL:
                print(f'  {m:>22} ' + ' '.join(f'{fmt(ratio(pkg, sp, s, m)):>14}' for s in SCHS))
    # B: spatial ladder, exact schedule
    print('\nB. Spatial ladder, exact schedule. B_max(model)/B_max(macro phi); >1 optimistic')
    for pkg in PKGS:
        print(f'\n  {pkg}')
        print(f"  {'reference phi':>22} " + ' '.join(f'{s[:14]:>14}' for s in SCHS))
        for sp in phis:
            print(f'  {sp:>22} ' + ' '.join(f"{fmt(ratio(pkg, 'tier-uniform (1D)', s, 'exact', sp)):>14}" for s in SCHS))
    # C: separability
    print('\nC. Separable correction: static-avg(uniform) x temporal factor(uniform) x spatial factor(static maps)')
    print('   vs the joint answer. Shown: joint / separable (>1 = the separable product is optimistic)')
    for pkg in PKGS:
        print(f'\n  {pkg}')
        print(f"  {'phi':>22} " + ' '.join(f'{s[:14]:>14}' for s in SCHS))
        for sp in phis:
            cells = []
            for s in SCHS:
                u, j = case(pkg, 'tier-uniform (1D)', s), case(pkg, sp, s)
                sep = u['exact']*j['static-peak']/u['static-peak']
                cells.append(f'{j["exact"]/sep:>13.2f}x')
            print(f'  {sp:>22} ' + ' '.join(cells))
    # D: verdicts
    print('\nD. Verdict at 19 TB/s against the reference (macro phi, exact), all packages x phi x schedules')
    for e in sorted(PB):
        print(f'\n  E/bit {e} pJ ({PB[e]:.2f} W/die at 19 TB/s)')
        print(f"  {'method (spatial model)':>40} {'correct':>8} {'false pass':>11} {'false rej.':>11}")
        rows = [(m, 'same') for m in TEMPORAL if m != 'exact'] + [('exact', 'uniform'), ('static-avg', 'uniform'),
                                                                   ('trace-1000us', 'uniform')]
        n_ref_fail = 0
        for m, spm in rows:
            ok = fp = fr = 0
            for pkg in PKGS:
                for sp in phis:
                    for s in SCHS:
                        ref = case(pkg, sp, s); Ru = ref['R_uniform_K_per_W']
                        c = case(pkg, sp if spm == 'same' else 'tier-uniform (1D)', s)
                        pr, pm = bmax(ref['exact'], Ru, e) >= B_R, bmax(c[m], Ru, e) >= B_R
                        ok += pr == pm; fp += pm and not pr; fr += pr and not pm
            print(f"  {m + (' (tier-uniform)' if spm == 'uniform' else ''):>40} {ok:>8} {fp:>11} {fr:>11}")
        fails = [(pkg, sp, s) for pkg in PKGS for sp in phis for s in SCHS
                 if bmax(case(pkg, sp, s)['exact'], case(pkg, sp, s)['R_uniform_K_per_W'], e) < B_R]
        print(f'  reference fails in {len(fails)} of {len(PKGS)*len(phis)*len(SCHS)} cases' +
              (': ' + '; '.join(f'{a}/{b.split("=")[1]}/{c.split()[0]}' for a, b, c in fails[:12]) if fails else ''))
    # E: absolute kelvin at the v3.4 point
    e = 0.217
    print(f'\nE. Absolute peak self-heating of the tier at E/bit {e} pJ, 19 TB/s (K); reference = exact')
    for pkg in PKGS:
        print(f'\n  {pkg}')
        print(f"  {'spatial | schedule':>44} {'exact':>7} {'s-peak':>7} {'s-avg':>7} {'1ms':>7} {'200us':>7} {'1D exact':>8}")
        for sp in (phis[0], phis[-1]):
            for s in SCHS:
                c = case(pkg, sp, s); u = case(pkg, 'tier-uniform (1D)', s); P = PB[e]
                print(f'  {sp + " | " + s[:20]:>44} {c["exact"]*P:>7.3f} {c["static-peak"]*P:>7.3f} '
                      f'{c["static-avg"]*P:>7.3f} {c["trace-1000us"]*P:>7.3f} {c["trace-200us"]*P:>7.3f} {u["exact"]*P:>8.3f}')

if __name__ == '__main__':
    main()
