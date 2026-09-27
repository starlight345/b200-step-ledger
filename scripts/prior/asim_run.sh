#!/bin/bash
# asim_run.sh — Accel-Sim 2.0 (GPGPU-Sim 4.x) as a prior-work predictor of DRAM bytes per step.
#
#   asim_run.sh trace NAME -- CMD ARGS...   trace CMD on the real GPU with the NVBit tracer, then post-process
#   asim_run.sh sim   NAME                  simulate NAME's traces with the SM120_RTXPRO5000 config
#
# Runs on dsil-sy. Tool: ~/l2probe/thirdparty/accel-sim-framework (dev d930ad6) with ONE patch: traces whose
# binary version is >= 100 (Blackwell) are decoded with the Hopper opcode table (issue #488: the release rejects
# sm_120). Config: ~/l2probe/asim_cfg/SM120_RTXPRO5000 = the SM86_RTX3070 template with the device's SM count,
# clocks, L2 capacity and DRAM channels; nothing is fitted to measurements.
# The policy knobs (set-aside, access-policy window) cannot be expressed in Accel-Sim, so each workload is traced
# and simulated once, at the baseline setting; its prediction is the same for every policy setting.
set -e
A=$HOME/l2probe/thirdparty/accel-sim-framework
T=$A/util/tracer_nvbit/tracer_tool
CFG=$HOME/l2probe/asim_cfg/SM120_RTXPRO5000
R=$HOME/l2probe/asim/runs
export PATH=/usr/local/cuda-12.8/bin:$PATH LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$LD_LIBRARY_PATH
what=$1; name=$2; shift 2
D=$R/$name
case $what in
  trace)
    [ "$1" = "--" ] && shift
    rm -rf $D; mkdir -p $D; cd $D
    echo "$@" > cmd.txt
    t0=$(date +%s)
    USER_DEFINED_FOLDERS=1 TRACES_FOLDER=$D CUDA_INJECTION64_PATH=$T/tracer_tool.so "$@" > app.out 2> app.err
    t1=$(date +%s)
    $T/traces-processing/post-traces-processing $D/traces -j 8 > post.log 2>&1
    t2=$(date +%s)
    echo "{\"trace_s\": $((t1 - t0)), \"post_s\": $((t2 - t1)), \"kernels\": $(ls $D/traces | grep -c -E '^kernel-.*\.trace'), \"bytes\": $(du -sb $D/traces | cut -f1)}" > trace_meta.json
    cat trace_meta.json ;;
  sim)
    mkdir -p $D/sim; cd $D/sim
    cp $CFG/* .
    sha256sum gpgpusim.config trace.config > config.sha256
    t0=$(date +%s)
    ${ASIM_BIN:-$A/gpu-simulator/bin/release/accel-sim.out} -trace $D/traces/kernelslist.g \
        -config ./gpgpusim.config -config ./trace.config > sim.log 2>&1 || echo "EXIT $?" >> sim.log
    t1=$(date +%s)
    echo "{\"sim_s\": $((t1 - t0))}" > sim_meta.json
    cat sim_meta.json ;;
  *) echo "usage: $0 trace|sim NAME [-- CMD...]"; exit 2 ;;
esac
