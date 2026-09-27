#!/usr/bin/env python3
"""Gate for R3: the manual decode with the intervention (--weights-cs) against HF's own forward, 3 decode steps.
Passes if the minimum logits cosine >= 0.98 and the mean argmax agreement >= 0.8.
Usage: python r3_check.py r3_check_<model>_B<batch>.json   (the JSON line printed by llm_policy_bench --mode check)"""
import json, sys

c = json.load(open(sys.argv[1]))['check']
ok = min(x['cos'] for x in c) >= 0.98 and sum(x['argmax_agree'] for x in c) / len(c) >= 0.8
print('check', sys.argv[1], [(round(x['cos'], 4), x['argmax_agree']) for x in c], 'ok' if ok else 'FAIL')
sys.exit(0 if ok else 1)
