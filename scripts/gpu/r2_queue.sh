#!/bin/bash
# r2_queue.sh — R2 measurement on dsil-sy: wait until no other GPU job of ours runs (the SASS listing queue,
# Accel-Sim, another bench), then r2_run.py over the grid frozen in r2_predictions_ampere.json.
# Start detached, without a preceding `cd ... &&` (an ssh chain ending in `&` keeps the session open):
#   ssh dsil-sy 'nohup bash ~/l2probe/r2_queue.sh > /dev/null 2>&1 < /dev/null &'
cd $HOME/l2probe && source venv/bin/activate && export HF_HOME=$HOME/l2probe/hf
while pgrep -u $USER -f "[r]2_list|[l]lm_policy_bench.py|[a]ccel-sim.out|[t]racer_tool" > /dev/null; do sleep 10; done
echo "$(date +%T) r2 start (predictions sha256 $(sha256sum r2_predictions_ampere.json | cut -c1-16))" >> r2_run.log
python r2_run.py r2_predictions_ampere.json r2_measured_ampere.jsonl >> r2_run.log 2>&1
echo "$(date +%T) r2 exit $?" >> r2_run.log
