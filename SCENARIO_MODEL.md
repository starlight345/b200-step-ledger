# Scenario Lab measurement boundaries

The whole-model cards retain the existing structural / calibrated traffic calculator. They are separate from the new representative-tile cache journey; the journey's hit rates and HBM bytes are not silently substituted into whole-model predictions.

## Journey model

- A deterministic sequence reads the same tile, introduces competing tiles, or modifies tile A and later evicts it. Modification is a synthetic mutable-state example, not an inference weight update.
- Fully associative, byte-capacity-limited LRU with whole illustrative tiles (16/32/64 MiB), write allocation and write-back. These tiles are not real 128-byte GPU cache lines. Sets, compression, request concurrency, prefetching, bank conflicts, L1, scheduling, instruction execution and real cache replacement are omitted.
- Initial normal L2 is empty. In the comparison, the near-memory case assumes A has already been placed there; the cost of initially populating it is excluded. No final dirty-cache flush is imposed.
- HBM reads pass through L2. On a hit, only L2 lookup and L2-to-compute service are charged. On a miss, lookup + HBM fixed delay + HBM transfer + L2-to-compute service are serialized. Fill bookkeeping itself has no additional delay because transfer into L2 is already included. Dirty eviction adds an HBM write before replacement. No compute execution time is claimed.
- A tile larger than available normal L2 is streamed but not retained as a whole tile. This is a coarse-model limitation, not a hardware rule.
- B200 device-query constants: L2 132,644,864 B; maximum persisting reservation 82,903,040 B; CUDA-reported device memory 191,503,138,816 B. In partition mode the near store is the idealized protected region of the same L2, and the normal region shrinks. Ideal persistence is a scenario assumption, not a guarantee made by CUDA access-policy hints.
- Editable example defaults: HBM 8 TB/s and 400 ns; L2 30 TB/s and 100 ns; added SRAM 20 TB/s and 50 ns. These link/lookup numbers are assumptions, not measurements or a B200 specification. Decimal TB/s is used. Duration in ns is latency_ns + bytes / (TBps * 1000).
- Animation uses one common time multiplier for all routes: 500,000 / selected_playback_speed. No per-route minimum display time or independent animation speed hides the relative durations. Zero-duration bookkeeping can be inspected with the next-action button. The simulation pauses on completion.

## Storage color semantics

Pink = weights, teal = KV, green = state. HBM bars show computed persistent backing payload against CUDA device capacity. Gray is unmodeled capacity, including possible activation, workspace, allocator reservations and free space; it is not measured free memory. Near-memory bars show placement fractions against selected capacity; gray there means unassigned capacity. A cached copy does not delete the HBM backing data. If persistent payload alone exceeds device capacity, the page shows an explicit warning and normalizes the bar to payload to prevent layout overflow.

L2 entries and percentages are state in the representative-tile simulator, not a measurement of real B200 cache contents. Entry colors follow object kinds; a yellow border marks dirty contents. Percentages use available normal L2 capacity, so the fractional space that cannot hold another whole illustrative tile stays empty.

## Verification

`node tests/cache-journey.test.cjs` checks repeated-read conservation, hits/misses, LRU eviction, dirty write-back ordering, capacity bounds, zero capacity and bandwidth sensitivity. Browser checks cover playback completion, dirty eviction (16 MiB written back), live storage colors, timing changes, preset changes and console errors.

References: [NVIDIA Nsight Compute cache and memory guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/), [CUDA persisting L2](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#device-memory-l2-access-management).
