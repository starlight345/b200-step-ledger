#!/usr/bin/env python3
"""Summary of the static load-hint census (load_hint_census.py on dsil-sy -> assets/sweep/load_hint_census{,_new}/*.jsonl).

Two software stacks: the one our measurements ran on (PyTorch 2.8 + cuBLAS 12.8.4, with vLLM 0.10.2 from the same
host; lhc_all.sh) and the current serving stacks (vLLM 0.28.0 + cuBLAS 13.1.1, SGLang 0.5.17 sgl_kernel; lhc_new.sh).
The library label is the JSONL file name (the sm90 and sm100 builds of sgl_kernel share a basename).

Per library and architecture generation (sm_80 / sm_90 / sm_100 / sm_120; the 'a' variants folded in): kernels with
global loads, kernels with an evict-first load (.EF), kernels whose loads use a kernel-built cache-policy descriptor
(createpolicy), and the kernel families behind each. Families are recomputed here from the mangled names (local
c++filt) so the naming rule can change without re-running cuobjdump.
Usage: python3 scripts/prior/load_hint_summary.py  -> assets/sweep/load_hint_summary.json
"""
import glob, json, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import load_hint_census as L

GEN = lambda a: a.rstrip('a')
STACKS = (('assets/sweep/load_hint_census', 'torch 2.8 / vLLM 0.10.2 / cuBLAS 12.8.4'),
          ('assets/sweep/load_hint_census_new', 'vLLM 0.28.0 / cuBLAS 13.1.1 / SGLang 0.5.17'))

if __name__ == '__main__':
    rows = []
    for d, stack in STACKS:
        for p in sorted(glob.glob(os.path.join(d, '*.jsonl'))):
            lib = os.path.basename(p)[:-len('.jsonl')].replace('venv-llm__', '').replace('venv-sglang__', '')
            rows += [dict(json.loads(l), stack=stack, lib=lib) for l in open(p)]
    dm = L.demangle(sorted({r['name'] for r in rows}))
    S = defaultdict(lambda: dict(kernels=set(), loads=set(), ef=set(), built=set(), fam={}))
    for r in rows:
        fam = L.family(dm.get(r['name'], r['name']))
        s = S[(r['stack'], r['lib'], GEN(r['arch']))]
        s['kernels'].add(r['name']); s['fam'][r['name']] = fam            # sm_XX and sm_XXa copies count once
        if r['variants']: s['loads'].add(r['name'])
        if r['ef']: s['ef'].add(r['name'])
        if r['custom_desc']: s['built'].add(r['name'])
    out = {}
    last = None
    for (stack, lib, gen), s in sorted(S.items()):
        if stack != last: print(f'### {stack}'); last = stack
        d = dict(kernels=len(s['kernels']), with_loads=len(s['loads']), evict_first=len(s['ef']), kernel_built_desc=len(s['built']),
                 ef_families=Counter(s['fam'][n] for n in s['ef']).most_common(12),
                 built_families=Counter(s['fam'][n] for n in s['built']).most_common(12))
        out[f'{stack} | {lib} | {gen}'] = d
        print(f"{lib[-44:]:<46}{gen:<7} kernels {d['kernels']:>5}  with loads {d['with_loads']:>5}  .EF {d['evict_first']:>4}  "
              f"kernel-built desc {d['kernel_built_desc']:>4}")
        if d['ef_families']: print('      .EF   :', ', '.join(f'{f} {n}' for f, n in d['ef_families'][:6]))
        if d['built_families']: print('      built :', ', '.join(f'{f} {n}' for f, n in d['built_families'][:6]))
    json.dump(out, open('assets/sweep/load_hint_summary.json', 'w'), indent=1)
    print('wrote assets/sweep/load_hint_summary.json')
