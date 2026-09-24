#!/usr/bin/env python3
"""Tabulate the macro-resolved transient runs (mapdl_macro.py) from the server's results.txt."""
import os, re, sys, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapdl_macro as MM

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'assets', 'mapdl', 'macro', 'results.txt')

def parse(path=SRC):
    rows = {}
    for line in open(path):
        if not line.startswith(('prod_', 'conv_', 'verify')): continue
        name = line.split()[0]
        vals = dict((k, float(v)) for k, v in re.findall(r'(\w+)=\s*([-+0-9.E]+)', line))
        vals['secs'] = int(re.search(r'\s(\d+)s\s', line).group(1))
        rows[name] = vals
    return rows

if __name__ == '__main__':
    R = parse()
    base = {k: R[f'prod_k{k}_phiU']['peak'] for k in (1, 10) if f'prod_k{k}_phiU' in R}
    if 'prod_kz1_phiU' in R: base['z1'] = R['prod_kz1_phiU']['peak']
    out = []
    print(f"{'case':<16} {'phi':>5} {'dens':>5} {'peak C':>10} {'logic C':>10} {'peak-logic':>10} "
          f"{'vs unif':>8} {'swing':>7} {'conv':>7}")
    for k in (1, 10, 'z1'):
        for tag, ph in (('U', MM.PERI_AREA_FRAC), ('50', .5), ('70', .7), ('90', .9)):
            nm = f'prod_k{k}_phi{tag}'
            if nm not in R: continue
            r = R[nm]
            row = dict(case=nm, kxy_over_kz=(1 if k == 'z1' else k), beol_kz=(1.0 if k == 'z1' else 2.5), phi=round(ph, 3),
                       periphery_density_x=round(ph/MM.PERI_AREA_FRAC, 2),
                       tier_peak_C=r['peak'], logic_at_peak_C=r['logic'],
                       peak_above_logic_K=r['peak']-r['logic'],
                       rise_vs_uniform_K=r['peak']-base[k], swing_K=r['peak']-r['trough'],
                       last_period_change=abs(r['peak']-r['prevpeak']))
            out.append(row)
            print(f"{nm:<16} {ph:>5.3f} {row['periphery_density_x']:>4.2f}x {r['peak']:>10.4f} "
                  f"{r['logic']:>10.4f} {row['peak_above_logic_K']:>9.4f}K {row['rise_vs_uniform_K']:>7.4f}K "
                  f"{row['swing_K']:>6.4f}K {row['last_period_change']*1e3:>5.2f}mK")
    if 'conv_fine' in R and 'prod_k1_phi90' in R:
        a, b = R['prod_k1_phi90'], R['conv_fine']
        la, lb = a['peak']-a['logic'], b['peak']-b['logic']
        print(f"\nmesh convergence at phi=0.9: peak {a['peak']:.4f} -> {b['peak']:.4f} C "
              f"(diff {abs(b['peak']-a['peak'])*1e3:.2f} mK); local rise above logic "
              f"{la:.4f} -> {lb:.4f} K ({abs(lb-la)/lb*100:.2f}%)")
    if 'verify' in R:
        pk, tr = MM.reference_1d()
        v = R['verify']
        print(f"\nverification: 3D transient peak {v['peak']:.6f} K vs 1D {pk:.6f} K "
              f"({abs(v['peak']-pk)/pk*100:.2f}%), trough {v['trough']:.6f} vs {tr:.6f}")
    dst = os.path.join(HERE, '..', 'assets', 'sweep', 'macro_transient.csv')
    with open(dst, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(f'\nwrote {os.path.relpath(dst)}')
