#!/usr/bin/env python3
"""Catch the predicted delta peak. Closed form (peer session): delta = f * C_tier / base_h with
f = KV/(W+KV), maximised at KV = W (context ~14,318 here), peak = C_tier/(4W)."""
import csv, os, sys
import replay_policies as R
GB=1e9; HERE=os.path.dirname(os.path.abspath(__file__))
CAP3D=R.cap_bytes('C2',600); CAP=R.C0+CAP3D
W_GB=15.010
def one(ctx, steps, mean_len=30):
    p=f'{HERE}/inputs/aperiodic-b8-s{steps}-L{mean_len}-N{ctx}.jsonl'
    stl,wr=R.tiles(p)
    base=R.run(stl,wr,0,'LIP'); bh=base['hbm_ss']
    red=lambda r:100*(1-r['hbm_ss']/bh)
    byp=R.run(stl,wr,CAP3D,'LIP-bypass'); man=R.run(stl,wr,CAP3D,'managed')
    last=stl[-1]
    sw=sum(b for k,b,o in last if o in R.WEIGHT_OBJ); skv=sum(b for k,b,o in last if o not in R.WEIGHT_OBJ)
    f_stream=skv/(sw+skv)
    pred=100*f_stream*CAP3D/bh
    return dict(ctx=ctx,steps=steps,KV_GB=skv/GB,stream_kv_frac=f_stream,
                bypass_pct=red(byp),managed_pct=red(man),delta_pp=red(man)-red(byp),
                predicted_pp=pred,base_hbm_GB=bh/GB)
if __name__=='__main__':
    plan=[(512,64),(1024,64),(2048,64),(4096,64),(8192,64),(16384,24),(32768,24)]
    rows=[]
    print(f"닫힌 형태 예측: 델타 = f x C_tier / base_h,  f = KV/(W+KV),  봉우리는 KV = W = {W_GB} GB")
    print(f"C_tier = {CAP3D/GB:.3f} GB  ->  예측 봉우리 = C_tier/(4W) = {100*CAP3D/GB/(4*W_GB):.2f}%p\n")
    print(f"{'문맥':>7s} {'스텝':>5s} {'KV GB':>8s} {'f':>7s} {'예측':>8s} {'실측':>8s} {'차이':>8s} {'위치':>8s}")
    for ctx,st in plan:
        try: r=one(ctx,st)
        except FileNotFoundError: print(f"{ctx:7d}  (장부 없음)"); continue
        rows.append(r)
        pos='상승' if r['KV_GB']<W_GB*0.9 else ('봉우리' if r['KV_GB']<W_GB*1.4 else '하강')
        print(f"{ctx:7d} {st:5d} {r['KV_GB']:7.2f}G {r['stream_kv_frac']:6.3f} {r['predicted_pp']:7.3f}p "
              f"{r['delta_pp']:7.3f}p {r['delta_pp']-r['predicted_pp']:+7.3f}p {pos:>8s}")
    with open(f'{HERE}/outputs/context_peak.csv','w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"\nwrote outputs/context_peak.csv")
