#!/usr/bin/env python3
"""R3 intervention: decode projections whose WEIGHT loads are evict-first (ld.global.cs = SASS LDG.E.EF).

At batch 1, cuBLAS decodes with gemvx, which already reads weights with LDG.E.EF; from batch 2 it switches to a
CUTLASS GEMM with normal-priority loads (R2 census), and the set-aside matters again. This module gives batch >= 2
decode the gemvx-style load class and nothing else: y = x W^T with x [M <= 16, K] and W [N, K] (nn.Linear layout),
bf16 in, fp32 accumulate, bf16 out, computed by cs_linear_kernel.cu (weights via __ldcs, one warp per output column),
built with nvcc into cs_linear_kernel.so and called through ctypes on PyTorch's current stream (no Python headers
needed; Triton 3.4 has no '.cs' load modifier). Rows beyond 16 (prefill) fall back to F.linear.

  patch(model)  route every bias-free nn.Linear of the model (q, k, v, o, gate, up, down, LM head) through this kernel
                while enabled() is true (set_enabled); returns the number of modules patched.
Usage (self-test, on a GPU):  python cs_linear.py   (builds the .so if missing, checks error and the SASS)
"""
import ctypes, os, subprocess
import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
SO, CU = os.path.join(HERE, 'cs_linear_kernel.so'), os.path.join(HERE, 'cs_linear_kernel.cu')
_ON = [False]
_LIB = [None]

def set_enabled(v): _ON[0] = bool(v)
def enabled(): return _ON[0]

def build():
    subprocess.check_call(['nvcc', '-O3', '-arch=sm_120', '-Xcompiler', '-fPIC', '-shared', '-o', SO, CU])

def lib():
    if _LIB[0] is None:
        if not os.path.exists(SO) or os.path.getmtime(SO) < os.path.getmtime(CU): build()
        L = ctypes.CDLL(SO)
        L.linear_cs_bf16.argtypes = [ctypes.c_void_p] * 3 + [ctypes.c_int] * 3 + [ctypes.c_void_p]
        L.linear_cs_bf16.restype = ctypes.c_int
        _LIB[0] = L
    return _LIB[0]

def linear_cs(x, w):
    shape = x.shape
    K = shape[-1]; N = w.shape[0]
    x2 = x.reshape(-1, K)
    M = x2.shape[0]
    if M > 16 or K % 8 or x.dtype != torch.bfloat16 or w.dtype != torch.bfloat16:
        return F.linear(x, w)
    x2 = x2.contiguous(); w = w.contiguous()
    assert x2.data_ptr() % 16 == 0 and w.data_ptr() % 16 == 0
    y = torch.empty((M, N), dtype=torch.bfloat16, device=x.device)
    rc = lib().linear_cs_bf16(x2.data_ptr(), w.data_ptr(), y.data_ptr(), M, N, K, torch.cuda.current_stream().cuda_stream)
    if rc: raise RuntimeError(f'linear_cs_bf16 returned {rc}')
    return y.reshape(*shape[:-1], N)

def patch(model):
    n = 0
    for mod in model.modules():
        if isinstance(mod, torch.nn.Linear) and mod.bias is None:
            orig = mod.forward
            mod.forward = (lambda x, _m=mod, _o=orig: linear_cs(x, _m.weight) if _ON[0] else _o(x))
            n += 1
    return n

if __name__ == '__main__':
    torch.manual_seed(0)
    worst = 0.0
    for M in (1, 2, 4, 8):
        for N, K in ((576, 576), (192, 576), (1536, 576), (576, 1536), (960, 960), (2560, 960), (960, 2560), (49152, 576)):
            x = torch.randn(M, 1, K, device='cuda', dtype=torch.bfloat16)
            w = torch.randn(N, K, device='cuda', dtype=torch.bfloat16) / K ** 0.5
            ref = F.linear(x.float(), w.float())
            got = linear_cs(x, w).float()
            worst = max(worst, ((got - ref).abs().max() / ref.abs().max()).item())
    torch.cuda.synchronize()
    print(f'max relative error vs fp32 reference over all shapes: {worst:.4f}')
    sass = subprocess.run(['cuobjdump', '-sass', SO], capture_output=True, text=True).stdout
    print('sass LDG.E.EF:', sass.count('LDG.E.EF'), ' sass LDG (all):', sass.count('LDG'))
