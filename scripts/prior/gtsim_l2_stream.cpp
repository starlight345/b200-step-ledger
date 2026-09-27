// Drive GPU-Tile-Sim's own L2 model (tilegen/include/memory.h, class L2Cache, unmodified) with the
// line-address stream of one workload, and count the DRAM reads of the measured steps.
//
// GTSim v0.1.0 cannot build a decode step itself: its GEMM builder tiles M by 128 (decode GEMV has
// M = batch = 1 or 8 -> zero tiles) and N by 256. So the workload's accesses are fed to its L2 directly,
// one 128-B line at a time; a miss is an access that finds its line neither in the cache nor in flight
// (MSHR), which is exactly when L2Cache::step() enqueues a DRAM read.
//
// Stream per step (same order every step, as the GPU runs it):
//   llm   : ws MiB read front to back
//   clean : hot MiB read, then a fresh chunk MiB from a pool that advances every step
//
// Build: c++ -O2 -std=c++17 -I<tilegen>/include gtsim_l2_stream.cpp -o gtsim_l2_stream
// Usage: gtsim_l2_stream <L2 MiB> llm <ws MiB> [warm meas]
//        gtsim_l2_stream <L2 MiB> clean <hot MiB> <chunk MiB> <pool MiB> [warm meas]
#define private public          // read-only access to cache / MSHR state for counting; no logic changed
#include "memory.h"
#undef private
#include <cstdio>
#include <cstdlib>
#include <cstring>

using namespace GTSim;

int main(int argc, char** argv) {
    if (argc < 4) { std::fprintf(stderr, "usage: see header\n"); return 1; }
    const double C_mib = std::atof(argv[1]);
    const bool llm = std::strcmp(argv[2], "llm") == 0;
    const int line = 128;
    const std::uint64_t MiB = 1ull << 20;
    double ws = 0, hot = 0, chunk = 0, pool = 0; int ai = 3;
    if (llm) ws = std::atof(argv[ai++]);
    else { hot = std::atof(argv[ai++]); chunk = std::atof(argv[ai++]); pool = std::atof(argv[ai++]); }
    int warm = argc > ai ? std::atoi(argv[ai++]) : 6;
    int meas = argc > ai ? std::atoi(argv[ai++]) : 4;

    // GTSim H100 defaults for everything that does not decide hit/miss; capacity and line from the GPU
    L2Cache l2(static_cast<int>(C_mib * MiB), line, 380, 1 << 20, 1 << 19, 1 << 30, false,
               1 << 20, 1, 2370.0, 2370.0);
    int cycle = 0;
    auto access = [&](std::uint64_t addr) -> bool {           // returns true if it went to DRAM
        CacheLineKey key{0, (addr / line) * line};
        bool miss = l2.cache.find(key) == l2.cache.end() && l2.mshr.find(key) == l2.mshr.end();
        while (!l2.enqueue_transaction_key(0, key, false)) l2.step(cycle++);
        do { l2.step(cycle++); } while (!l2.mshr.empty() || !l2.l2_queue_read.empty());
        return miss;
    };
    const std::uint64_t hot_b = static_cast<std::uint64_t>((llm ? ws : hot) * MiB);
    const std::uint64_t chunk_b = static_cast<std::uint64_t>(chunk * MiB);
    const std::uint64_t pool_base = 1ull << 40, pool_b = static_cast<std::uint64_t>(pool * MiB);
    std::uint64_t pool_off = 0, dram = 0;
    for (int s = 0; s < warm + meas; ++s) {
        std::uint64_t miss = 0;
        for (std::uint64_t a = 0; a < hot_b; a += line) miss += access(a);
        for (std::uint64_t a = 0; a < chunk_b; a += line) {
            miss += access(pool_base + pool_off); pool_off = (pool_off + line) % pool_b;
        }
        if (s >= warm) dram += miss * line;
    }
    std::printf("{\"dram_read_per_step\": %.1f}\n", static_cast<double>(dram) / meas);
    return 0;
}
