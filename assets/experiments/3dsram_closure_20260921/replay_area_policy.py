#!/usr/bin/env python3
from pathlib import Path
from collections import OrderedDict
import json,csv,math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
# Gate 0 (2026-09-21): the preserved 2026-09-16 ledger omits the LM head, which decode reads in
# full every step. That omission is the 7.08% gap against the canonical accounting. LEDGER selects
# which one to replay; 'unified' is canon (weight-side 15.010 GB/step), 'legacy' reproduces the
# earlier figure. Set LEDGER=legacy to regenerate the pre-Gate-0 numbers.
import os
LEDGER=os.environ.get('LEDGER','unified')
SRC=ROOT/('inputs/llama-b8-l2048-events-unified.jsonl' if LEDGER=='unified' else 'inputs/llama-b8-l2048-events.jsonl')
OUT=ROOT/('outputs' if LEDGER=='unified' else 'outputs_legacy'); OUT.mkdir(exist_ok=True)
MiB=2**20; STEPS=32; C0=132_644_864; TILE=MiB
USABLE=(1-.12)*(1-.05); BYTES_PER_MACRO=1_000_000/8*USABLE
MACRO={'C2':(153,518),'C3':(183,656)}
ev=[json.loads(x) for x in SRC.read_text().splitlines()]
ev=[e for e in ev if e.get('kind')=='event' and e.get('model_tag')=='llama' and e.get('batch')==8 and e.get('context')==2048]
reads=[e for e in ev if e['op']=='read']; writes=[e for e in ev if e['op']=='write']
F=sum(e['bytes'] for e in reads); W=sum(e['bytes'] for e in writes)
trace=[]
for e in reads:
 for i,off in enumerate(range(0,e['bytes'],TILE)):
  trace.append(((e['layer'],e['object'],i),min(TILE,e['bytes']-off)))
class Cache:
 def __init__(self,cap,policy): self.cap=int(cap);self.policy=policy;self.d=OrderedDict();self.live=0;self.ins=0
 def access(self,k,n):
  if k in self.d: self.d.move_to_end(k);return True
  if n>self.cap:return False
  while self.live+n>self.cap:
   _,x=self.d.popitem(last=False);self.live-=x
  self.d[k]=n;self.live+=n;self.ins+=1
  if self.policy=='LIP' or (self.policy=='BIP' and self.ins%32):self.d.move_to_end(k,last=False)
  return False
def replay(top,policy='LIP',lower=None):
 a=Cache(top,policy);b=Cache(lower,policy) if lower else None;hbm=0;lower_access=0;last=0
 for s in range(STEPS):
  step=0
  for k,n in trace:
   if a.access(k,n):continue
   if b:
    lower_access+=n
    if b.access(k,n):continue
   hbm+=n;step+=n
  if s==STEPS-1:last=step
 return {'hbm_bytes_step':hbm/STEPS+W,'last_hbm_bytes_step':last+W,'tier_lookup_bytes_step':lower_access/STEPS if b else 0}
def capacity(case,area,layers):
 w,h=MACRO[case];n=math.floor(area/(w*h/1e6));return n*BYTES_PER_MACRO*layers*2,n
base=replay(C0,'LIP'); base_h=base['hbm_bytes_step']
rows=[]
for case in MACRO:
 for layers in (1,2):
  for area in (400,500,600,700,800):
   cap,n=capacity(case,area,layers)
   configs={
    'keep_sL2_separate_3D_LIP':replay(C0,'LIP',cap),
    'integrated_sL2_plus_3D_LIP':replay(C0+cap,'LIP'),
    'remove_sL2_3D_only_LIP':replay(cap,'LIP'),
    'integrated_sL2_plus_3D_LRU':replay(C0+cap,'LRU'),
   }
   ideal=max(0,base_h-(F-max(0,min(F,C0+cap))*(STEPS-1)/STEPS+W))
   for name,x in configs.items():
    red=1-x['hbm_bytes_step']/base_h
    for phi in (.25,.5,.75,1.0):
     rows.append(dict(case=case,layers=layers,net_area_mm2_per_die_tier=area,macros_per_die_tier=n,capacity_GB_gpu=cap/1e9,architecture=name,hbm_GiB_step=x['hbm_bytes_step']/2**30,hbm_reduction_percent=100*red,tier_lookup_GiB_step=x['tier_lookup_bytes_step']/2**30,p99_hbm_fraction=phi,optimistic_p99_reduction_percent=100*phi*red,optimistic_speedup=1/(1-phi*red)))
   rows.append(dict(case=case,layers=layers,net_area_mm2_per_die_tier=area,macros_per_die_tier=n,capacity_GB_gpu=cap/1e9,architecture='ideal_nonoverlap_retention_bound',hbm_GiB_step=(base_h-ideal)/2**30,hbm_reduction_percent=100*ideal/base_h,tier_lookup_GiB_step=0,p99_hbm_fraction='',optimistic_p99_reduction_percent='',optimistic_speedup=''))
