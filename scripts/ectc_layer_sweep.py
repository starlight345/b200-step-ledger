#!/usr/bin/env python3
"""ECTC figure 2: how many layers are worth stacking, and what actually stops you.

Two answers that do not agree with the usual framing:
 (a) The benefit SATURATES, and not because of bandwidth. Admission (Gate 6) takes only
     the weight stream, so once tier capacity covers the 15.01 GB weight working set,
     more capacity buys nothing. That knee sits near 7 layers at C2 / 800 mm^2 / 2 dies.
 (b) Self-heating of the tier does NOT reach the knee first, under any per-layer thermal
     resistance in a plausible range -- because the duty cycle is a few percent and the
     area is a full reticle. The binding device question is therefore not "how much does
     the tier heat up" but "what absolute junction temperature can a BEOL device take,
     sitting on a ~1 kW logic die".
"""
import os, sys, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
import ectc_thermal_model as M
import thermal_sensitivity as SENS      # verified 1D solver, wrapped per stack variant

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures'); os.makedirs(FIG, exist_ok=True)
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,
                     'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

AREA, DIES, CASE = 800.0, 2, 'C2'
N = np.arange(1, 13)
C   = np.array([M.capacity_GB(AREA, int(n), DIES, CASE) for n in N])
FR  = np.array([M.f_red(c) for c in C])
DTY = np.array([M.duty(c) for c in C])
knee = next(int(n) for n, c in zip(N, C) if M.f_red(c) >= M.F_MAX - 1e-9)

fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.6, 4.7), facecolor=SURF)
fig.subplots_adjust(left=0.062, right=0.965, top=0.715, bottom=0.145, wspace=0.30)
for ax in (axL, axR): ax.set_facecolor(SURF); ax.grid(True, color=GRID, lw=0.5, zorder=0)

# ---------------- (a) benefit saturates, and admission is why
axL.axvspan(0.5, 2.5, color=S1, alpha=0.08, zorder=1)
axL.text(1.5, 70, 'realizable today\n(1-2 layers)', fontsize=7.4, color=S1, ha='center', va='top', zorder=6)
axL.plot(N, FR*100, color=S2, lw=2.3, marker='o', ms=4.5, mfc='white', mec=S2, mew=1.4, zorder=5,
         label='HBM traffic served by the tier')
axL.axhline(M.F_MAX*100, color=INK2, lw=1.1, ls=(0,(4,2)), zorder=4)
axL.text(12.2, 68, f'{M.F_MAX*100:.1f}% ceiling: the tier has\ncovered the {M.W_READ:.2f} GB weight stream,\n'
         f'and admission refuses KV --\nextra layers buy nothing',
         fontsize=7.3, color=INK2, ha='right', va='top', zorder=6)
axL.axvline(knee, color=RED, lw=1.1, zorder=4)
axL.text(knee-0.25, 8, f'knee at {knee} layers', fontsize=7.4, color=RED, ha='right', rotation=90, va='bottom', zorder=6)
axL.set_xlabel(f'stacked layers  ({CASE}, {AREA:.0f} mm2 per die per layer, {DIES} dies)')
axL.set_ylabel('HBM byte reduction  [%]', color=S2)
axL.tick_params(axis='y', colors=S2)
axL.set_xlim(0.5, 12.5); axL.set_ylim(0, 100)
ax2 = axL.twinx(); ax2.set_facecolor('none')
ax2.plot(N, C, color=MUTED, lw=1.4, ls=':', zorder=3)
ax2.set_ylabel('tier capacity  [GB]', color=MUTED); ax2.tick_params(axis='y', colors=MUTED)
ax2.set_ylim(0, 27); ax2.spines['right'].set_color(AXIS)
ax2.text(9.2, 20.3, 'capacity (linear)', fontsize=7.3, color=MUTED, ha='left')
axL.set_title('(a)  benefit saturates -- and bandwidth is not why.\nadmission caps what the tier can ever serve',
              fontsize=9.2, color=INK, loc='left', pad=8)

