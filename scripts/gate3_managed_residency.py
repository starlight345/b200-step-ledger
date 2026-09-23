#!/usr/bin/env python3
"""Gate 3 (v2): managed-residency service model (2026-09-21).

Replaces the demand-cache beta model on the main path. Under managed residency the steady state
reads a pinned set, so only one bandwidth enters per step:
    B_R_delivered   3D -> compute sustained read, swept 2..25 TB/s
The fill bandwidth B_W is confined to Gate 5 (request-lifetime), where it costs <1.2% of the gain.

Traffic input is the EXACT replay (trace replay result). Time output is a PROJECTION that assumes
removing a byte from HBM saves byte/B_HBM of step time; that causal coefficient is Gate 4.
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sram_capacity_bandwidth_sweep as S
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
EXP  = os.path.join(ROOT, 'assets/experiments/3dsram_closure_20260921/outputs')
GB = 1e9; GiB = 2**30
T0 = S.CAL['llama']['t0_ms']; B_HBM = S.CAL['llama']['BW_eff_TBs']
B_R_SWEEP = [2,3,4,5,6.4,8,10,12,15,17.7,19,21,25]
INT='integrated_sL2_plus_3D_LIP'

def replay():
    rows=[r for r in csv.DictReader(open(f'{EXP}/closure_area_policy.csv'))]
    base=json.load(open(f'{EXP}/closure_summary.json'))['baseline_existing_sL2_LIP_HBM_GiB_step']*GiB/GB
    out={}
    for r in rows:
        if r['layers']!='2' or r['architecture']!=INT or r['p99_hbm_fraction']!='0.5': continue
        out[(r['case'],float(r['net_area_mm2_per_die_tier']))]=dict(hbm=float(r['hbm_GiB_step'])*GiB/GB, cap=float(r['capacity_GB_gpu']))
    return out, base

def project(hbm, base_hbm, b_r):
    Sv=base_hbm-hbm; tb=T0+base_hbm/B_HBM
    return tb/(T0+hbm/B_HBM+Sv/b_r), tb/(T0+max(hbm/B_HBM, Sv/b_r)), Sv

if __name__=='__main__':
    R, base = replay()
    print(f"기준 (통일 장부, 티어 없음): HBM {base:.3f} GB/step, step {T0+base/B_HBM:.3f} ms")
    print(f"HBM 유효 대역폭 {B_HBM:.2f} TB/s [measured-derived]. 아래 speedup 은 모두 projection 이다.\n")
    print("=== 3-1. B_R 스윕 × 면적 (C2 2층, 직렬 / 겹침 projection) ===")
    areas=[400,500,600,700,800]
    print(f"  {'B_R':>6s} " + ' '.join(f"{str(a)+' mm²':>15s}" for a in areas))
    rows=[]
    for b_r in B_R_SWEEP:
        cells=[]
        for A in areas:
            d=R[('C2',float(A))]; ser,ovl,Sv=project(d['hbm'],base,b_r)
            cells.append(f"{ser:.3f}/{ovl:.3f}")
            rows.append(dict(case='C2',layers=2,area_mm2=A,cap_GB=d['cap'],b_r_TBs=b_r,
                             served_GB=Sv,hbm_GB=d['hbm'],serial_projection=ser,overlap_projection=ovl))
        mark = '  <- HBM 유효' if abs(b_r-B_HBM)<1e-9 else ''
        print(f"  {b_r:5.1f}T " + ' '.join(f"{c:>15s}" for c in cells) + mark)
    print("\n=== 3-2. 문턱 ===")
    d=R[('C2',600.0)]
    print(f"  직렬: 이득 조건 S/B_R < S/B_HBM  =>  B_R > {B_HBM:.2f} TB/s. 면적 무관.")
    for A in areas:
        d=R[('C2',float(A))]; Sv=base-d['hbm']
        print(f"    겹침 {A} mm²: S {Sv:.3f} GB, H {d['hbm']:.3f} GB  =>  B_R > {Sv/(d['hbm']/B_HBM):.2f} TB/s")
    print(f"\n  현재 가정한 delivered-read 시나리오는 15 / 17.7 / 19 TB/s 이고 모두 {B_HBM:.2f} 를 넘는다.")
    print("  따라서 조건부 진술: '현재 service model 과 이 delivered-read 시나리오 아래에서는")
    print("   read BW 가 정상 상태 decode 이득을 제한하지 않는다.' 실제 delivered BW 는 Gate 2/3 device 회신 대기.")
    p=os.path.join(ROOT,'assets/sweep/gate3_managed_residency.csv')
    with open(p,'w',newline='') as f:
        k=sorted({x for r in rows for x in r}); w=csv.DictWriter(f,fieldnames=k); w.writeheader(); w.writerows(rows)
    print(f"\nwrote {os.path.relpath(p,ROOT)}")
