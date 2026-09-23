#!/usr/bin/env python3
"""Figure: managed residency's value is a property of the DESIGN. Bypass's is a property
of the TRACE.

Three unmeasured axes, all of which move bypass (rung 3b) and none of which move managed
residency (rung 4):
  (a) prefill activation traffic -- bounded below by the layer boundary (2 round trips of the
      hidden state, which no fusion removes) and above by materialising every GEMM output at
      T = 16,384 tokens (21). Nobody has measured where a real engine sits.
  (a, inset) prefill emission order -- the same first-fill sensitivity that zeroed the admission
      delta when weights were emitted in bulk.
  (b) request churn, with and without a refresh discipline -- the peer session's *1 control.

Managed residency is flat in all three because it never admits anything it did not choose.
"""
import os, sys, json, math
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
import prefill_phase as PF
import prefill_policy_replay as PR
import gate6_bypass_refresh as G6
import replay_policies as R

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIG  = os.path.join(ROOT, 'assets', 'figures'); os.makedirs(FIG, exist_ok=True)
SURF, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
S1, S2, S3, RED = '#2a78d6', '#eb6834', '#1baf7a', '#d03b3b'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
                     'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,
                     'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

# ---------------- panel (a): prefill, activation volume + emission order
LO, HI = PF.act_roundtrips_bounds()
ARTS = [LO, 4, 6, 8, 12, 16, HI]
act_gb, byp, mgd = [], [], []
CAP = PR.capacity('C2', 600, 2)
base = PR.run(lambda: PR.Cache(PR.C0, 'LIP'), False)['avg']
for art in ARTS:
    PR.PRE, _ = PR.tiles_from(PF.build_events(1.0, art))
    b = PR.run(lambda: PR.Frozen(PR.C0+CAP), True)
    m = PR.run(lambda: PR.Managed(PR.C0+CAP, PR.DEC), True)
    act_gb.append(PF.prefill_bytes(1.0, art)['activation']/1e9)
    byp.append((1-b['last']/base)*100); mgd.append((1-m['last']/base)*100)

PR.PRE, _ = PR.tiles_from(PF.build_events(1.0, 2))
NOM = PR.PRE
orders = {'weight first': sorted(NOM, key=lambda t: t[0][1] not in ('layer_weight','lm_head')),
          'layer-interleaved': NOM,
          'activation first': sorted(NOM, key=lambda t: t[0][1] != 'activation')}
ord_vals = {}
for lab, tr in orders.items():
    PR.PRE = tr
    ord_vals[lab] = (1-PR.run(lambda: PR.Frozen(PR.C0+CAP), True)['last']/base)*100
PR.PRE = NOM

# ---------------- panel (b): churn, with and without refresh
cap6 = R.cap_bytes('C2', 600)
LENS = [10000, 400, 120, 60, 30, 16]
ch = {'managed': [], 'bypass': [], 'bypass P=4': []}
for L in LENS:
    stl, wr = R.tiles(os.path.join(ROOT, 'assets', 'experiments', '3dsram_aperiodic_20260921',
                                   'inputs', f'aperiodic-b8-s128-L{L}.jsonl'))
    b0 = G6.run(stl, wr, 0, 'LIP')
    for lab, pol, P in (('managed','managed',None), ('bypass','bypass',None), ('bypass P=4','bypass',4)):
        r = G6.run(stl, wr, cap6, pol, P)
        ch[lab].append((1-r['hbm_ss']/b0['hbm_ss'])*100)

fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.6, 4.8), facecolor=SURF)
fig.subplots_adjust(left=0.062, right=0.975, top=0.715, bottom=0.145, wspace=0.26)
for ax in (axL, axR): ax.set_facecolor(SURF); ax.grid(True, color=GRID, lw=0.5, zorder=0)

