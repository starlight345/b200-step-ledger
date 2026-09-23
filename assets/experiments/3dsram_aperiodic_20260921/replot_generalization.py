#!/usr/bin/env python3
"""Re-draw the generalization figure from the cached CSV. The replays are the slow part; once
make_generalization_figure.py has written outputs/dead_kv_generalization.csv this redraws in a
second, so caption wording can be iterated without re-running the sweep."""
import csv, os, sys
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
HERE=os.path.dirname(os.path.abspath(__file__))
SURF,INK,INK2,MUTED,GRID,AXIS='#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
S1,S2='#2a78d6','#eb6834'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
 'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})
rows=[r for r in csv.DictReader(open(f'{HERE}/outputs/dead_kv_generalization.csv'))]
if 'normalised' not in rows[0]:
    sys.exit("CSV is still the pre-normalisation version; wait for make_generalization_figure.py")
churn=[(float(r['dead_pct']),float(r['normalised'])) for r in rows if r['family']=='churn']
window=[(float(r['dead_pct']),float(r['normalised']),r['label']) for r in rows if r['family']=='window']
sl={r['family']:float(r['slope_pp']) for r in rows}
fig,ax=plt.subplots(figsize=(7.8,4.7),facecolor=SURF); fig.subplots_adjust(left=0.10,right=0.97,top=0.755,bottom=0.185)
ax.set_facecolor(SURF)
ax.plot([0,100],[0,1.0],lw=1.4,ls='--',color=MUTED,label='general form: normalised delta = dead fraction')
ax.plot([p[0] for p in churn],[p[1] for p in churn],marker='o',ms=6.5,lw=2,color=S1,mfc='white',mew=1.5,
        label=f'churn axis: mean output 10 to 10,000 at 2k context (slope {sl["churn"]:.2f} %p)')
ax.plot([p[0] for p in window],[p[1] for p in window],marker='D',ms=7.5,lw=0,color=S2,mfc='white',mew=1.8,
        label=f'window control: one 8k-context trace, 24 vs 64 steps (slope {sl["window"]:.2f} %p)')
for xx,yy,lb in window: ax.annotate(lb,xy=(xx,yy),xytext=(xx-3.5,yy+0.045),fontsize=7,color=S2,ha='right')
ax.set_xlim(-4,108); ax.set_ylim(-0.05,1.13)
ax.set_xlabel('fraction of the frozen KV whose request has departed  (%)')
ax.set_ylabel('delta / (P_kv / base HBM)   [dimensionless]')
ax.set_title('Two independent ways to move one scalar collapse onto the identity',fontsize=9.6,loc='left',pad=8)
ax.grid(alpha=.25,color=GRID); ax.legend(fontsize=7.1,frameon=False,loc='upper left')
for s_ in ('top','right'): ax.spines[s_].set_visible(False)
ax.text(44,0.30,'The two families sit at different contexts, so their raw %p\nslopes differ by 2x. Normalised by each run\'s own slope they\nshare one line: the arrival distribution, the observation\nwindow and the context only pick where a run sits on this\naxis, not the relationship itself.',fontsize=7.2,color=INK2)
fig.text(0.10,0.905,'The window points are a control: one context at two observation lengths differs only in how much of the pre-populated batch has left.',fontsize=7,color=MUTED)
fig.text(0.10,0.878,'Expect scatter in the middle. The two families reach a given dead fraction by different routes — a running steady state versus a batch draining once —',fontsize=7,color=MUTED)
fig.text(0.10,0.851,'so they need only meet at 0 and at 100%. Tight agreement mid-range would be the suspicious outcome, not the reassuring one.',fontsize=7,color=MUTED)
fig.text(0.10,0.055,'Each family sits a constant distance above the identity — 0.0026 for churn, 0.0010 for the window control. Restored to bytes through each run\'s own base HBM,',fontsize=6.8,color=MUTED)
fig.text(0.10,0.030,'both are one tile: 1.016 MiB and 1.031 MiB. The offset is the replay\'s 1 MiB granularity, not a mechanism, which is why it must be quoted in bytes rather than in %p.',fontsize=6.8,color=MUTED)
fig.text(0.10,0.005,'Trace replay, not a measurement. Raw values in outputs/dead_kv_generalization.csv.',fontsize=6.8,color=MUTED)
for suf in ('png','svg'): fig.savefig(f'{HERE}/outputs/dead_kv_generalization.{suf}',facecolor=SURF,dpi=200 if suf=='png' else None)
print('replotted from CSV')
for r in rows: print(f"  {r['family']:7s} {r['label']:18s} dead {float(r['dead_pct']):5.1f}%  normalised {float(r['normalised']):.3f}")
