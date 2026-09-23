#!/usr/bin/env python3
"""Gate 3: convert the Gate-0/1 traffic result into service time (2026-09-21).

Input is the EXACT replay, not a coverage proportion: assets/experiments/3dsram_closure_20260921
(unified ledger) gives HBM logical bytes per step for each area x organization x policy.

Managed residency makes the write path a startup cost rather than a steady-state one, so the
two bandwidths enter at different places:
    B_R  3D -> SM sustained read. Enters every step.
    B_W  HBM -> 3D sustained fill. Enters once at preload, amortized over the residency lifetime.

Per step, with D = logical traffic, H = HBM bytes after the tier, S = D - H served by the tier:
    serial      t = t0 + H/B_HBM + S/B_R
    overlapped  t = t0 + max(H/B_HBM, S/B_R)
Baseline is the same replay with no tier: t_base = t0 + H_base/B_HBM.
Preload adds C/B_W once; amortized over L steps it is C/(B_W * L) per step.

Only t0 and B_HBM come from measurement, and their causal validity is Gate 4.
"""
import csv, json, os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sram_capacity_bandwidth_sweep as S
from canon_3dsram import get

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
EXP = os.path.join(ROOT, 'assets/experiments/3dsram_closure_20260921/outputs')
GB = 1e9; GiB = 2**30
T0 = S.CAL['llama']['t0_ms']; B_HBM = S.CAL['llama']['BW_eff_TBs']
B_R_CAPS = {'slack_r1': 15.0, 'deck_320': 17.7, 'via_L2_fabric': 19.0}   # canon: design_point_axes.read_delivery_cap_TBs
ARCH = ['keep_sL2_separate_3D_LIP', 'integrated_sL2_plus_3D_LIP', 'remove_sL2_3D_only_LIP', 'integrated_sL2_plus_3D_LRU']

def load_replay():
    rows = [r for r in csv.DictReader(open(f'{EXP}/closure_area_policy.csv'))]
    base = json.load(open(f'{EXP}/closure_summary.json'))['baseline_existing_sL2_LIP_HBM_GiB_step']
    out = {}
    for r in rows:
        if r['layers'] != '2': continue
        if r['architecture'] != 'ideal_nonoverlap_retention_bound' and r['p99_hbm_fraction'] != '0.5': continue
        out[(r['case'], float(r['net_area_mm2_per_die_tier']), r['architecture'])] = dict(
            hbm_GiB=float(r['hbm_GiB_step']), cap_GB=float(r['capacity_GB_gpu']))
    return out, base

def step_times(hbm_GiB, base_hbm_GiB, b_r):
    H = hbm_GiB*GiB/GB; Hb = base_hbm_GiB*GiB/GB; Sv = Hb - H     # bytes the tier serves, from the exact replay
    t_base = T0 + Hb/B_HBM
    return dict(base_ms=t_base,
                serial=t_base/(T0 + H/B_HBM + Sv/b_r),
                overlap=t_base/(T0 + max(H/B_HBM, Sv/b_r)),
                served_GB=Sv, hbm_GB=H, base_hbm_GB=Hb)

