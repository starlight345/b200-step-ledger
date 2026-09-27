// l2policy_bench.cu — H1/H2: does the CUDA L2 persistence policy change traffic the way our model says?
//
// Two synthetic workloads, repeated as "steps" (M2):
//   clean : each step reads the whole HOT buffer, then the next CHUNK of a large cold POOL.
//           Hot reuse distance = hot + chunk; the pool never repeats within L2 lifetime.
//           (NVIDIA Best Practices style: persistent region + streaming region.)
//   llm   : each step reads WS bytes as LAYERS equal kernels in a fixed order, like decode reading
//           every weight once per token. Everything recurs with reuse distance = WS.
//
// The ONLY things that change between runs of the same workload are the policy knobs:
//   setaside   cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize, bytes)
//   window     cudaAccessPolicyWindow over the first `window` bytes of HOT (clean) or of the weights (llm)
//   hitratio   fraction of the window given hitProp=Persisting; the rest get missProp=Streaming
// Same kernels, same launch shapes, same addresses, same bytes requested -> any time change is the
// policy's effect on where the bytes come from (the fixed-compute causal experiment of H2).
//
// Build: nvcc -O3 -arch=native -o l2policy_bench l2policy_bench.cu
//        (Accel-Sim tracing, baseline only: add -DNO_POLICY_CALLS -o l2policy_bench_nopol)
// Run  : ./l2policy_bench mode=llm ws=192 layers=32 setaside=48 window=128 hitratio=0.5
// Output: one JSON line.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include <cuda_runtime.h>

#define CK(x) do { cudaError_t e_ = (x); if (e_ != cudaSuccess) { \
    fprintf(stderr, "%s:%d %s\n", __FILE__, __LINE__, cudaGetErrorString(e_)); exit(1); } } while (0)

// Plain global loads (no __restrict__/const, so no special cache path), summed so they are not
// optimised away; the single conditional store never fires.
__global__ void rd(float4* p, size_t n4, int reps, float* out) {
    float acc = 0.f;
    for (int r = 0; r < reps; ++r)
        for (size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x; i < n4; i += (size_t)gridDim.x * blockDim.x) {
            float4 v = p[i]; acc += v.x + v.y + v.z + v.w;
        }
    if (acc == 1234.5678f) out[0] = acc;
}

// hint=1/2 (rd_hint): the same loads carrying an L2 eviction-priority cache policy (createpolicy + ld.L2::cache_hint),
// evict_first / evict_last on every load. Tests whether per-instruction hints (as library kernels may carry)
// change how the access-policy window and set-aside act. hint=0 (default) is the plain kernel above.
__device__ __forceinline__ float4 ld_pol(const float4* a, unsigned long long pol) {
    float4 v;
    asm volatile("ld.global.L2::cache_hint.v4.f32 {%0,%1,%2,%3}, [%4], %5;"
                 : "=f"(v.x), "=f"(v.y), "=f"(v.z), "=f"(v.w) : "l"(a), "l"(pol));
    return v;
}
__global__ void rd_hint(float4* p, size_t n4, int reps, float* out, int hint) {
    unsigned long long pol;
    if (hint == 1) asm volatile("createpolicy.fractional.L2::evict_first.b64 %0, 1.0;" : "=l"(pol));
    else           asm volatile("createpolicy.fractional.L2::evict_last.b64 %0, 1.0;" : "=l"(pol));
    float acc = 0.f;
    for (int r = 0; r < reps; ++r)
        for (size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x; i < n4; i += (size_t)gridDim.x * blockDim.x) {
            float4 v = ld_pol(p + i, pol); acc += v.x + v.y + v.z + v.w;
        }
    if (acc == 1234.5678f) out[0] = acc;
}

