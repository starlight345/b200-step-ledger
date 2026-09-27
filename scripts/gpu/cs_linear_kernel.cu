// cs_linear_kernel.cu — R3 intervention kernel: y[M, N] = x[M, K] @ w[N, K]^T for decode (M <= 16), bf16 in/out,
// fp32 accumulate. The WEIGHT matrix is read with __ldcs (ld.global.cs = SASS LDG.E.EF, evict-first in L1 and L2), the
// load class cuBLAS gemvx uses at batch 1; x is read normally (it is tiny and reused by every warp).
// One warp per output column n: the warp streams row w[n, :] once in 16-B chunks (8 bf16 per lane per iteration).
// Needs K % 8 == 0 and 16-B aligned rows (true for every projection of the SmolLM models; checked by the caller).
// Build: nvcc -O3 -arch=sm_120 -Xcompiler -fPIC -shared -o cs_linear_kernel.so cs_linear_kernel.cu
// C entry point (called with ctypes from cs_linear.py on PyTorch's current stream): linear_cs_bf16(...)
#include <cuda_bf16.h>
#include <cuda_runtime.h>
#include <stdint.h>

constexpr int MAXM = 16, WARPS = 8;

__global__ void __launch_bounds__(WARPS * 32) linear_cs(const __nv_bfloat16* __restrict__ x, const __nv_bfloat16* w,
                                                         __nv_bfloat16* __restrict__ y, int M, int N, int K) {
    const int lane = threadIdx.x & 31, n = blockIdx.x * WARPS + (threadIdx.x >> 5);
    if (n >= N) return;
    float acc[MAXM];
#pragma unroll
    for (int m = 0; m < MAXM; ++m) acc[m] = 0.f;
    const uint4* wr = reinterpret_cast<const uint4*>(w + (size_t)n * K);
    for (int k8 = lane; k8 < K / 8; k8 += 32) {
        uint4 wv = __ldcs(wr + k8);                                   // evict-first weight load (LDG.E.EF.128)
        const __nv_bfloat162* wp = reinterpret_cast<const __nv_bfloat162*>(&wv);
        float2 wf[4];
#pragma unroll
        for (int j = 0; j < 4; ++j) wf[j] = __bfloat1622float2(wp[j]);
#pragma unroll
        for (int m = 0; m < MAXM; ++m) {
            if (m < M) {
                uint4 xv = reinterpret_cast<const uint4*>(x + (size_t)m * K)[k8];
                const __nv_bfloat162* xp = reinterpret_cast<const __nv_bfloat162*>(&xv);
#pragma unroll
                for (int j = 0; j < 4; ++j) {
                    float2 xf = __bfloat1622float2(xp[j]);
                    acc[m] += xf.x * wf[j].x + xf.y * wf[j].y;
                }
            }
        }
    }
#pragma unroll
    for (int m = 0; m < MAXM; ++m) {
        float v = acc[m];
#pragma unroll
        for (int o = 16; o > 0; o >>= 1) v += __shfl_xor_sync(0xffffffffu, v, o);
        if (lane == 0 && m < M) y[(size_t)m * N + n] = __float2bfloat16(v);
    }
}

extern "C" int linear_cs_bf16(const void* x, const void* w, void* y, int M, int N, int K, void* stream) {
    if (M < 1 || M > MAXM || K % 8) return -1;
    dim3 grid((N + WARPS - 1) / WARPS), block(WARPS * 32);
    linear_cs<<<grid, block, 0, (cudaStream_t)stream>>>((const __nv_bfloat16*)x, (const __nv_bfloat16*)w,
                                                        (__nv_bfloat16*)y, M, N, K);
    return (int)cudaGetLastError();
}
