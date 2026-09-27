#!/bin/bash
# r3_queue.sh — R3 on dsil-sy: after R2 exits and no other GPU job of ours runs, check the intervention kernel
# (cs_linear self-test must show LDG.E.EF; the manual decode with the intervention must match HF's logits: min cos
# >= 0.98, argmax agreement >= 0.8 over 3 steps, for one model of each size), then r3_run.py over the grid frozen in
# r3_predictions_ampere.json. Start detached:
#   ssh dsil-sy 'nohup bash ~/l2probe/r3_queue.sh > /dev/null 2>&1 < /dev/null &'
cd $HOME/l2probe && source venv/bin/activate && export HF_HOME=$HOME/l2probe/hf
export PATH=/usr/local/cuda-12.8/bin:$PATH LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$LD_LIBRARY_PATH
until grep -q "r2 exit" r2_run.log 2>/dev/null; do sleep 30; done
# The ECTC thermal session captures a ~5 min nsys decode timeline (python decode_timeline.py under nsys) once the GPU has
# been idle for 2 min after R2; give it that window, then wait until it is gone. Counters must never overlap it.
sleep 240
while pgrep -u $USER -f "[r]2_run|[l]lm_policy_bench.py|[a]ccel-sim.out|[t]racer_tool|[d]ecode_timeline|[n]sys " > /dev/null; do
  sleep 10
done
echo "$(date +%T) r3 selftest" >> r3_run.log
python cs_linear.py >> r3_run.log 2>&1
if ! grep -q "sass LDG.E.EF: [1-9]" r3_run.log; then echo "$(date +%T) r3 exit selftest-failed" >> r3_run.log; exit 1; fi
for mb in "SmolLM-135M 2" "SmolLM-360M 4"; do
  set -- $mb
  python llm_policy_bench.py --model HuggingFaceTB/$1 --batch $2 --context 512 --mode check --weights-cs 2>>r3_run.log \
      | tail -1 > r3_check_$1_B$2.json
  if ! python r3_check.py r3_check_$1_B$2.json >> r3_run.log 2>&1; then
    echo "$(date +%T) r3 exit check-failed $1 B$2" >> r3_run.log; exit 1
  fi
done
echo "$(date +%T) r3 start (predictions sha256 $(sha256sum r3_predictions_ampere.json | cut -c1-16))" >> r3_run.log
python r3_run.py r3_predictions_ampere.json r3_measured_ampere.jsonl >> r3_run.log 2>&1
echo "$(date +%T) r3 exit $?" >> r3_run.log
