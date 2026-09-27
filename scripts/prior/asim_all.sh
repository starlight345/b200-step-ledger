#!/bin/bash
# asim_all.sh — trace the held-out workloads (H1c: 6 synthetic; R1: 3 real-LLM decode) on the GPU, one at a time,
# and simulate each in the background as soon as its trace is ready. Run on dsil-sy after the GPU is idle
# (tracing runs kernels: it must not overlap a counter measurement).
# Every workload is traced for 2 steps: 1 warm-up + 1 predicted (LRU-type caches reach steady state after one
# pass of a cyclic stream). The simulator runs at ~0.04 MiB of traffic per second, so this is the affordable set.
#   synthetic: l2policy_bench_nopol at the baseline setting (warmup=1 iters=1)
#   R1       : llm_policy_bench.py --mode profile --prof 2 --no-policy-calls (baseline)
# Usage: [TRACE_ONLY=1] bash asim_all.sh [MAX_PARALLEL_SIMS]      (log: ~/l2probe/asim/all.log)
H=$HOME/l2probe; RUN=$H/asim_run.sh; P=${1:-8}
mkdir -p $H/asim
cd $H
sim_bg() {   # keep at most P simulations running
  while [ $(pgrep -u $USER -f accel-sim.out | wc -l) -ge $P ]; do sleep 20; done
  (nice -n 10 bash $RUN sim $1 > $H/asim/runs/$1.sim.out 2>&1; echo "$(date +%T) sim done $1" >> $H/asim/all.log) &
}
trace() {    # name, then the command
  n=$1; shift
  echo "$(date +%T) trace $n" >> $H/asim/all.log
  if bash $RUN trace $n -- "$@" >> $H/asim/all.log 2>&1; then
    case $n in                                         # R1 sims start by hand after the opcode census
      r1_*) ;;                                         # (asim_opcodes.py) of their traces
      *) [ -n "$TRACE_ONLY" ] || sim_bg $n ;;          # TRACE_ONLY=1: trace everything now, simulate later
    esac
  else echo "$(date +%T) TRACE FAILED $n" >> $H/asim/all.log; fi
}
B=$H/l2policy_bench_nopol          # built with -DNO_POLICY_CALLS (NVBit 1.8 fails in cudaCtxResetPersistingL2Cache)
export HF_HOME=$H/hf
r1() { trace r1_$1_B$2 env ACTIVE_FROM_START=0 $H/venv/bin/python $H/llm_policy_bench.py --model HuggingFaceTB/$1 \
         --batch $2 --context 512 --mode profile --warmup 10 --prof 2 --no-policy-calls; }
llm() { trace llm_$1 $B mode=llm ws=$1 layers=32 warmup=1 iters=1; }
clean() { trace clean_$1_$2 $B mode=clean hot=$1 chunk=$2 pool=2048 warmup=1 iters=1; }
# longest simulations first so they finish together
r1 SmolLM-360M 1; r1 SmolLM-135M 8; r1 SmolLM-135M 1
llm 288; clean 112 64; clean 80 64; llm 144; clean 64 64; llm 72
wait
echo "$(date +%T) ALL DONE" >> $H/asim/all.log
