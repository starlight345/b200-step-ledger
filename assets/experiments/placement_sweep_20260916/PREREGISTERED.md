# Final B200 measurement window

Registered 2026-09-16, before the new measurements described here. Access ends at midnight KST. Stop admitting GPU jobs at 23:35, terminate only this campaign's own jobs by 23:40 if needed, and reserve the final 20 minutes for preservation. Existing jobs must never be killed or overlapped.

Primary gaps:

1. Long-context **accuracy**, not only refresh-row savings, for the existing observation-window retention policy. Use Llama, Mistral, Qwen3 at 16K and 32K on essay needle, multi-key retrieval, variable tracking and common-word extraction. Save full-cache outputs, protected-cache outputs, low-occupancy-row-drop outputs, and matched-count random token-drop controls. Preserve absolute token positions. Report per-reference fraction and all-reference success separately. The selector does not see answers.
2. Recover actual model parameter/buffer and KV/state tensor metadata after allocation, with shared storage deduplicated, plus phase-specific allocated/reserved/peak memory. No tensor values or HBM counters are inferred from the metadata. Use both vLLM runner implementations and avoid the earlier pre-allocation empty-dump mistake.
3. Finish the registered equal-object placement experiment, then sweep object size, access order, and repeated trials. Report reversals and reservation-only controls. These are memory proxies, not physical 3D SRAM or full LLM speedups.
4. Fill missing baseline cells and preserve runtime dependencies, configurations, source code and large previously excluded traces. Capture every completed job before proceeding to lower-priority work.

Existing studies remain immutable. New scripts/results live under final_window_20260916 on B200 and final-window-20260916 locally. Empty dumps, OOMs, unsupported models, deadline skips and numerical disagreements are recorded explicitly. Dataset identity uses content fingerprints, not a potentially repeated dataset index. Quality statements require a successful full-cache control on the same samples.

The observation-window prefill uses SDPA for the prefix and eager attention only for the final 64 prefix queries. Their summed key scores implement the same causal final-window score with less transient memory; this needs an 8K equivalence check before claiming numerical equivalence with the historical full-eager implementation. Source revision, backend and timings are recorded. This implementation difference is never silently pooled with historical results.

## Added before dynamic-phase measurements, 21:55 KST

Use three equal 64 MiB objects and 36 chunks. Weight-dominant phase calls weight read six times, KV read once, state update once per chunk; KV-dominant swaps weight/KV multiplicities; state-dominant calls state update three times and reads the other objects once. Test all six phase orders, phase lengths 1/8/64/256 steps, three rotated policy passes, fixed total measured work of 512 steps per phase. Repeated reads are adjacent within chunks, so logical reuse may already be served by existing cache and does not imply repeated HBM traffic.

Compare default, reservation-only, fixed weight/KV/state, and a phase-informed logical-access selector with and without resetting persisting status on a switch. The selector knows the synthetic phase and is not claimed to be an optimal policy, learned predictor, or new cache algorithm. Record whole wall time, CUDA-event time by phase, host API switching time, switch count, and exact state-update correctness. All policies synchronize at the same phase boundaries. Graph construction is excluded; runtime switching and phase synchronization are included in wall time. Compare against the best fixed policy and report slowdowns as well as improvements.
