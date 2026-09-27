#!/bin/bash
# n1_queue.sh — N1 (negative control, SmolLM2-1.7B, WS ~ 35x L2) on dsil-sy, after R3. Two stages:
#   1. once R3 has exited and the GPU has no compute process: the manual decode against HF's logits (the engine has
#      not run this model before; same gate as R3: min cos >= 0.98, argmax agreement >= 0.8), then the load-class
#      census for batch 1 and 4 at context 512 (r2_list.sh, NVBit; no counters);
#   2. waits for n1_predictions_ampere.json — frozen on the laptop from the census (r2_fetch.sh -> n1_predict.py)
#      and uploaded as .part then renamed, so a partial file is never read — then n1_run.py (ncu counters, timing).
# Start detached:  ssh dsil-sy 'nohup bash ~/l2probe/n1_queue.sh > /dev/null 2>&1 < /dev/null &'
# Other GPU users: the counters are device-wide; wait for 'n1 exit' in ~/l2probe/n1_run.log.
cd $HOME/l2probe && source venv/bin/activate && export HF_HOME=$HOME/l2probe/hf
export PATH=/usr/local/cuda-12.8/bin:$PATH LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$LD_LIBRARY_PATH
L=n1_run.log
idle() { ! pgrep -u $USER -f "[r]3_run|[l]lm_policy_bench.py|[a]ccel-sim.out|[t]racer_tool|[d]ecode_timeline|[n]sys " > /dev/null &&
         [ -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; }
wait_idle() { while ! idle; do sleep 10; done; sleep 60; while ! idle; do sleep 10; done; }
until grep -q "r3 exit" r3_run.log 2>/dev/null; do sleep 30; done
wait_idle
echo "$(date +%T) n1 check" >> $L
python llm_policy_bench.py --model HuggingFaceTB/SmolLM2-1.7B --batch 1 --context 512 --mode check 2>>$L | tail -1 > n1_check.json
if ! python r3_check.py n1_check.json >> $L 2>&1; then echo "$(date +%T) n1 exit check-failed" >> $L; exit 1; fi
for b in 1 4; do
  echo "$(date +%T) n1 census B$b" >> $L
  if ! bash r2_list.sh SmolLM2-1.7B $b 512 >> $L 2>&1; then echo "$(date +%T) n1 exit census-failed" >> $L; exit 1; fi
done
echo "$(date +%T) n1 census done; waiting for n1_predictions_ampere.json" >> $L
until [ -f n1_predictions_ampere.json ]; do sleep 20; done
wait_idle
echo "$(date +%T) n1 start (predictions sha256 $(sha256sum n1_predictions_ampere.json | cut -c1-16))" >> $L
python n1_run.py n1_predictions_ampere.json n1_measured_ampere.jsonl >> $L 2>&1
echo "$(date +%T) n1 exit $?" >> $L
