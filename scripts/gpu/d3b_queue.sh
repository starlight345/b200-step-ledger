#!/bin/bash
# d3b_queue.sh — D3b on dsil-sy in the N1 gap: once the N1 census is done (or N1 stopped), before the N1 counters
# (the N1 predictions are uploaded only after 'd3b exit', so the two never overlap). Gate: every new kernel
# (hints 4, 6, 7) runs to completion (the bulk-copy kernel waits on an mbarrier; a hang is caught by the timeout).
# Then h1_run.py over the grid frozen in d3b_predictions_ampere.json with the D3b build of l2policy_bench.
cd $HOME/l2probe && source venv/bin/activate
export PATH=/usr/local/cuda-12.8/bin:$PATH LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$LD_LIBRARY_PATH
L=d3b_run.log
idle() { ! pgrep -u $USER -f "[r]3_run|[r]2_list|[n]1_run|[l]lm_policy_bench.py|[a]ccel-sim.out|[t]racer_tool|[d]ecode_timeline|[n]sys " > /dev/null &&
         [ -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; }
until grep -qE "n1 census done|n1 exit" n1_run.log 2>/dev/null; do sleep 20; done
while ! idle; do sleep 10; done
echo "$(date +%T) d3b gate" >> $L
for h in 4 6 7; do
  if ! timeout 120 ./l2policy_bench_d3b mode=llm ws=268 layers=32 hint=$h warmup=5 iters=20 >> $L 2>&1; then
    echo "$(date +%T) d3b exit gate-failed hint $h" >> $L; exit 1
  fi
done
echo "$(date +%T) d3b start (predictions sha256 $(sha256sum d3b_predictions_ampere.json | cut -c1-16))" >> $L
L2BENCH=./l2policy_bench_d3b python h1_run.py d3b_predictions_ampere.json d3b_measured_ampere.jsonl >> $L 2>&1
echo "$(date +%T) d3b exit $?" >> $L
