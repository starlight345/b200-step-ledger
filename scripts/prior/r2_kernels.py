#!/usr/bin/env python3
"""R2 load-class check: from an NVBit kernel listing, one decode step's kernels and the ids to trace.

The harness (llm_policy_bench.py --mode profile --warmup 10 --prof 2) ends with identical decode steps, so
  K = kernels per step = the period of the name sequence at the tail (as asim_r1.sh);
  P = kernels per layer = the period inside the last step (all layers run the same operators on the same shapes),
      found with the offset s of layer 0 (embedding and other per-step kernels come first);
  picks = the last step's prefix + layer 0 + everything after the last layer (final norm, LM head, sampling), so
      every distinct kernel of the step is traced exactly once per position in a layer.
Usage: python3 r2_kernels.py TRACES_DIR  (stats_ctx_* inside)  -> JSON on stdout
"""
import csv, glob, json, subprocess, sys

def main(d):
    rows = list(csv.reader(open(glob.glob(d + '/stats_ctx_*')[0])))[1:]
    ids = [int(r[0].split('-')[1]) for r in rows]
    names = [r[1].strip() for r in rows]
    N = len(names)
    K = next(k for k in range(10, N // 4) if names[-k:] == names[-2 * k:-k] == names[-3 * k:-2 * k])
    step = names[-K:]; sid = ids[-K:]
    best = None
    for s in range(0, 40):
        for p in range(8, K // 2):
            L = (K - s) // p
            if L < 4: break
            if all(step[s + i * p:s + (i + 1) * p] == step[s:s + p] for i in range(1, L)) and \
                    step[s + L * p:s + (L + 1) * p] != step[s:s + p]:
                if best is None or L * p > best[1] * best[2]: best = (s, L, p)
                break
    s, L, P = best
    picks = sid[:s + P] + sid[s + L * P:]
    uniq = sorted(set(step), key=step.index)
    code = {n: f'k{i}' for i, n in enumerate(uniq)}
    dm = subprocess.run(['c++filt'], input='\n'.join(uniq), capture_output=True, text=True).stdout.splitlines()
    out = dict(N=N, K=K, step_first_id=sid[0], prefix=s, layers=L, per_layer=P, tail=K - s - L * P,
               picks=picks,
               kernels={code[n]: dict(mangled=n, name=(dm[i] if i < len(dm) else n)[:160], per_step=step.count(n),
                                      in_layer=step[s:s + P].count(n))
                        for i, n in enumerate(uniq)},
               step=[code[n] for n in step[:s]], layer=[code[n] for n in step[s:s + P]],
               tail_seq=[code[n] for n in step[s + L * P:]])
    print(json.dumps(out, indent=1))

if __name__ == '__main__':
    main(sys.argv[1])
