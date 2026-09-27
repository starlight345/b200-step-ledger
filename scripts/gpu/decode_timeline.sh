#!/bin/bash
# Waits until the GPU is idle (no other measurement queued or running, no compute process for
# 2 minutes), then captures the decode timeline in graph and eager mode (decode_timeline.py) and
# exports each kernel's start and duration. ~5 minutes of GPU time. Run from ~/ectc_thermal/timeline.
cd $HOME/ectc_thermal/timeline && source $HOME/l2probe/venv/bin/activate
NSYS=/usr/local/cuda-12.8/bin/nsys
busy() { pgrep -u $USER -f "[r]2_run.py|[r]2_queue|[l]lm_policy_bench.py|[r]2_list|[a]ccel-sim.out|[t]racer_tool" >/dev/null ||
         [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; }
idle=0
while [ $idle -lt 4 ]; do if busy; then idle=0; else idle=$((idle+1)); fi; sleep 30; done
echo "$(date +%T) gpu idle, start" >> timeline.log
for m in graph eager; do
  $NSYS profile -f true -t cuda,nvtx --cuda-graph-trace=node --capture-range=cudaProfilerApi \
      --capture-range-end=stop -o tl_$m python decode_timeline.py --mode $m >> timeline.log 2>&1
  $NSYS stats -f csv -r cuda_gpu_trace -o tl_$m tl_$m.nsys-rep >> timeline.log 2>&1
  echo "$(date +%T) $m exit $?" >> timeline.log
done
echo DONE >> timeline.log