// hint=3: ld.global.cs (SASS LDG.E.EF, evict-first in L1 and L2) — how cuBLAS's gemvx kernel reads the weight
// matrix on sm_120 (cuobjdump of libcublasLt: LDG.E.EF.U16), i.e. what the real-LLM decode (R1) actually issues.
__global__ void rd_cs(float4* p, size_t n4, int reps, float* out) {
    float acc = 0.f;
    for (int r = 0; r < reps; ++r)
        for (size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x; i < n4; i += (size_t)gridDim.x * blockDim.x) {
            float4 v = __ldcs(p + i); acc += v.x + v.y + v.z + v.w;
        }
    if (acc == 1234.5678f) out[0] = acc;
}

// D3b (hints 4-7): is it the priority a load carries, or who built its descriptor, that decides whether the access-policy
// window applies? D3 found both createpolicy priorities (evict_first / evict_last) void the window, and guessed that the
// window reaches a kernel only through the driver's default descriptor (constant bank, c[0x0][0x358] on sm_120).
//   hint=4/5: createpolicy L2::evict_normal / L2::evict_unchanged on every LDG (a kernel-built descriptor that asks
//             for nothing special);
//   hint=6/7: the TMA bulk-copy path (cp.async.bulk global -> shared, SASS UBLKCP) that CUTLASS 3.x and FlashMLA
//             kernels load through, without (6) and with (7) an L2::cache_hint evict_normal policy.
__global__ void rd_hint2(float4* p, size_t n4, int reps, float* out, int hint) {
    unsigned long long pol;
    if (hint == 4) asm volatile("createpolicy.fractional.L2::evict_normal.b64 %0, 1.0;" : "=l"(pol));
    else           asm volatile("createpolicy.fractional.L2::evict_unchanged.b64 %0, 1.0;" : "=l"(pol));
    float acc = 0.f;
    for (int r = 0; r < reps; ++r)
        for (size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x; i < n4; i += (size_t)gridDim.x * blockDim.x) {
            float4 v = ld_pol(p + i, pol); acc += v.x + v.y + v.z + v.w;
        }
    if (acc == 1234.5678f) out[0] = acc;
}

constexpr unsigned BULK = 16384;              // bytes per bulk copy (one CTA buffer; 4 CTAs per SM fit in shared memory)
__global__ void rd_bulk(float4* p, size_t n4, int reps, float* out, int hint) {
    __shared__ alignas(128) float4 buf[BULK / sizeof(float4)];
    __shared__ alignas(8) unsigned long long mbar;
    unsigned b_s = (unsigned)__cvta_generic_to_shared(buf), m_s = (unsigned)__cvta_generic_to_shared(&mbar);
    unsigned long long pol;
    asm volatile("createpolicy.fractional.L2::evict_normal.b64 %0, 1.0;" : "=l"(pol));
    if (threadIdx.x == 0) {
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;" :: "r"(m_s));
        asm volatile("fence.mbarrier_init.release.cluster;" ::: "memory");
    }
    __syncthreads();
    size_t nb = n4 * sizeof(float4);
    unsigned phase = 0;
    float acc = 0.f;
    for (int r = 0; r < reps; ++r)
        for (size_t off = (size_t)blockIdx.x * BULK; off < nb; off += (size_t)gridDim.x * BULK) {
            unsigned len = (unsigned)(nb - off < BULK ? nb - off : BULK);          // multiple of 256 B (per_b aligned)
            if (threadIdx.x == 0) {
                const char* src = (const char*)p + off;
                asm volatile("mbarrier.arrive.expect_tx.shared::cta.b64 _, [%0], %1;" :: "r"(m_s), "r"(len) : "memory");
                if (hint == 7)
                    asm volatile("cp.async.bulk.shared::cluster.global.mbarrier::complete_tx::bytes.L2::cache_hint"
                                 " [%0], [%1], %2, [%3], %4;" :: "r"(b_s), "l"(src), "r"(len), "r"(m_s), "l"(pol) : "memory");
                else
                    asm volatile("cp.async.bulk.shared::cluster.global.mbarrier::complete_tx::bytes [%0], [%1], %2, [%3];"
                                 :: "r"(b_s), "l"(src), "r"(len), "r"(m_s) : "memory");
            }
            asm volatile("{\n .reg .pred P1;\n WAIT_%=:\n mbarrier.try_wait.parity.shared::cta.b64 P1, [%0], %1;\n"
                         " @!P1 bra WAIT_%=;\n}" :: "r"(m_s), "r"(phase) : "memory");
            phase ^= 1;
            for (unsigned i = threadIdx.x; i < len / sizeof(float4); i += blockDim.x) {
                float4 v = buf[i]; acc += v.x + v.y + v.z + v.w;
            }
            __syncthreads();                                                        // buffer free before the next copy
        }
    if (acc == 1234.5678f) out[0] = acc;
}

