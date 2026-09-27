#!/bin/bash
# asim_r1.sh MODEL BATCH — trace the last two decode steps of the R1 harness for Accel-Sim.
# The NVBit 1.8 tracer does not see cudaProfilerStart/cuProfilerStart from PyTorch (tested: runtime and driver
# calls both leave the region inactive), so the two steps are selected by kernel id instead:
#   1. listing pass (DYNAMIC_KERNEL_RANGE beyond the end): kernel names only, nothing traced;
#   2. K = kernels per decode step = the period of the name sequence at the tail (the harness ends with
#      10 warm-up + 2 profiled identical steps); the last 2K kernels are the two profiled steps;
#   3. tracing pass with DYNAMIC_KERNEL_RANGE = those ids, through asim_run.sh (then post-processing).
# Same binary, arguments and allocation order in both passes, so kernel ids line up.
set -e
H=$HOME/l2probe; M=$1; B=$2; N=r1_${M}_B${B}
T=$H/thirdparty/accel-sim-framework/util/tracer_nvbit/tracer_tool
export PATH=/usr/local/cuda-12.8/bin:$PATH LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$LD_LIBRARY_PATH HF_HOME=$H/hf
CMD="$H/venv/bin/python $H/llm_policy_bench.py --model HuggingFaceTB/$M --batch $B --context 512 --mode profile --warmup 10 --prof 2 --no-policy-calls"
L=$H/asim/list/$N; rm -rf $L; mkdir -p $L; cd $L
DYNAMIC_KERNEL_RANGE=100000000 CUDA_INJECTION64_PATH=$T/tracer_tool.so $CMD > list.out 2>&1
RANGE=$(python3 - <<'EOF'
import csv, glob
names = [r[1].strip() for r in list(csv.reader(open(glob.glob('traces/stats_ctx_*')[0])))[1:]]
N = len(names)
K = next(k for k in range(10, N // 4) if names[-k:] == names[-2 * k:-k] == names[-3 * k:-2 * k])
print(f'{N - 2 * K + 1}-{N}')
EOF
)
echo "$N kernels $RANGE" | tee range.txt
DYNAMIC_KERNEL_RANGE="$RANGE" bash $H/asim_run.sh trace $N -- $CMD