with (OUT/'closure_area_policy.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
# Summary at 600, 2 layers, phi rows collapsed to 0.5
summary=[r for r in rows if r['net_area_mm2_per_die_tier']==600 and r['layers']==2 and (r['p99_hbm_fraction']==.5 or r['architecture']=='ideal_nonoverlap_retention_bound')]
(OUT/'closure_summary.json').write_text(json.dumps({'scope':'logical object-tile replay; not hardware cache, HBM counters, or measured p99','ledger':LEDGER,'steps':STEPS,'logical_read_GiB_step':F/2**30,'logical_append_write_MiB_step':W/MiB,'baseline_existing_sL2_LIP_HBM_GiB_step':base_h/2**30,'rows_600mm2_2layer':summary},ensure_ascii=False,indent=2))
# Plot HBM reduction, two layers only; architecture compare C2/C3.
# Three of the five series coincide, and that coincidence IS the result, so they are drawn with
# distinct widths/dashes and annotated rather than left hidden under one another:
#   keep_sL2_separate == remove_sL2  to 4 decimals -> the existing 126 MB L2 contributes nothing
#                                       to this 15 GiB/step stream, so deleting it changes nothing.
#   integrated_LIP    ~= ideal bound (0.007 %p)   -> one merged scan-resistant cache already reaches
#                                       the managed non-overlap upper bound.
# Draw order: widest/faintest first so the coincident partner stays visible underneath.
fig,axs=plt.subplots(1,2,figsize=(11.6,4.8),sharey=True,layout='constrained')
STYLE=[  # arch, color, linewidth, dash, marker, markersize, zorder
 ('ideal_nonoverlap_retention_bound','#1f4e79',6.0,(None,None),None,0,2),
 ('integrated_sL2_plus_3D_LIP','#1b9e77',2.0,(None,None),'o',5.5,5),
 ('keep_sL2_separate_3D_LIP','#d95f02',5.5,(None,None),None,0,3),
 ('remove_sL2_3D_only_LIP','#7570b3',1.8,(3,2.2),'o',4.5,4),
 ('integrated_sL2_plus_3D_LRU','#777777',2.0,(None,None),'o',5.0,5),
]
labels={'keep_sL2_separate_3D_LIP':'keep existing B200 L2 + separate 3D (LIP)','integrated_sL2_plus_3D_LIP':'integrated existing L2 + 3D (LIP)','remove_sL2_3D_only_LIP':'remove existing L2, 3D only (LIP)  — identical to "keep"','integrated_sL2_plus_3D_LRU':'integrated LRU','ideal_nonoverlap_retention_bound':'managed non-overlap upper bound'}
def series(case,arch):
 xs=[];ys=[]
 for a in (400,500,600,700,800):
  rr=[r for r in rows if r['case']==case and r['layers']==2 and r['net_area_mm2_per_die_tier']==a and r['architecture']==arch]
  if arch!='ideal_nonoverlap_retention_bound':rr=[r for r in rr if r['p99_hbm_fraction']==.5]
  xs.append(a);ys.append(rr[0]['hbm_reduction_percent'])
 return xs,ys
for ax,case in zip(axs,('C3','C2')):
 for arch,col,lw,dash,mk,ms,z in STYLE:
  xs,ys=series(case,arch)
  ax.plot(xs,ys,lw=lw,dashes=dash if dash[0] else (1,0),color=col,marker=mk,ms=ms,mfc='white',mew=1.6,label=labels[arch],zorder=z,solid_capstyle='round')
 ax.axvline(600,ls=':',color='#444',lw=1);ax.set_title(f'{case}, 2 memory tiers, 2 dies')
 ax.set_xlabel('net macro-placeable area / die / tier (mm²)');ax.grid(alpha=.2)
 ax.set_xlim(370,860)
 if case=='C3':   # annotate once, on the left panel, so the right panel stays clean for the legend
  kx,ky=series(case,'keep_sL2_separate_3D_LIP');ix,iy=series(case,'integrated_sL2_plus_3D_LIP');bx,by_=series(case,'ideal_nonoverlap_retention_bound');gx,gy=series(case,'integrated_sL2_plus_3D_LRU')
  ax.annotate('"keep" and "remove" coincide exactly: in THIS replay\nthe existing 126 MB L2 adds no HBM-byte reduction,\nso removing it changes nothing here',
    xy=(500,ky[1]),xytext=(405,ky[1]+7.2),fontsize=7.2,color='#d95f02',
    arrowprops=dict(arrowstyle='->',color='#d95f02',lw=0.9,shrinkA=0,shrinkB=4))
  ax.annotate('integrated LIP lands within %.3f %%p\nof the managed upper bound'%abs(by_[4]-iy[4]),
    xy=(770,iy[4]-0.35),xytext=(600,6.2),fontsize=7.2,color='#1b9e77',ha='left',
    arrowprops=dict(arrowstyle='->',color='#1b9e77',lw=0.9,shrinkA=2,shrinkB=4,connectionstyle='arc3,rad=-0.15'))
  ax.annotate('plain LRU is flat at %.2f %%: capacity cannot fix the policy'%gy[0],
    xy=(600,gy[2]),xytext=(410,gy[2]+3.6),fontsize=7.2,color='#555',
    arrowprops=dict(arrowstyle='->',color='#777',lw=0.9,shrinkA=0,shrinkB=4))
axs[0].set_ylabel('HBM logical bytes reduction vs existing-L2 LIP baseline (%)')
axs[1].legend(fontsize=7.2,frameon=False,loc='upper left',handlelength=2.6,borderpad=0.2)
fig.suptitle('Area and L2 organization change HBM traffic; latency is still a projection',fontsize=12,y=1.02)
fig.text(0.008,-0.02,'Existing L2 = the B200 silicon L2, 132,644,864 B measured. LIP = LRU-insertion policy (new lines enter at LRU), a scan-resistant variant. '
 'Logical object-tile replay of 96 preserved events; not a hardware cache model, not HBM counters, not measured latency.',fontsize=6.8,color='#555')
fig.savefig(OUT/'closure_area_policy.png',dpi=180,bbox_inches='tight');fig.savefig(OUT/'closure_area_policy.svg',bbox_inches='tight')
print(json.dumps(json.loads((OUT/'closure_summary.json').read_text()),ensure_ascii=False,indent=2))