if __name__ == '__main__':
    R, base = load_replay()
    print(f"기준 (통일 장부, 티어 없음): HBM {base*GiB/GB:.3f} GB/step, t0 {T0:.2f} ms, B_HBM {B_HBM:.2f} TB/s")
    print(f"  기준 step = {T0 + base*GiB/GB/B_HBM:.3f} ms\n")

    print("=== 3-1. 트래픽 감소 → step 시간 (C2, 2층, integrated LIP) ===")
    print(f"  {'면적':>5s} {'용량':>8s} {'티어 서비스':>10s} {'HBM 감소':>9s} | " + ' '.join(f"{'B_R '+str(v)+' 직렬/겹침':>20s}" for v in B_R_CAPS.values()))
    rows=[]
    for A in (400,500,600,700,800):
        k=('C2',float(A),'integrated_sL2_plus_3D_LIP'); d=R[k]
        cells=[]
        for nm,br in B_R_CAPS.items():
            st=step_times(d['hbm_GiB'], base, br); cells.append(f"{st['serial']:.4f}/{st['overlap']:.4f}")
            rows.append(dict(gate='3-1',case='C2',area=A,arch='integrated_LIP',cap_GB=d['cap_GB'],b_r_name=nm,b_r=br,**{k2:v for k2,v in st.items()}))
        st0=step_times(d['hbm_GiB'], base, 15.0)
        print(f"  {A:5d} {d['cap_GB']:7.3f}G {st0['served_GB']:9.3f}G {100*st0['served_GB']/st0['base_hbm_GB']:8.2f}% | " + ' '.join(f"{c:>20s}" for c in cells))

    print("\n=== 3-2. 구조별 비교 (600 mm², C2, 2층) — 트래픽 순위가 시간 순위로 이어지는가 ===")
    print(f"  {'구조':32s} {'HBM 감소':>9s} {'직렬':>8s} {'겹침':>8s}")
    for a in ARCH:
        d=R[('C2',600.0,a)]; st=step_times(d['hbm_GiB'], base, 15.0)
        print(f"  {a:32s} {100*st['served_GB']/st['base_hbm_GB']:8.2f}% {st['serial']:8.4f} {st['overlap']:8.4f}")
        rows.append(dict(gate='3-2',case='C2',area=600,arch=a,cap_GB=d['cap_GB'],b_r_name='slack_r1',b_r=15.0,**{k2:v for k2,v in st.items()}))

    print("\n=== 3-3. B_R 문턱: 티어가 절감분을 상쇄하지 않으려면 (직렬 경계) ===")
    print("  직렬에서 이득 조건은 S/B_R < S/B_HBM, 즉 B_R > B_HBM. 겹침에서는 S/B_R < H/B_HBM.")
    print(f"  {'면적':>5s} {'S(GB)':>7s} {'H(GB)':>7s} {'겹침에서 필요한 최소 B_R':>24s}")
    for A in (400,600,800):
        d=R[('C2',float(A),'integrated_sL2_plus_3D_LIP')]; st=step_times(d['hbm_GiB'], base, 15.0)
        need = st['served_GB']/(st['hbm_GB']/B_HBM)
        print(f"  {A:5d} {st['served_GB']:7.3f} {st['hbm_GB']:7.3f} {need:23.2f} TB/s")
        rows.append(dict(gate='3-3',case='C2',area=A,arch='integrated_LIP',b_r_name='threshold',b_r=need,**{k2:v for k2,v in st.items()}))
    print(f"  직렬 경계의 문턱은 면적과 무관하게 B_R > B_HBM = {B_HBM:.2f} TB/s 하나다.")

    print("\n=== 3-4. 예열 비용: B_W 는 몇 스텝에 걸쳐 상각되는가 (600 mm², C2 2층, 3.164 GB) ===")
    C = R[('C2',600.0,'integrated_sL2_plus_3D_LIP')]['cap_GB']
    st = step_times(R[('C2',600.0,'integrated_sL2_plus_3D_LIP')]['hbm_GiB'], base, 15.0)
    gain_ms = st['base_ms'] - st['base_ms']/st['serial']
    print(f"  스텝당 이득 {gain_ms:.4f} ms (직렬, B_R 15). 상주 집합 {C:.3f} GB.")
    print(f"  {'B_W':>6s} {'예열 시간':>10s} {'본전 스텝수':>10s} {'2048 스텝 상각 시 순이득':>22s}")
    for bw in (2.0, 4.0, 6.4, 8.0, 15.0):
        pre = C/bw*1e3; n = pre/gain_ms
        net = gain_ms - pre/2048
        print(f"  {bw:5.1f}T {pre:9.3f}ms {n:10.0f} {net:19.4f} ms/step")
        rows.append(dict(gate='3-4',case='C2',area=600,arch='integrated_LIP',b_r_name='preload',b_r=bw,preload_ms=pre,breakeven_steps=n,net_gain_ms=net,**{k2:v for k2,v in st.items()}))
    print("  관리 상주에서는 B_W 가 정상 상태가 아니라 예열에만 들어간다. 수백 스텝이면 상각된다.")

    p=os.path.join(ROOT,'assets/sweep/gate3_traffic_to_time.csv')
    with open(p,'w',newline='') as f:
        keys=sorted({k for r in rows for k in r}); w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(rows)
    print(f"\nwrote {os.path.relpath(p,ROOT)}")