static double arg(int argc, char** argv, const char* k, double dflt) {
    size_t n = strlen(k);
    for (int i = 1; i < argc; ++i) if (!strncmp(argv[i], k, n) && argv[i][n] == '=') return atof(argv[i] + n + 1);
    return dflt;
}
static std::string sarg(int argc, char** argv, const char* k, const char* dflt) {
    size_t n = strlen(k);
    for (int i = 1; i < argc; ++i) if (!strncmp(argv[i], k, n) && argv[i][n] == '=') return std::string(argv[i] + n + 1);
    return dflt;
}

int main(int argc, char** argv) {
    const size_t MiB = 1u << 20;
    std::string mode = sarg(argc, argv, "mode", "llm");
    double ws = arg(argc, argv, "ws", 192), hot = arg(argc, argv, "hot", 96), chunk = arg(argc, argv, "chunk", 96);
    double pool = arg(argc, argv, "pool", 2048), win = arg(argc, argv, "window", 0), sa = arg(argc, argv, "setaside", 0);
    double hr = arg(argc, argv, "hitratio", 0);
    int layers = (int)arg(argc, argv, "layers", 32), warm = (int)arg(argc, argv, "warmup", 30);
    int iters = (int)arg(argc, argv, "iters", 200), reps = (int)arg(argc, argv, "reps", 1);
    int hint = (int)arg(argc, argv, "hint", 0);

    cudaDeviceProp pr; CK(cudaGetDeviceProperties(&pr, 0));
    int grid = pr.multiProcessorCount * 4, block = 256;
    cudaStream_t s; CK(cudaStreamCreate(&s));
    float* out; CK(cudaMalloc(&out, sizeof(float)));

    bool clean = (mode == "clean");
    size_t hot_b = (size_t)(hot * MiB), chunk_b = (size_t)(chunk * MiB), pool_b = (size_t)(pool * MiB);
    size_t ws_b = (size_t)(ws * MiB), per_b = (ws_b / layers) & ~(size_t)255;   // 256-B aligned per kernel (float4 loads)
    char *A = nullptr, *P = nullptr;
    if (clean) { CK(cudaMalloc(&A, hot_b)); CK(cudaMalloc(&P, pool_b));
                 CK(cudaMemset(A, 0, hot_b)); CK(cudaMemset(P, 0, pool_b)); }
    else       { CK(cudaMalloc(&A, ws_b)); CK(cudaMemset(A, 0, ws_b)); }

    // --- policy knobs --------------------------------------------------------------------------
    size_t sa_b = (size_t)(sa * MiB), got = 0;
#ifdef NO_POLICY_CALLS
    // Tracing build for Accel-Sim (-DNO_POLICY_CALLS): NVBit 1.8 fails inside cudaCtxResetPersistingL2Cache,
    // so no persistence API is called at all; only the baseline setting is meaningful here.
    if (sa != 0 || win != 0) { fprintf(stderr, "NO_POLICY_CALLS build runs the baseline only\n"); exit(2); }
    size_t win_b = 0;
#else
    CK(cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize, sa_b));
    CK(cudaDeviceGetLimit(&got, cudaLimitPersistingL2CacheSize));
    size_t win_b = std::min((size_t)(win * MiB), (size_t)pr.accessPolicyMaxWindowSize);
    win_b = std::min(win_b, clean ? hot_b : ws_b);
    cudaStreamAttrValue at; memset(&at, 0, sizeof(at));
    if (win_b > 0) {
        at.accessPolicyWindow.base_ptr = (void*)A;
        at.accessPolicyWindow.num_bytes = win_b;
        at.accessPolicyWindow.hitRatio = (float)hr;
        at.accessPolicyWindow.hitProp = cudaAccessPropertyPersisting;
        at.accessPolicyWindow.missProp = cudaAccessPropertyStreaming;
    }
    CK(cudaStreamSetAttribute(s, cudaStreamAttributeAccessPolicyWindow, &at));
    CK(cudaCtxResetPersistingL2Cache());
