#!/usr/bin/env python3
"""Single source of truth for 3D SRAM constants, shared by every agent working in this tree.

    from canon_3dsram import C, get
    get('device_3dsram.macro_area_mm2.C2')   -> 0.079254

`python3 scripts/canon_3dsram.py`          prints the canon with provenance grades
`python3 scripts/canon_3dsram.py --check`  greps sibling scripts for hardcoded values that
                                           disagree with the canon and lists them
"""
import json, os, re, sys, glob
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PATH = os.path.join(ROOT, 'assets/sweep/canonical_constants.json')
C = json.load(open(PATH))

def get(dotted):
    o = C
    for k in dotted.split('.'):
        o = o[k]
    return o['value'] if isinstance(o, dict) and 'value' in o else o

def _walk(o, p=''):
    if isinstance(o, dict):
        if 'value' in o:
            yield p, o
        else:
            for k, v in o.items():
                if not k.startswith('_'): yield from _walk(v, f'{p}.{k}' if p else k)

CHECKS = [   # (canon key, regexes that indicate a divergent hardcode, files)
    ('workload.llama31_8b_weight_read_per_step_GB', [r"wstep=15\.1\*GB", r"15\.1\*GB"], 'rounded 15.1 GB; canon 15.010 (LM head included, embedding excluded)'),
    ('device_3dsram.macro_area_mm2', [r"0\.0793\b", r"0\.1201\b", r"0\.0567\b"], '4-digit macro areas; canon 0.079254 / 0.120048 / 0.056658'),
    ('design_point_axes.read_delivery_cap_TBs', [r"ladder_bounds\([^)]*,\s*15\.0\)", r"B_R_DECK\s*=\s*17\.7"], 'single hardcoded read cap; canon carries three caps {15, 17.7, 19} as a scenario axis'),
]

if __name__ == '__main__':
    if '--check' in sys.argv:
        files = [f for f in glob.glob(os.path.join(ROOT, 'scripts/*.py')) if not f.endswith('canon_3dsram.py')]
        bad = 0
        for key, pats, note in CHECKS:
            for f in files:
                s = open(f, encoding='utf8', errors='ignore').read()
                for pat in pats:
                    for m in re.finditer(pat, s):
                        line_no = s[:m.start()].count('\n') + 1
                        line_txt = s.splitlines()[line_no-1]
                        if '# canon:' in line_txt: continue          # intentionally equal to canon, annotated
                        print(f"DIVERGES  {os.path.relpath(f, ROOT)}:{line_no}  '{m.group(0)}'  <- {key}: {note}"); bad += 1
        print(f"\n{bad} hardcoded value(s) diverge from canon" if bad else "\nall checked scripts agree with canon")
        sys.exit(1 if bad else 0)
    print(f"canonical constants ({C['_updated']}) — {PATH}\n")
    for p, o in _walk(C):
        v = o['value'] if 'value' in o else {k: v for k, v in o.items() if k not in ('grade', 'source')}
        print(f"  {p:58s} {str(v):>28s}  [{o.get('grade','')}]")
        if 'source' in o: print(f"  {'':58s} {o['source'][:110]}")