axL.fill_between(act_gb, byp, mgd, color=RED, alpha=0.10, zorder=1)
axL.plot(act_gb, mgd, color=S3, lw=2.4, marker='o', ms=4, mfc='white', mec=S3, mew=1.4, zorder=5)
axL.plot(act_gb, byp, color=S2, lw=2.4, marker='o', ms=4, mfc='white', mec=S2, mew=1.4, zorder=5)
axL.text(92, mgd[-1]+0.9, 'managed residency -- flat', fontsize=7.8, color=S3, ha='right')
axL.text(92, byp[-1]-1.6, 'bypass (rung 3b)', fontsize=7.8, color=S2, ha='right')
xn = PF.prefill_bytes(1.0, 2)['activation']/1e9
axL.plot([xn, xn], [min(ord_vals.values()), max(ord_vals.values())], color=S1, lw=1.2, zorder=6)
for lab, v, va, dy in (('weight first', ord_vals['weight first'], 'top', -0.7),
                       ('layer-interleaved', ord_vals['layer-interleaved'], 'bottom', 0.7),
                       ('activation first', ord_vals['activation first'], 'bottom', 0.7)):
    axL.plot([xn], [v], marker='_', ms=20, mew=2.4, color=S1, zorder=7)
    axL.text(xn+2.2, v+dy, f'{lab}  {v:.1f}%', fontsize=7.0, color=S1, va=va, ha='left', zorder=7)
axL.annotate('one activation volume,\nthree emission orders:\nthe whole 0 - 19%p span',
             xy=(xn, 6.5), xytext=(34, 3.0), fontsize=7.4, color=S1, ha='left',
             arrowprops=dict(arrowstyle='-', color=S1, lw=0.9, shrinkA=2, shrinkB=4), zorder=7)
axL.set_xlim(0, 96); axL.set_ylim(-4, 22)
axL.set_xlabel('prefill activation traffic  [GB]      (bounded 8.6 - 90.2; unmeasured within)')
axL.set_ylabel('HBM byte reduction, steady state  [%]')
axL.set_title('(a)  prefill: two unmeasured implementation axes\nmove bypass across 0 - 19%p and leave managed untouched',
              fontsize=9.2, color=INK, loc='left', pad=8)

axR.plot(LENS, ch['managed'], color=S3, lw=2.4, marker='o', ms=4, mfc='white', mec=S3, mew=1.4, zorder=5)
axR.plot(LENS, ch['bypass'], color=S2, lw=2.4, marker='o', ms=4, mfc='white', mec=S2, mew=1.4, zorder=5)
axR.plot(LENS, ch['bypass P=4'], color=S1, lw=1.7, ls=(0,(4,2)), marker='s', ms=3.5,
         mfc='white', mec=S1, mew=1.2, zorder=6)
axR.set_xscale('log')
axR.text(11000, 18.82, 'managed residency -- flat, and fill = 0', fontsize=7.8, color=S3, ha='left')
axR.text(11000, 16.10, 'bypass, freeze once -- fill = 0,\nbut it strands dead KV as churn rises',
         fontsize=7.6, color=S2, ha='left', va='bottom')
axR.text(11000, 17.05, 'bypass + refresh every 4 steps: recovers the\nreduction, but now fills 0.80 GB/step\n'
         'and its 128-step AVERAGE drops to 13.8%',
         fontsize=7.6, color=S1, ha='left', va='bottom')
axR.set_xlim(14000, 13); axR.set_ylim(15.4, 19.2)
axR.set_xlabel('mean request length  [decode steps]        churn increases ->')
axR.set_ylabel('HBM byte reduction, steady state  [%]')
axR.set_title('(b)  churn: the peer session\'s fair baseline. refresh closes the gap\n'
              'on this axis by opening one on the fill axis',
              fontsize=9.2, color=INK, loc='left', pad=8)

fig.text(0.062, 0.955, 'Managed residency is the only rung whose value is a property of the design rather than of the trace',
         fontsize=12.0, color=INK, va='top')
fig.text(0.062, 0.900, 'Llama-3.1-8B, C2 2-layer 600 mm2 (3.164 GB + existing L2). Left: one prefill forward pass ahead of 32 decode steps. '
         'Right: synthetic aperiodic\nledger, 128 steps, warm pass. Bypass here uses a CORRECTED freeze predicate; as shipped it never froze and was plain LIP.',
         fontsize=7.8, color=INK2, va='top', linespacing=1.5)
for ext in ('png','svg'):
    fig.savefig(os.path.join(FIG, f'policy-fragility.{ext}'), dpi=220, facecolor=SURF)
print('bypass across activation range: %.2f -> %.2f%%   managed: %.2f (flat)' % (byp[0], byp[-1], mgd[0]))
print('emission orders:', {k: round(v,2) for k,v in ord_vals.items()})
print('churn (managed / bypass / bypass P=4) at L=30:', [round(ch[k][-2],2) for k in ch])
print('wrote assets/figures/policy-fragility.{png,svg}')
