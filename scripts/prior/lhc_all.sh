#!/bin/bash
# Static load-hint census over the vLLM 0.10.2 / cuBLAS 12.8.4.1 kernel libraries (CPU only, nice'd).
export PATH=/usr/local/cuda-12.8/bin:$PATH
SP=$HOME/venv-vllm128/lib/python3.12/site-packages
O=$HOME/l2probe/lhc; mkdir -p $O; cd $HOME/l2probe
A=sm_80,sm_90,sm_90a,sm_100,sm_100a,sm_120,sm_120a
for f in $SP/vllm/_flashmla_C.abi3.so $SP/vllm/_moe_C.abi3.so $SP/vllm/_C.abi3.so $SP/nvidia/cublas/lib/libcublas.so.12 \
         $SP/vllm/vllm_flash_attn/_vllm_fa2_C.abi3.so $SP/vllm/vllm_flash_attn/_vllm_fa3_C.abi3.so $SP/nvidia/cublas/lib/libcublasLt.so.12; do
  n=$(basename $f .so); t0=$(date +%s)
  nice -n 19 python3 load_hint_census.py $O/$n.jsonl $A $f > $O/$n.summary 2>&1
  echo "$(date +%T) $n $(( $(date +%s) - t0 ))s" >> $O/progress.log
done
echo "$(date +%T) lhc exit" >> $O/progress.log
