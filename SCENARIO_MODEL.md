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

## Whole-system overview

The default view presents all stores and links simultaneously. Storage bars use the capacity of each memory as their denominator. Gray HBM capacity is unmodeled, not measured free space. Recorded cases use hatching for unknown L2 contents. What-if model cases default to a visibly labeled hypothetical steady-state composition, with an option to show unknown contents instead. Near-memory read and write paths are separate; link totals are not summed into HBM traffic. Link service bars show aggregate read+write bytes divided by the chosen bandwidth on a common time scale. These are not measured end-to-end step latencies.

The moving dots are a fixed 16 MiB link-service illustration, using the same time multiplier on every link. Their count and line width do not encode aggregate traffic. The adjacent byte labels and service bars show the whole scenario's volume and duration. Sequential dependencies and eviction order can be inspected in the separate request view.

Scenarios: a whole model step, mixed repeated/new reads, explicitly prewarmed hits, cold misses, capacity eviction, dirty eviction, and preloaded near-memory reads. Teaching scenarios use the same deterministic cache engine as the request view. The initial/final L2 toggle changes the illustrated cache snapshot without changing the scenario's total traffic. Their hit ratios are not inputs to whole-model estimates.

### Recorded cases

- 64 and 256 MiB placement cases load `assets/placement_sweep_summary.json` and the matching `placement_m64_l36.jsonl` / `placement_m256_l36.jsonl`. Object sizes come from the actual aligned integer `object_bytes`, not the rounded requested MiB. Policies compare the same order/pass cells. Speedup is `exp(mean(log(default_step_ms / policy_step_ms)))`, not a ratio of policy medians. The displayed median times are separately summarized. The 64 MiB sweep value (1.108287×) is distinct from the two-device pooled matched-object result (1.109926×).
- Those trials measure timing, allocated objects, reservation/window settings and validation errors. Their per-object HBM traffic, L2 hit counts and L2 residency are **unknown**. Reservation coverage is a budget ratio, not an observed hit rate. Logical read/write counts are known from the test program.
- Llama and Granite decode cases load exact B=8, context=2048 records from `assets/model_evidence.json`. Measured times are median intervals between synchronized `execute_model` completions, not pure kernel time. Storage/requests in their diagram are separate structural calculations. The Granite DCGM state ratio is identified as a separate calibrated regression and is not silently assigned to the displayed decode run.
- Changing model conditions leaves a recorded case and enters a what-if calculation. Editing bandwidth assumptions does not recompute recorded execution times.

## Whole-model inputs

The following are **calculator scenario constants**, not measurements of HBM read bytes or complete allocation dumps. Some were inherited from the earlier traffic calculator without a per-coefficient raw-data mapping; the UI therefore does not label them measured. `assets/numerical_evidence.json` explicitly records the Llama 16.1 GB resident-weight / 15.1 GB step-read inputs as model quantities. Fixed B=8, context=2048 timing anchors are traceable to `assets/model_evidence.json`; they do not become measured timings at other batch/context settings.

| Model | weight payload GB | fixed step read GB | base ms | KV/state structural inputs |
|---|---:|---:|---:|---|
| Llama-3.1-8B | 16.1 | 15.1 | 4.5556 | 32 × 4096 B/token |
| Qwen3-8B | 16.4 | 13.9 | 4.7256 | 36 × 4096 B/token |
| Mistral-7B | 14.5 | 14.2 | 4.5825 | 32 × 4096 B/token |
| Llama-2-7B | 13.5 | 13.2 | 5.3264 | 32 × 16384 B/token |
| Granite | 14 | MoE formula | 4.6995 | 4 × 2048 B/token; 36 × 806400 state B/request |
| Gemma-3-27B | 54.8 | 54.8 | 13.3924 | 10 global + 52 window-1024 layers, 8192 B/token/layer |
| gpt-oss-120b | 61 | MoE formula | 6.7203 | 18 global + 18 window-128 layers, 2048 B/token/layer |
| DeepSeek-V2-Lite | 31.4 | MoE formula | 4.6275 | 27 × 1152 B/token |

MoE step-read assumption (GB): `trunk + per_expert_per_layer × layers × E × (1 − (1 − k/E)^B)`. This assumes independent uniform routing, not a replay of actual expert selections. Constants `(trunk, per_expert_per_layer, layers, E, k)` are Granite `(1.92, .00472, 40, 64, 6)`, gpt-oss `(3, .0133, 36, 128, 4)`, DeepSeek `(2, .0176, 26, 64, 6)`.

