#!/bin/bash
# c1_setaside_order.sh — diagnostic D1 (file name keeps the older c1 label): does lowering the persisting set-aside INSIDE one process take effect?
#
# R1 changed the set-aside setting by setting inside one process (baseline, set-aside 60 MiB control, then
# window 127 MiB with S = 12, 24, ... MiB), and its measured DRAM hardly depends on S; the synthetic H1c runs used
# a fresh process per setting and depend on S strongly. Same model and policy setting, three ways:
#   A  fresh process:               [W127 S12 r0.4]
#   B  after the S = 60 control:    [baseline, S60 only, W127 S12 r0.4]      (R1's order; last range is the test)
#   C  fresh process:               [W127 S60 r0.4]
#   D  fresh process, S raised:     [W127 S12 r0.4, W127 S60 r0.4]           (does raising take effect?)
# If A != B and B ~ C, a lower set-aside does not take effect in-process and R1's window settings ran at S = 60.
# Run on dsil-sy from ~/l2probe after the GPU is idle.  Output: c1_setaside_order.jsonl
cd ~/l2probe && source venv/bin/activate && export HF_HOME=~/l2probe/hf
NCU=/usr/local/cuda-12.8/bin/ncu
M='dram__bytes_read.sum,lts__t_sectors_lookup_hit.sum,lts__t_sectors_lookup_miss.sum'
W='{"window":127,"setaside":'; E=',"hitratio":0.4}'
declare -A CASE=(
  [A]="[${W}12${E}]"
  [B]="[{\"window\":0,\"setaside\":0,\"hitratio\":0},{\"window\":0,\"setaside\":60,\"hitratio\":0},${W}12${E}]"
  [C]="[${W}60${E}]"
  [D]="[${W}12${E},${W}60${E}]"
)
: > c1_setaside_order.jsonl
for c in A B C D; do
  echo "${CASE[$c]}" > c1_$c.json
  $NCU --metrics $M --cache-control none --replay-mode app-range --csv --print-units base \
      python llm_policy_bench.py --model HuggingFaceTB/SmolLM-135M --batch 1 --context 512 \
      --mode sweep-profile --settings c1_$c.json --warmup 20 --prof 3 > c1_$c.out 2>&1
  python - "$c" <<'EOF'
import csv, io, json, sys
from collections import defaultdict
c = sys.argv[1]; out = open(f'c1_{c}.out').read()
rows = [l for l in out.splitlines() if l.startswith('"')]
tot = defaultdict(lambda: defaultdict(float))
for r in csv.DictReader(io.StringIO('\n'.join(rows))):
    v = (r.get('Metric Value') or '').replace(',', '')
    if v: tot[int(r['ID'])][r['Metric Name']] += float(v)
sets = [json.loads(l[8:]) for l in out.splitlines() if l.startswith('SETTING ')]
res = [dict(case=c, i=i, setting=s['setting'], setaside_got=s['setaside_got'],
            dram_read_mib_per_step=tot[k]['dram__bytes_read.sum'] / 3 / 2**20)
       for i, (k, s) in enumerate(zip(sorted(tot), sets))]
with open('c1_setaside_order.jsonl', 'a') as f:
    for r in res: f.write(json.dumps(r) + '\n'); print(json.dumps(r))
EOF
done
