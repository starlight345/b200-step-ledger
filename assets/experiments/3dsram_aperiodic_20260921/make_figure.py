#!/usr/bin/env python3
"""Rung 4 earns a delta only once the trace stops being cyclic (2026-09-21)."""
import csv, collections, os
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=os.path.dirname(os.path.abspath(__file__))
SURF,INK,INK2,MUTED,GRID,AXIS='#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
S1,S2,S3,S4='#2a78d6','#eb6834','#1baf7a','#e34948'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
  'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})
rows=[r for r in csv.DictReader(open(f'{HERE}/outputs/aperiodic_policies.csv'))]
by=collections.defaultdict(dict)
for r in rows: by[(int(r['mean_len']),int(r['requests']))][r['policy']]=r
keys=sorted(by, key=lambda k:k[1]/128)
x=[k[1]/128 for k in keys]
def ser(pol,f): return [float(by[k][pol][f]) for k in keys]
fig,axs=plt.subplots(1,2,figsize=(11.2,4.3),facecolor=SURF)
fig.subplots_adjust(left=0.07,right=0.985,top=0.78,bottom=0.15,wspace=0.24)
ax=axs[0]; ax.set_facecolor(SURF)
for pol,col,lbl in (('managed',S1,'managed: admit weight only (rung 4)'),
                    ('LIP-bypass',S2,'LIP + bypass: fill once, freeze (rung 3b)'),
                    ('LIP',S3,'LIP: demand-filled (rung 3)'),
                    ('managed+KV',S4,'managed + KV in the slack')):
    ax.plot(x,ser(pol,'reduction_ss_pct'),marker='o',ms=5,lw=2,color=col,label=lbl,mfc='white',mew=1.4)
ax.set_xlabel('request churn: departures per step  (arrivals / 128 steps)')
ax.set_ylabel('HBM logical-byte reduction, steady state (%)')
ax.set_title('A  Policies separate only when requests turn over',fontsize=9.4,loc='left',pad=8)
ax.grid(alpha=.25,color=GRID); ax.legend(fontsize=7,frameon=False,loc='center right')
for s_ in ('top','right'): ax.spines[s_].set_visible(False)
ax.annotate('near-cyclic: all policies coincide\n(the closure replay lives here)',xy=(x[0],18.43),xytext=(0.12,17.0),
  fontsize=7.2,color=MUTED,arrowprops=dict(arrowstyle='->',color=MUTED,lw=0.9))
ax2=axs[1]; ax2.set_facecolor(SURF)
d_ss=[float(by[k]['managed']['reduction_ss_pct'])-float(by[k]['LIP-bypass']['reduction_ss_pct']) for k in keys]
d_av=[float(by[k]['managed']['reduction_avg_pct'])-float(by[k]['LIP-bypass']['reduction_avg_pct']) for k in keys]
ax2.plot(x,d_ss,marker='o',ms=5,lw=2.2,color=S1,label='steady state (last step)',mfc='white',mew=1.4)
ax2.plot(x,d_av,marker='s',ms=4.5,lw=1.6,color=S1,alpha=.45,label='128-step average',mfc='white',mew=1.2)
kv=12.2
ax2.axhline(2.38,color=MUTED,lw=0.9,ls=':')
ax2.text(0.30,2.44,'saturates at 2.38 %p',fontsize=7.2,color=MUTED)
ax2.set_xlabel('request churn: departures per step'); ax2.set_ylabel('rung 4 minus rung 3b  (%p)')
ax2.set_title('B  What rung 4 buys, and why',fontsize=9.4,loc='left',pad=8)
ax2.grid(alpha=.25,color=GRID); ax2.legend(fontsize=7.2,frameon=False,loc='lower right')
for s_ in ('top','right'): ax2.spines[s_].set_visible(False)
ax2.text(0.06,1.55,'Mechanism: bypass freezes whatever arrived first,\nso %.1f%% of its resident set is request KV that\ndies when that request leaves. managed admits\nweight only, so its resident set is 100%% live.'%kv,
  fontsize=7.2,color=INK2,va='top')
fig.suptitle('Does explicit admission beat "fill once and freeze"?  C2, 600 mm²/die/tier, 2 tiers, 2 dies, 3.16 GB, batch 8',
  x=0.07,y=0.955,ha='left',fontsize=9.8,color=INK)
fig.text(0.07,0.885,'Synthetic aperiodic decode ledger: Poisson arrivals, lognormal lengths, seeded. Per-layer interleaving of weight and KV reads, as real decode issues them.',fontsize=7,color=MUTED)
fig.text(0.07,0.03,'Trace replay of a synthetic ledger, not a measurement and not a real serving trace. Both tier sides are counted; bypass and managed both hold steady-state fill at 0. '
 'A real trace (ShareGPT, Azure) has a different churn distribution and would move the delta.',fontsize=6.8,color=MUTED)
out=f'{HERE}/outputs/aperiodic_rung4_delta'
for suf,kw in (('svg',{}),('png',{'dpi':200})): fig.savefig(f'{out}.{suf}',facecolor=SURF,**kw)
print('wrote outputs/aperiodic_rung4_delta.{svg,png}')