#endif

    size_t pool_slots = clean ? std::max<size_t>(1, pool_b / chunk_b) : 1;
    auto launch = [&](char* base, size_t bytes) {
        if (hint == 3)  rd_cs<<<grid, block, 0, s>>>((float4*)base, bytes / sizeof(float4), reps, out);
        else if (hint >= 6) rd_bulk<<<grid, block, 0, s>>>((float4*)base, bytes / sizeof(float4), reps, out, hint);
        else if (hint >= 4) rd_hint2<<<grid, block, 0, s>>>((float4*)base, bytes / sizeof(float4), reps, out, hint);
        else if (hint)  rd_hint<<<grid, block, 0, s>>>((float4*)base, bytes / sizeof(float4), reps, out, hint);
        else            rd<<<grid, block, 0, s>>>((float4*)base, bytes / sizeof(float4), reps, out);
    };
    auto step = [&](long k) {
        if (clean) { launch(A, hot_b); launch(P + (k % pool_slots) * chunk_b, chunk_b); }
        else for (int l = 0; l < layers; ++l) launch(A + (size_t)l * per_b, per_b);
    };

    for (int k = 0; k < warm; ++k) step(k);
    CK(cudaStreamSynchronize(s));
    std::vector<cudaEvent_t> ev(iters + 1);
    for (auto& e : ev) CK(cudaEventCreate(&e));
    CK(cudaEventRecord(ev[0], s));
    for (int k = 0; k < iters; ++k) { step(warm + k); CK(cudaEventRecord(ev[k + 1], s)); }
    CK(cudaStreamSynchronize(s));
    CK(cudaGetLastError());
    std::vector<float> ms(iters);
    for (int k = 0; k < iters; ++k) CK(cudaEventElapsedTime(&ms[k], ev[k], ev[k + 1]));
    std::vector<float> so = ms; std::sort(so.begin(), so.end());
    double mean = 0; for (float x : ms) mean += x; mean /= iters;

    // --- leave the device as we found it ---------------------------------------------------------
#ifndef NO_POLICY_CALLS
    memset(&at, 0, sizeof(at));
    CK(cudaStreamSetAttribute(s, cudaStreamAttributeAccessPolicyWindow, &at));
    CK(cudaCtxResetPersistingL2Cache());
    CK(cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize, 0));
#endif

    double step_bytes = clean ? (double)(hot_b + chunk_b) : (double)(per_b * layers);
    printf("{\"mode\":\"%s\",\"ws_mib\":%.1f,\"hot_mib\":%.1f,\"chunk_mib\":%.1f,\"layers\":%d,\"reps\":%d,"
           "\"setaside_req_mib\":%.2f,\"setaside_got_bytes\":%zu,\"window_bytes\":%zu,\"hitratio\":%.3f,"
           "\"step_bytes\":%.0f,\"iters\":%d,\"ms_median\":%.5f,\"ms_mean\":%.5f,\"ms_p10\":%.5f,\"ms_p90\":%.5f,"
           "\"l2_bytes\":%d,\"persist_max\":%d,\"window_max\":%d,\"hint\":%d,\"gpu\":\"%s\"}\n",
           mode.c_str(), ws, hot, chunk, clean ? 2 : layers, reps, sa, got, win_b, hr, step_bytes * reps, iters,
           so[iters / 2], mean, so[iters / 10], so[(iters * 9) / 10],
           pr.l2CacheSize, pr.persistingL2CacheMaxSize, pr.accessPolicyMaxWindowSize, hint, pr.name);
    return 0;
}
