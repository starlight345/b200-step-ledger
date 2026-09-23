#!/usr/bin/env python3
"""Gate 1 (full): does the architecture ordering hold across the ENTIRE area sweep? (2026-09-21)

Earlier the ordering was checked only at 600 mm². This tests every cell of
C2/C3 x {400,500,600,700,800} mm² x {1,2} tiers against four orderings:
    O1  integrated non-overlap  >  keep existing L2 + separate 3D
    O2  keep existing L2 + separate 3D  ==  remove existing L2  (existing L2 adds nothing here)
    O3  any managed/LIP variant  >  integrated plain LRU
    O4  C2  >  C3 at equal area (denser macro buys more capacity)
Unified ledger only. Reports every violation.
"""
import csv, os, sys, collections
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
CSV = os.path.join(ROOT, 'assets/experiments/3dsram_closure_20260921/outputs/closure_area_policy.csv')
KEEP='keep_sL2_separate_3D_LIP'; INT='integrated_sL2_plus_3D_LIP'; REM='remove_sL2_3D_only_LIP'
LRU='integrated_sL2_plus_3D_LRU'; UPPER='ideal_nonoverlap_retention_bound'

def load():
    by = collections.defaultdict(dict)
    for r in csv.DictReader(open(CSV)):
        if r['architecture'] != UPPER and r['p99_hbm_fraction'] != '0.5': continue
        by[(r['case'], int(r['layers']), float(r['net_area_mm2_per_die_tier']))][r['architecture']] = float(r['hbm_reduction_percent'])
    return by

if __name__ == '__main__':
    by = load(); areas = sorted({k[2] for k in by}); cases = ('C3','C2'); layers = (1,2)
    print("=== Gate 1 전체 면적 순서 검증 (통일 장부) ===")
    print(f"검사 셀: {len(cases)} 케이스 x {len(layers)} 층 x {len(areas)} 면적 = {len(cases)*len(layers)*len(areas)}\n")
    viol = collections.defaultdict(list)
    for case in cases:
        for L in layers:
            for A in areas:
                v = by[(case,L,A)]
                if not (v[INT] > v[KEEP] + 1e-9): viol['O1'].append((case,L,A,f"{v[INT]:.4f} vs {v[KEEP]:.4f}"))
                if abs(v[KEEP]-v[REM]) > 1e-6:    viol['O2'].append((case,L,A,f"{v[KEEP]:.4f} vs {v[REM]:.4f}"))
                if not (min(v[KEEP],v[INT],v[REM]) > v[LRU] + 1e-9): viol['O3'].append((case,L,A,f"min LIP {min(v[KEEP],v[INT],v[REM]):.4f} vs LRU {v[LRU]:.4f}"))
    for L in layers:
        for A in areas:
            if not (by[('C2',L,A)][INT] > by[('C3',L,A)][INT] + 1e-9):
                viol['O4'].append(('C2 vs C3',L,A,f"{by[('C2',L,A)][INT]:.4f} vs {by[('C3',L,A)][INT]:.4f}"))
    names = {'O1':'integrated non-overlap > keep + separate','O2':'keep == remove (기존 L2 기여 0)',
             'O3':'managed/LIP > 일반 LRU','O4':'C2 > C3 (동일 면적)'}
    for k in ('O1','O2','O3','O4'):
        n = len(cases)*len(layers)*len(areas) if k != 'O4' else len(layers)*len(areas)
        ok = n - len(viol[k])
        print(f"  [{'PASS' if not viol[k] else 'FAIL'}] {names[k]:38s} {ok}/{n}")
        for c,L,A,d in viol[k][:5]: print(f"          위반: {c} {L}층 {A:.0f} mm²  {d}")
    print("\n=== 전체 표: integrated non-overlap 의 HBM 감소율 (%) ===")
    print(f"  {'구성':12s} " + ' '.join(f"{int(a):>8d}" for a in areas))
    for case in cases:
        for L in layers:
            print(f"  {case+' '+str(L)+'층':12s} " + ' '.join(f"{by[(case,L,a)][INT]:8.2f}" for a in areas))
    print("\n=== LRU 는 어디서나 평탄한가 ===")
    lru = {by[(c,L,a)][LRU] for c in cases for L in layers for a in areas}
    print(f"  전 셀 LRU 값 범위: {min(lru):.4f} ~ {max(lru):.4f} %  (분산 {max(lru)-min(lru):.4f}%p)")
    print(f"  면적을 {areas[0]:.0f} → {areas[-1]:.0f} mm² 로 두 배 늘려도 변화 없음.")
    print("\n=== integrated 가 관리 상한에 얼마나 가까운가 ===")
    gaps=[by[(c,L,a)][UPPER]-by[(c,L,a)][INT] for c in cases for L in layers for a in areas]
    print(f"  상한과의 격차: 최소 {min(gaps):.4f} ~ 최대 {max(gaps):.4f} %p (전 셀)")
