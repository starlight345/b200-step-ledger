# B200 last-window cache experiment · registered before measurements

2026-09-16, Asia/Seoul. Use physical GPU 1 only after verifying no other compute process. GPU 0 and GPU 2 services remain untouched.

## Question and scope

At identical GPU/L2 hardware and an identical address sequence, does the existing CUDA persisting-access mechanism change elapsed time for a state-update stream interleaved with weight reads? This tests an existing policy, not a newly invented policy. A positive result supports the importance of management but does not establish novelty. A null result remains a result.

This is a controlled memory microbenchmark using Granite-4.0-h-tiny state footprints (36 layers, 806400 bytes per layer per sequence). Arithmetic is exact uint32 increment, not Mamba/SSM arithmetic; weight read kernels are not GEMMs. It is not end-to-end LLM inference or physical 3D SRAM enlargement. No output will label it as those measurements.

## Matched conditions

- B=1,2,4,8; state total 29,030,400 × B bytes.
- Distinct weight buffers per layer, 0/8/64/256 MiB per layer, 36 layers. This sweeps intervening traffic across the physical cache size.
- Same cg loads (bypass L1), identical kernel bodies, launch order and CUDA graphs in every policy.
- Policies: default (no reserved region); reserved_normal (same reservation as persistence but no window); persist_state_1; persist_state_tuned (hint=min(1, reserved/window)). The hint is an access-property fraction, NOT measured hit rate.
- Record actual reservation, maximum window, coverage. State beyond the device window remains unprotected and is not silently treated as protected.
- Three passes with reversed/rotated policy order; ten warm graph iterations, five pilot iterations, then approximately 200 ms of graph replay per trial. Pilot iteration counts and timing recorded. Smoke run uses one cell, one pass and shorter timing.
- Verify every state element equals the exact number of updates after each trial. Abort on any mismatch.
- No clock/power/driver changes. Record background GPU utilization and power/clock snapshots.

## Outputs and decision rules

Primary: CUDA-event time per complete 36-layer memory-proxy step; report all passes and policy ratios against matched default. Report variation, including reversals; do not select a single favorable cell. Reservation-only control separates carving out L2 from access hints.

HBM bytes and hit rate require GPU performance counters. A fresh ncu probe is blocked by ERR_NVGPUCTRPERM; logical bytes must NOT be relabeled as measured HBM traffic. If an administrator-supported profiling path becomes available, save direct read/write/L2 counters with cache flush disabled and control for replay. No access or driver bypass.

Capacity changes in a future simulator will be synthetic counterfactuals. This experiment can validate behavior at today's hardware size only.

## Preservation

Save source, environment, raw JSONL, stdout/stderr, timing summaries and hash manifests on the Mac and enduring Ampere before final reporting. Do not rely on B200 retaining the only copy.
