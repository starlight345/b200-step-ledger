#!/bin/bash
# r2_fetch.sh MODEL BATCH CONTEXT ... — copy an R2 class-check result from dsil-sy into assets/sweep/r2_census/
# and derive classes.json locally (r2_classes.py needs the HF configs, which live on this machine).
cd "$(dirname "$0")/../.."
for w in "$@"; do
  set -- $w; n=r2_$1_B$2_c$3; d=assets/sweep/r2_census/$n; mkdir -p $d
  for f in cmd.txt meta.json kernels.json census.jsonl; do scp -q dsil-sy:l2probe/asim/list/$n/$f $d/ || exit 1; done
  python3 scripts/prior/r2_classes.py $d $1 $2 $3 > $d/classes.json
  python3 -c "import json; d = json.load(open('$d/classes.json')); print(d['workload'], ''.join(v['class'] for v in d['operands'].values()), 'unmatched', d['unmatched'])"
done
