#!/usr/bin/env python3
"""Print the numbers R2's pre-registered checks refer to, straight from the frozen r2_predictions (no hand copying).

Per workload: the v3 load classes (from SASS), step bytes, the baseline each predictor expects, the set-aside
contrast at window 127 MiB, hitRatio 0.4 (DRAM at S 12 minus DRAM at S 60; R1 measured 3.2 / 0.7 MiB on the
evict-first B1 workloads and 33.9 on B8), and the setting each predictor would pick as best.

Usage: python3 scripts/r2_preregister.py [assets/sweep/r2_predictions_ampere.json]
"""
import json, sys
from collections import defaultdict

MiB = 1 << 20
PRED = ('v3', 'ours_v2', 'ours_v1', 'autoscratch', 'gtsim_l2', 'memexplorer')

def main(path):
    d = json.load(open(path))
    g = defaultdict(dict)
    for r in d['runs']:
        q = r['run']; w = f"{q['model']}/B{q['batch']}/c{q['context']}"
        g[w][(q['window'], q['setaside'], q['hitratio'])] = r
    for w, s in g.items():
        r0 = s[(0, 0, 0)]; b = r0['bytes']; step = (b['weights'] + b['kv_read']) / MiB
        cls = d['load_classes'][w]['classes']
        print(f"{w}: step {step:.1f} MiB (weights {b['weights'] / MiB:.1f}, KV {b['kv_read'] / MiB:.1f}); "
              f"classes weights {''.join(cls[k] for k in ('q', 'k', 'v', 'o', 'gate', 'up', 'down', 'lm_head'))} "
              f"KV {cls['K']}{cls['V']}")
        for f in PRED:
            base = r0['dram_read_bytes'][f] / MiB
            c = (s[(127, 12, 0.4)]['dram_read_bytes'][f] - s[(127, 60, 0.4)]['dram_read_bytes'][f]) / MiB
            best = min(s, key=lambda k: s[k]['dram_read_bytes'][f])
            print(f"   {f:12s} baseline {base:7.1f}   S12-S60 (W127 r.4) {c:+6.1f}   best {best} "
                  f"{s[best]['dram_read_bytes'][f] / MiB:7.1f}")

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'assets/sweep/r2_predictions_ampere.json')
