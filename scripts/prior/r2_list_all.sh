#!/bin/bash
# r2_list_all.sh — run r2_list.sh for every R2 candidate workload, one after another (GPU, ~10 min each).
cd $HOME/l2probe
for w in "SmolLM-135M 2 512" "SmolLM-135M 4 512" "SmolLM-135M 1 1536" "SmolLM-360M 4 512" "SmolLM-360M 8 512"; do
  set -- $w
  echo "$(date +%T) start $w"
  bash r2_list.sh $1 $2 $3 || echo "$(date +%T) FAILED $w"
done
echo "$(date +%T) r2 list all done"