`KV = B Σ(layers × bytes/token/layer × effective_tokens)` with `effective_tokens = N` for global attention and `min(N, window)` for sliding attention. This is effective payload; allocator pool reservations, padding, activations and workspace are omitted. `KV write = B Σ(layers × bytes/token/layer)`. `state = B Σ(layers × state_bytes/layer/request)` and its assumed steady-state access is read+write = `2 × state`.

Placement ranks `(read+write)/allocation`, or obeys the manually chosen first object, and fills available near capacity. `served = access × placed/allocation` assumes uniform access within each object. Added SRAM starts populated and stays resident: initial fill, dirty eviction and final flush costs are omitted. Cached copies do not remove HBM backing payload. New writes are apportioned by the same placement fraction, not by a measured address trace.

Added mode assumes zero ordinary-L2 reuse saving: `HBM = total access − near service`. This is a scenario assumption, not an observed zero hit rate. Partition mode also subtracts `min(1, normal_L2 / remaining_working_set) × remaining_traffic`, a uniform capacity-coverage approximation. Physical L2 capacity remains 132,644,864 B across its normal and protected regions. Exact replacement/set conflicts are not modeled. Measured proxy speedups are displayed only for supported object sizes in partition mode with the experiment's maximum reservation; there is no nearest-size interpolation presented as measured.

Whole-model service time is `HBM bytes/HBM BW + near bytes/near BW`, with request latency omitted because no request-count model exists. Link-specific overview bars additionally expose L2 service. The older hypothetical speedup uses `compute_floor = max(.02 ms, fixed_base_ms − total_bytes/HBM_BW)` and `max(compute_floor, HBM_service, near_service)`; it is a coarse illustration, not an end-to-end performance prediction. Hardware counter access was unavailable for the new microbenchmarks, so none of these byte expressions is relabeled measured HBM traffic.

### Overview verification

`tests/scenario-overview.test.cjs` validates warm/cold/mixed read conservation, insufficient-capacity behavior, near-memory fallback, measured geometric-mean reproduction from all 18 matching trial pairs per policy, and placement/traffic conservation across 648 model/mode/capacity/batch/context combinations. Browser checks cover all 11 scenario choices, recorded/what-if transitions, the initial/final occupancy toggle, overview-to-request continuity, bandwidth sensitivity and console errors.

## L2 composition estimate and HBM scale

The what-if overview can draw a steady-state hypothesis even though an actual per-object L2 snapshot is unavailable. For each object, define `W_i = allocation_i - placed_near_i`. Let `U = min(normal_L2_capacity, sum(W_i))`. Draw `U * W_i / sum(W_i)` bytes for each object, or zero when the remaining working set is zero. This assumes uniformly mixed eligible bytes, excluding the idealized near-memory copies. It does not infer real line residency, sets, recent kernel access order or expert routing. It cannot be read as a measured or predicted hit rate. Toggle `L2 내용 표시` to compare this hypothesis with the unknown-state display. The toggle does not alter the existing traffic or timing calculation.

If the working set exceeds normal L2 capacity, this hypothesis fills the available normal region. Smaller working sets do not necessarily fill it. Actual warm cache fullness is not a guarantee of hits: a requested address can be absent even when all eligible lines are occupied. Cold start, small accessed working sets, invalidation and mapping/policy constraints can change occupancy. NVIDIA documents hit rate as the fraction of requested sectors that do not miss, a different quantity from capacity usage: https://docs.nvidia.com/nsight-compute/ProfilingGuide/#l2-cache .

The partition model is an idealized fixed-region approximation. Actual CUDA persisting L2 is a priority mechanism; unused set-aside capacity can be used by normal/streaming accesses. The diagram is not evidence of physically exclusive regions: https://docs.nvidia.com/cuda/archive/13.0.0/cuda-c-programming-guide/index.html#l2-cache-set-aside-for-persisting-accesses .

An equal-object 64 MiB proxy allocates approximately 192 MiB of test objects (exact aligned sizes are recorded separately), which is only about 0.11% of the CUDA-reported 191.5 GB device. It is not an entire LLM. Proxy views are explicitly labeled and never display their internal size selector as a token count. HBM remains scaled to device capacity, with a separate expanded composition bar whose denominator is only the displayed payload. Full-model payload omits reserved KV pools, activations, workspace and allocator overhead; unmodeled HBM capacity is not measured free memory.

Changing a scenario or any computational input rebuilds and pauses the overview animation and resets/pauses the request journey. The overview labels motion as a repeating path illustration, not a running GPU model, and announces the newly calculated condition. Press play to start the new condition. Playback-speed changes alone do not change or restart the memory scenario.
