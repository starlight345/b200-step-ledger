#!/bin/bash
# Static load-hint census, second pass: the current serving stacks (CPU only, nice'd), after lhc_all.sh.
#   vLLM 0.28.0 + cuBLAS 13.1.1.3 (~/venv-llm) and SGLang 0.5.17 sgl_kernel 0.4.5 (~/venv-sglang).
# CUDA 13 cubins are disassembled with the cu13 nvdisasm (cuobjdump 12.8 calls nvdisasm from PATH).
V=$(ls -d $HOME/venv-llm/lib/python3*/site-packages); G=$(ls -d $HOME/venv-sglang/lib/python3*/site-packages)
export PATH=$V/nvidia/cu13/bin:/usr/local/cuda-12.8/bin:$PATH
O=$HOME/l2probe/lhc_new; mkdir -p $O; cd $HOME/l2probe
until grep -q "lhc exit" lhc/progress.log 2>/dev/null; do sleep 30; done
A=sm_80,sm_90,sm_90a,sm_100,sm_100a,sm_120,sm_120a
for f in $V/vllm/_flashmla_C.abi3.so $V/vllm/_moe_C_stable_libtorch.abi3.so $V/vllm/_C_stable_libtorch.abi3.so \
         $V/vllm/vllm_flash_attn/_vllm_fa2_C.abi3.so $V/vllm/vllm_flash_attn/_vllm_fa3_C.abi3.so $V/nvidia/cu13/lib/libcublas.so.13 \
         $G/sgl_kernel/sm90/common_ops.abi3.so $G/sgl_kernel/sm100/common_ops.abi3.so $G/sgl_kernel/flash_ops.abi3.so \
         $V/nvidia/cu13/lib/libcublasLt.so.13; do
  n=$(echo $f | sed -E "s#.*/(venv-[a-z]+)/.*site-packages/#\1/#; s#/#__#g"); t0=$(date +%s)
  nice -n 19 python3 load_hint_census.py $O/$n.jsonl $A $f > $O/$n.summary 2>&1
  echo "$(date +%T) $n $(( $(date +%s) - t0 ))s" >> $O/progress.log
done
echo "$(date +%T) lhc_new exit" >> $O/progress.log
