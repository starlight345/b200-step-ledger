#!/usr/bin/env python3
"""16,384 / 32,768 at the SAME 64 steps as the rest. The 24-step run was a confound: dead-KV
saturated at only 75%, understating the delta by the same 75%."""
import csv, os
import replay_policies as R
GB=1e9; HERE=os.path.dirname(os.path.abspath(__file__)); cap=R.cap_bytes('C2',600); CAP=R.C0+cap
rows=[]
for ctx in (16384, 32768):
    p=f'{HERE}/inputs/aperiodic-b8-s64-L30-N{ctx}.jsonl'
    stl,wr=R.tiles(p)
    base=R.run(stl,wr,0,'LIP'); bh=base['hbm_ss']
    red=lambda r:100*(1-r['hbm_ss']/bh)
    byp=R.run(stl,wr,cap,'LIP-bypass'); man=R.run(stl,wr,cap,'managed')
    t=R.Tier(CAP,'LIP-bypass')
    for _ in range(2):
        for i,st in enumerate(stl):
            t.step=i
            for k,b,obj in st: t.access(k,b,obj)
    live={k[2] for k,_,_ in stl[-1] if k[2]>=0}
    w=sum(n for k,n in t.d.items() if k[1] in R.WEIGHT_OBJ); kv=sum(n for k,n in t.d.items() if k[1] not in R.WEIGHT_OBJ)
    dead=sum(n for k,n in t.d.items() if k[1] not in R.WEIGHT_OBJ and k[2] not in live)
    last=stl[-1]; sw=sum(b for k,b,o in last if o in R.WEIGHT_OBJ); skv=sum(b for k,b,o in last if o not in R.WEIGHT_OBJ)
    r=dict(ctx=ctx,steps=64,f_stream=skv/(sw+skv),f_res=kv/(w+kv),dead_frac=dead/max(kv,1),
           bypass_pct=red(byp),managed_pct=red(man),delta_pp=red(man)-red(byp),
           share=(red(man)-red(byp))/red(man),base_hbm_GB=bh/GB)
    rows.append(r)
    print(f"ctx {ctx}: 델타 {r['delta_pp']:.3f}p, managed {r['managed_pct']:.3f}%, 비중 {100*r['share']:.1f}%, "
          f"f_res {r['f_res']:.3f}, 죽은KV {100*r['dead_frac']:.1f}%", flush=True)
with open(f'{HERE}/outputs/context_peak_64.csv','w',newline='') as f:
    w_=csv.DictWriter(f,fieldnames=list(rows[0])); w_.writeheader(); w_.writerows(rows)
print("wrote outputs/context_peak_64.csv")
