#!/usr/bin/env python3
"""Context sweep: the tier's total value falls while admission's share of it rises."""
import csv, os
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
SURF,INK,INK2,MUTED,GRID,AXIS='#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
S1,S2,S3='#2a78d6','#eb6834','#1baf7a'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial','DejaVu Sans'],'font.size':8.5,
 'svg.fonttype':'none','axes.edgecolor':AXIS,'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK})
R=[{k:(int(v) if k in ('ctx','steps') else float(v)) for k,v in r.items()} for r in csv.DictReader(open(f'{HERE}/outputs/context_final.csv'))]
x=[r['ctx'] for r in R]
fig,axs=plt.subplots(1,2,figsize=(11.4,4.4),facecolor=SURF)
fig.subplots_adjust(left=0.065,right=0.945,top=0.775,bottom=0.155,wspace=0.30)
# A: absolute falls, share rises
ax=axs[0]; ax.set_facecolor(SURF); ax.set_xscale('log',base=2)
ax.plot(x,[r['managed'] for r in R],marker='o',ms=6,lw=2.2,color=S1,mfc='white',mew=1.5,label='managed: total HBM reduction')
ax.plot(x,[r['bypass'] for r in R],marker='s',ms=5,lw=1.8,color=S2,mfc='white',mew=1.3,label='bypass: same, without admission')
ax.set_xlabel('context length (tokens)'); ax.set_ylabel('HBM logical-byte reduction (%)')
ax.set_xticks(x); ax.set_xticklabels([f'{v//1024}k' if v>=1024 else str(v) for v in x])
ax.minorticks_off(); ax.grid(alpha=.25,color=GRID); ax.legend(fontsize=7.4,frameon=False,loc='upper right')
for s_ in ('top','right'): ax.spines[s_].set_visible(False)
ax.set_title('A  The tier buys less as context grows',fontsize=9.5,loc='left',pad=8)
ax.annotate('',xy=(x[-1],R[-1]['managed']),xytext=(x[-1],R[-1]['bypass']),arrowprops=dict(arrowstyle='<->',color=INK2,lw=1.0))
ax.text(x[-1]*0.93,(R[-1]['managed']+R[-1]['bypass'])/2,'delta',fontsize=7.2,color=INK2,ha='right',va='center')
rb=R[0]['bypass']/R[-1]['bypass']; rm=R[0]['managed']/R[-1]['managed']
ax.text(700,6.4,'They do not collapse at the same rate:\n'
  f'without admission  {R[0]["bypass"]:.1f}% -> {R[-1]["bypass"]:.1f}%  ({rb:.1f}x)\n'
  f'with admission     {R[0]["managed"]:.1f}% -> {R[-1]["managed"]:.1f}%  ({rm:.1f}x)\n'
  'At 32k a tier without admission is worth almost\nnothing; with it, a third survives.',
  fontsize=7.0,color=INK2,va='top')
# B: delta and share
ax2=axs[1]; ax2.set_facecolor(SURF); ax2.set_xscale('log',base=2)
ax2.plot(x,[r['delta'] for r in R],marker='o',ms=6,lw=2.2,color=S1,mfc='white',mew=1.5,label='delta (%p, left)')
ax2.set_ylabel('rung 4 minus rung 3b  (%p)',color=S1); ax2.tick_params(axis='y',labelcolor=S1)
ax2.set_xlabel('context length (tokens)')
ax2.set_xticks(x); ax2.set_xticklabels([f'{v//1024}k' if v>=1024 else str(v) for v in x]); ax2.minorticks_off()
pk=max(R,key=lambda r:r['delta'])
ax2.plot([pk['ctx']],[pk['delta']],marker='o',ms=11,mfc='none',mec=S1,mew=1.8)
ax2.annotate(f"peak {pk['delta']:.2f} %p at {pk['ctx']//1024}k\n(closed form predicted 14-16k)",
  xy=(pk['ctx'],pk['delta']),xytext=(1100,4.9),fontsize=7.2,color=S1,
  arrowprops=dict(arrowstyle='->',color=S1,lw=0.9))
ax3=ax2.twinx(); ax3.set_facecolor('none')
ax3.plot(x,[r['share'] for r in R],marker='^',ms=5.5,lw=1.8,ls='--',color=S3,mfc='white',mew=1.3,label='delta / managed (%, right)')
ax3.set_ylabel('admission share of the tier\'s value (%)',color=S3); ax3.tick_params(axis='y',labelcolor=S3)
for s_ in ('top',): ax2.spines[s_].set_visible(False); ax3.spines[s_].set_visible(False)
ax2.grid(alpha=.25,color=GRID)
h1,l1=ax2.get_legend_handles_labels(); h2,l2=ax3.get_legend_handles_labels()
ax2.legend(h1+h2,l1+l2,fontsize=7.4,frameon=False,loc='lower right')
ax2.set_title('B  But what you refuse to admit dominates what is left',fontsize=9.5,loc='left',pad=8)
fig.suptitle('Context length: admission matters more exactly where the tier matters less   C2, 600 mm²/die/tier, 3.16 GB, batch 8, mean output 30',
  x=0.065,y=0.955,ha='left',fontsize=9.7,color=INK)
fig.text(0.065,0.885,'All seven points at 64 steps with dead-KV saturated at 100%. A 24-step run understated 16k/32k by exactly its 75% dead fraction, which the general form predicts.',fontsize=7,color=MUTED)
fig.text(0.065,0.03,'Trace replay of a synthetic aperiodic ledger, not a measurement. Absolute reduction falls because a fixed 3.16 GB tier covers a growing stream; the share rises because more of a first-fill tier is KV that dies.',fontsize=6.8,color=MUTED)
for suf in ('png','svg'): fig.savefig(f'{HERE}/outputs/context_admission.{suf}',facecolor=SURF,dpi=200 if suf=='png' else None)
print('wrote outputs/context_admission.{png,svg}')
