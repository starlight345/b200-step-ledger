#!/usr/bin/env python3
"""The delta depends on one scalar. Two independent ways of moving that scalar collapse onto y = x.

NOTE: the two families sit at different contexts (churn at 2,048, window control at 8,192), so their
slopes P_kv/base_h differ by 2x. Plotting raw %p puts them on two different lines, which an earlier
draft of this figure did while claiming they coincided. The claim is about the SHAPE, so the y axis
is the delta normalised by that run's own P_kv/base_h; then both families must fall on the identity.

x = fraction of the frozen KV whose request has departed
  churn axis   : 8 settings, mean output length 10 -> 10,000, all at 128 steps
  window axis  : the SAME context at 24 vs 64 steps, which changes only how much of the
                 pre-populated batch has had time to leave
If the general form were wrong, these two families would not overlap.
"""
import csv, os
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import replay_policies as R
GB=1e9; HERE=os.path.dirname(os.path.abspath(__file__)); cap=R.cap_bytes('C2',600); CAP=R.C0+cap
SURF,INK,INK2,MUTED,GRID,AXIS='#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
S1,S2='#2a78d6','#eb6834'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
 'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})

def probe(path):
    stl,wr=R.tiles(path)
    base=R.run(stl,wr,0,'LIP'); bh=base['hbm_ss']
    red=lambda r:100*(1-r['hbm_ss']/bh)
    byp=R.run(stl,wr,cap,'LIP-bypass'); man=R.run(stl,wr,cap,'managed')
    t=R.Tier(CAP,'LIP-bypass')
    for _ in range(2):
        for i,st in enumerate(stl):
            t.step=i
            for k,b,obj in st: t.access(k,b,obj)
    live={k[2] for k,_,_ in stl[-1] if k[2]>=0}
    kv=sum(n for k,n in t.d.items() if k[1] not in R.WEIGHT_OBJ)
    dead=sum(n for k,n in t.d.items() if k[1] not in R.WEIGHT_OBJ and k[2] not in live)
    return dead/max(kv,1), red(man)-red(byp), 100*kv/bh   # dead fraction, delta %p, this run's slope

churn=[]; window=[]; rows=[]
for L in (10000,1000,300,120,60,30,16,10):
    p=f'{HERE}/inputs/aperiodic-b8-s128-L{L}-N2048.jsonl'
    if not os.path.exists(p): p=f'{HERE}/inputs/aperiodic-b8-s128-L{L}.jsonl'
    d,dl,sl=probe(p); churn.append((100*d,dl/sl)); rows.append(dict(family='churn',label=f'mean output {L}',ctx=2048,dead_pct=100*d,delta_pp=dl,slope_pp=sl,normalised=dl/sl))
for st in (24,64):
    p=f'{HERE}/inputs/aperiodic-b8-s{st}-L30-N8192.jsonl'
    if os.path.exists(p):
        d,dl,sl=probe(p); window.append((100*d,dl/sl,f'{st} steps')); rows.append(dict(family='window',label=f'{st} steps',ctx=8192,dead_pct=100*d,delta_pp=dl,slope_pp=sl,normalised=dl/sl))
with open(f'{HERE}/outputs/dead_kv_generalization.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
fig,ax=plt.subplots(figsize=(7.6,4.6),facecolor=SURF); fig.subplots_adjust(left=0.10,right=0.97,top=0.775,bottom=0.15)
ax.set_facecolor(SURF)
ax.plot([0,100],[0,1.0],lw=1.4,ls='--',color=MUTED,label='general form: normalised delta = dead fraction')
ax.plot([p[0] for p in churn],[p[1] for p in churn],marker='o',ms=6.5,lw=2,color=S1,mfc='white',mew=1.5,label='churn axis: mean output 10 to 10,000 at 2k context, 128 steps')
ax.plot([p[0] for p in window],[p[1] for p in window],marker='D',ms=7.5,lw=0,color=S2,mfc='white',mew=1.8,label='window control: one 8k-context trace at 24 vs 64 steps')
for xx,yy,lb in window: ax.annotate(lb,xy=(xx,yy),xytext=(xx-3.5,yy+0.045),fontsize=7,color=S2,ha='right')
ax.set_xlim(-4,108); ax.set_ylim(-0.05,1.13)
ax.set_xlabel('fraction of the frozen KV whose request has departed  (%)')
ax.set_ylabel('delta / (P_kv / base HBM)   [dimensionless]')
ax.set_title('Two independent ways to move one scalar collapse onto the identity',fontsize=9.6,loc='left',pad=8)
ax.grid(alpha=.25,color=GRID); ax.legend(fontsize=7.2,frameon=False,loc='upper left')
for s_ in ('top','right'): ax.spines[s_].set_visible(False)
ax.text(44,0.30,'The two families sit at different contexts, so their raw\n%p slopes differ by 2x (2.36 vs 4.74 %p at saturation).\nNormalised by each run\'s own slope they coincide: the\narrival distribution and the observation window only pick\nwhere a run sits on this axis, not the relationship.',fontsize=7.2,color=INK2)
fig.text(0.10,0.905,'The window points are a control: the same context at two observation lengths differs only in how much of the pre-populated batch has left.',fontsize=7,color=MUTED)
fig.text(0.10,0.885,'A continuously running server sits at 100% — bypass freezes once, so every request resident at that moment eventually departs.',fontsize=7,color=MUTED)
fig.text(0.10,0.03,'Trace replay, not a measurement. Raw values in outputs/dead_kv_generalization.csv. Residual is O(one 1 MiB tile) over base HBM, which is why it shrinks as the stream grows.',fontsize=6.8,color=MUTED)
for suf in ('png','svg'): fig.savefig(f'{HERE}/outputs/dead_kv_generalization.{suf}',facecolor=SURF,dpi=200 if suf=='png' else None)
print('wrote outputs/dead_kv_generalization.{png,svg}')
print(f"  churn {len(churn)} points (ctx 2048), window control {len(window)} points (ctx 8192)")
for r in rows: print(f"    {r['family']:7s} {r['label']:18s} dead {r['dead_pct']:5.1f}%  delta {r['delta_pp']:5.3f}p  slope {r['slope_pp']:5.3f}p  normalised {r['normalised']:.3f}")
