#!/bin/bash
# r2_list.sh MODEL BATCH CONTEXT — R2 load-class check, step 1 of 2 (runs on dsil-sy, needs the GPU).
#
#   1. listing pass: the NVBit tracer with DYNAMIC_KERNEL_RANGE beyond the end records every kernel's name and
#      id but traces nothing (a few minutes);
#   2. r2_kernels.py finds the last decode step, its layer period and the kernel ids that cover every distinct
#      kernel of a step (prefix + first layer + tail after the last layer);
#   3. those ids alone are traced (asim_run.sh trace, DYNAMIC_KERNEL_RANGE = id list) and r2_census.py counts,
#      per kernel, the 32-B sectors each load variant touches (LDG.E.EF.* = evict-first, the rest normal).
# The decode command is the R2 measurement's (llm_policy_bench.py --mode profile) with --no-policy-calls, because
# NVBit 1.8 fails on cudaCtxResetPersistingL2Cache; kernel ids repeat run to run (checked on R1: the listing gave
# the same range as the manual count), so the ids from pass 1 select the same kernels in pass 3.
set -e
H=$HOME/l2probe; M=$1; B=$2; CTX=$3; N=r2_${M}_B${B}_c${CTX}
T=$H/thirdparty/accel-sim-framework/util/tracer_nvbit/tracer_tool
export PATH=/usr/local/cuda-12.8/bin:$PATH LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$LD_LIBRARY_PATH HF_HOME=$H/hf
CMD="$H/venv/bin/python $H/llm_policy_bench.py --model HuggingFaceTB/$M --batch $B --context $CTX --mode profile --warmup 10 --prof 2 --no-policy-calls"
L=$H/asim/list/$N; rm -rf $L; mkdir -p $L; cd $L
echo "$CMD" > cmd.txt
t0=$(date +%s)
DYNAMIC_KERNEL_RANGE=100000000 CUDA_INJECTION64_PATH=$T/tracer_tool.so $CMD > list.out 2>&1
t1=$(date +%s)
python3 $H/r2_kernels.py $L/traces > kernels.json
IDS=$(python3 -c "import json; print(' '.join(map(str, json.load(open('kernels.json'))['picks'])))")
DYNAMIC_KERNEL_RANGE="$IDS" bash $H/asim_run.sh trace $N -- $CMD > trace.out 2>&1
t2=$(date +%s)
python3 $H/r2_census.py $H/asim/runs/$N > census.jsonl
echo "{\"list_s\": $((t1 - t0)), \"trace_s\": $((t2 - t1)), \"picks\": $(echo $IDS | wc -w)}" > meta.json
echo "r2 list done $N $(cat meta.json)"