# ---------------- (b) the tier's own rise never reaches that knee
# Panel (b) used to call ectc_thermal_model.dT_peak, which is the SINGLE-NODE lumped model
# that MAPDL later showed to be optimistic by 4.16x (claim E8). Using it here while the
# rest of the paper rejects it was an internal inconsistency. It now runs on the verified
# 1D transient solver, and the band is swept over BEOL effective conductivity, which the
# sensitivity ranking identifies as the dominant unmeasured quantity (95%) -- the old band
# swept a per-layer thermal resistance that the ranking puts at 1%.
for e_pJ, col, ls in ((0.5, RED, '-'), (0.2, S2, '-'), (0.1, S3, '-')):
    lo, hi, mid = [], [], []
    for n in N:
        pb = M.p_burst_W(e_pJ)/2.0                     # per die, matching the solver
        lo.append(SENS.variant(n_tiers=int(n), beol_k=5.0)[1]*pb)
        hi.append(SENS.variant(n_tiers=int(n), beol_k=1.0)[1]*pb)
        mid.append(SENS.variant(n_tiers=int(n))[1]*pb)
    axR.fill_between(N, lo, hi, color=col, alpha=0.13, zorder=2)
    axR.plot(N, mid, color=col, lw=2.1, ls=ls, zorder=5)
    axR.text(12.35, mid[-1], f'E/bit {e_pJ} pJ', fontsize=7.4, color=col, ha='left', va='center', zorder=6)
axR.axvline(knee, color=RED, lw=1.1, zorder=4)
axR.text(knee-0.25, 0.012, f'benefit knee, {knee} layers', fontsize=7.4, color=RED, ha='right', rotation=90, va='bottom', zorder=6)
axR.axhline(10.0, color=INK2, lw=1.2, ls=(0,(4,2)), zorder=4)
axR.text(0.7, 10.8, 'example 10 K headroom', fontsize=7.4, color=INK2, va='bottom', zorder=6)
axR.set_yscale('log'); axR.set_ylim(0.008, 40); axR.set_xlim(0.5, 14.6)
axR.set_xlabel('stacked layers   (band = BEOL effective conductivity 1.0-5.0 W/m/K, the dominant unmeasured axis)')
axR.set_ylabel('peak tier temperature rise above local baseline  [K]')
axR.set_title('(b)  on the VERIFIED solver, the tier\'s own rise stays far below any\n'
              'plausible headroom -- what stops the stack is admission, not heat',
              fontsize=9.2, color=INK, loc='left', pad=8)

fig.text(0.062, 0.955, 'Admission caps the benefit at 8 layers; the tier\'s own heat never gets anywhere near stopping it',
         fontsize=12.0, color=INK, va='top')
fig.text(0.062, 0.900, 'Llama-3.1-8B decode, B=8 N=2048. Capacity is a geometric upper bound (no legal polygon). dT is a first-order periodic-steady-state\n'
         'rise ABOVE the local baseline. That baseline is a measured 698.7 W package (decode B=8 N=2048), so the limit that actually binds is the\n'
         'BEOL device\'s absolute Tj, which is unmeasured. Decode is the verified thermal worst case: prefill duty is 0.08-0.41% against decode\'s 4.80%.',
         fontsize=7.8, color=INK2, va='top', linespacing=1.5)
for ext in ('png','svg'):
    fig.savefig(os.path.join(FIG, f'ectc-layer-sweep.{ext}'), dpi=220, facecolor=SURF)

print(f'knee at {knee} layers, capacity {M.capacity_GB(AREA,knee,DIES,CASE):.2f} GB, f_red ceiling {M.F_MAX*100:.1f}%')
for n in (1,2,4,knee,12):
    c = M.capacity_GB(AREA, int(n), DIES, CASE)
    dt = SENS.variant(n_tiers=int(n), beol_k=1.0)[1]*M.p_burst_W(0.5)/2.0
    print(f'  N={n:>2}  C={c:>6.2f} GB  f_red={M.f_red(c)*100:>5.1f}%  duty={M.duty(c)*100:>5.2f}%  '
          f'dT(0.5pJ, worst BEOL k)={dt:>5.3f} K')
print('wrote assets/figures/ectc-layer-sweep.{png,svg}')
