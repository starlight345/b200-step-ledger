#!/usr/bin/env python3
"""Gate 4 결과 분석 — 기계별 회귀와 교차 그림. GPU 없이 로컬에서 돈다.

입력: gpu01 이 만든 gate4_<host>_<mode>/ 디렉터리들 (timing.json + ncu_*.csv)
출력: assets/sweep/gate4_causal.csv, assets/figures/gate4-causal.{png,svg}

판정 (REQUEST_GATE4_CAUSAL.md)
  기울기가 그 기계 B_eff 의 ±20% 안이고 R² ≥ 0.9  -> projection 을 논문 수치로 승격
  벗어남                                          -> 실측 기울기로 교체, 표 재계산
  R² < 0.9                                        -> 선형 교체 모델 폐기
"""
import csv, json, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent.parent
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
SERIES = ['#2a78d6','#eb6834','#1b9e77','#7570b3']          # 고정 순서, 순환 금지
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Apple SD Gothic Neo','Helvetica','DejaVu Sans'],
                     'font.size':8.5,'svg.fonttype':'none','axes.unicode_minus':False,'axes.edgecolor':AXIS,
                     'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

def ncu_bytes(path):
    """ncu --csv 에서 dram__bytes_read/write 합을 뽑는다. 포맷은 버전마다 조금 다르다."""
    txt = Path(path).read_text().split('#STDERR')[0]
    tot = {'dram__bytes_read.sum': 0.0, 'dram__bytes_write.sum': 0.0, 'lts__t_sectors_hit_rate': []}
    for row in csv.DictReader(l for l in txt.splitlines() if l and not l.startswith('==')):
        m, v = row.get('Metric Name'), row.get('Metric Value', '')
        if m in tot and v:
            try: val = float(str(v).replace(',', ''))
            except ValueError: continue
            if m.endswith('hit_rate'): tot[m].append(val)
            else: tot[m] += val
    return dict(dram_read_B=tot['dram__bytes_read.sum'], dram_write_B=tot['dram__bytes_write.sum'],
                l2_hit_rate=float(np.mean(tot['lts__t_sectors_hit_rate'])) if tot['lts__t_sectors_hit_rate'] else None)

def load(dirs):
    out = []
    for d in dirs:
        d = Path(d)
        rows = json.loads((d/'timing.json').read_text())
        by_pb = {}
        for r in rows: by_pb.setdefault(r['persist_bytes'], []).append(r['step_ms'])
        for pb, ts in sorted(by_pb.items()):
            rec = dict(host=rows[0]['host'], mode=rows[0]['mode'], persist_bytes=pb,
                       persist_MiB=pb/2**20, step_ms=float(np.median(ts)),
                       step_ms_sd=float(np.std(ts)), n=len(ts))
            c = d/f'ncu_{pb}.csv'
            if c.exists(): rec.update(ncu_bytes(c))
            out.append(rec)
    return out

def regress(recs):
    """x = HBM 바이트(GB), y = step 시간(ms).  기울기 = 1/B_eff [ms/GB] -> TB/s"""
    xs = np.array([r['dram_read_B']/1e9 for r in recs if r.get('dram_read_B')])
    ys = np.array([r['step_ms'] for r in recs if r.get('dram_read_B')])
    if len(xs) < 3: return None
    A = np.vstack([xs, np.ones_like(xs)]).T
    (slope, icpt), res, *_ = np.linalg.lstsq(A, ys, rcond=None)
    ss_res = float(res[0]) if len(res) else float(((ys-(slope*xs+icpt))**2).sum())
    r2 = 1 - ss_res/float(((ys-ys.mean())**2).sum())
    return dict(slope_ms_per_GB=float(slope), t0_ms=float(icpt), r2=float(r2),
                B_eff_TBs=(1.0/float(slope) if slope > 0 else float('inf')), n=len(xs))

if __name__ == '__main__':
    dirs = sys.argv[1:] or sorted(Path('.').glob('gate4_*'))
    if not dirs: print('gate4_* 디렉터리가 없다. gpu01 결과를 가져와라.'); sys.exit(1)
    recs = load(dirs)
    with (ROOT/'assets/sweep/gate4_causal.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in recs for k in r})); w.writeheader(); w.writerows(recs)

    hosts = sorted({r['host'] for r in recs})
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11.6, 4.5), facecolor=SURF)
    print(f"{'기계':22} {'점':>3} {'기울기 ms/GB':>13} {'B_eff TB/s':>11} {'t0 ms':>8} {'R²':>7}  판정")
    for i, h in enumerate(hosts):
        rs = [r for r in recs if r['host'] == h]; col = SERIES[i % len(SERIES)]
        ax.errorbar([r['persist_MiB'] for r in rs], [r['step_ms'] for r in rs],
                    yerr=[r['step_ms_sd'] for r in rs], color=col, lw=2.0, marker='o', ms=6,
                    capsize=3, label=h, zorder=4)
        fit = regress(rs)
        if fit:
            xs = np.array([r['dram_read_B']/1e9 for r in rs if r.get('dram_read_B')])
            ys = np.array([r['step_ms'] for r in rs if r.get('dram_read_B')])
            ax2.plot(xs, ys, 'o', ms=7, color=col, label=f"{h}  {fit['B_eff_TBs']:.2f} TB/s", zorder=4)
            g = np.linspace(xs.min(), xs.max(), 50)
            ax2.plot(g, fit['slope_ms_per_GB']*g + fit['t0_ms'], color=col, lw=1.6, ls=(0,(5,2.5)), zorder=3)
            verdict = 'R² < 0.9 — 선형 모델 재검토' if fit['r2'] < 0.9 else '선형 성립'
            print(f"{h:22} {fit['n']:3d} {fit['slope_ms_per_GB']:13.4f} {fit['B_eff_TBs']:11.2f} "
                  f"{fit['t0_ms']:8.3f} {fit['r2']:7.3f}  {verdict}")
        else:
            print(f'{h:22}  카운터 데이터 부족 — ncu 패스 확인')
    for a_, xl, yl, ti in ((ax, 'persisting L2 예약 [MiB]', 'step 시간 [ms]', '통제 변수 하나: 예약 크기'),
                           (ax2, '실측 HBM 읽기 [GB/step]', 'step 시간 [ms]', '기울기 = 1 / B_eff. 이것이 인과 계수다')):
        a_.set_facecolor(SURF); a_.set_xlabel(xl); a_.set_ylabel(yl)
        a_.set_title(ti, fontsize=10, color=INK, pad=8, loc='left')
        a_.grid(True, color=GRID, lw=.6); a_.set_axisbelow(True)
        if len(hosts) >= 2: a_.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    for ext in ('png','svg'): fig.savefig(ROOT/f'assets/figures/gate4-causal.{ext}', dpi=200, facecolor=SURF)
    print(f'\n저장: assets/sweep/gate4_causal.csv, assets/figures/gate4-causal.png')
