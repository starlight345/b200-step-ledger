# B200 Ledger3D matched-object placement experiment

Registered before any measurement on 2026-09-16 (Asia/Seoul).

## Question

On one physical B200, when equal-sized weight-like, KV-like, and recurrent-state-like
objects compete for the same finite on-chip cache, which object should receive the
existing CUDA persisting-access window?

This is a controlled memory experiment on the B200's real L2 cache. It is a proxy
for placement policy and is not a measurement of fabricated 3D SRAM capacity,
latency, energy, temperature, or end-to-end LLM inference.

## Fixed workload

- Three distinct 64 MiB objects, each split across 36 model-like layers.
- Weight-like object: read once per step (logical traffic/resident byte = 1).
- KV-like object: read once per step (logical traffic/resident byte = 1).
- Recurrent-state-like object: read and written once per step (logical
  traffic/resident byte = 2).
- `ld.global.cg` bypasses L1. Kernel bodies and addresses are identical across
  placement policies.
- All six within-layer object orders are tested so a favorable recency order is
  not selected after measurement.
- Policies: default, reservation-only control, persist weight, persist KV, and
  persist state. The target windows have identical sizes and hit-ratio hints.
- Three repetitions use rotated policy orders. Each trial includes warm-up,
  pilot timing, and approximately 250 ms of measured graph replay.
- Exact recurrent-state updates are validated after every trial.

## Prediction and decision rule

The Ledger score is avoided off-chip traffic per resident byte per step. It
predicts state (score 2) ahead of weight and KV (score 1 each). The primary
comparison is the geometric mean speedup over the matched default across all
six object orders and three repetitions. Report every cell and reversals; do not
select only favorable orders. Reservation-only separates capacity carving from
the access-window target.

Support requires persist-state to have the largest aggregate speedup and no
correctness failures. A tie, reversal, or slowdown remains a result and rejects
the simple score for this workload.

## Limits

No GPU performance counters are available, so logical bytes are not labeled as
measured HBM traffic. Existing full-model measurements provide the separate
physical-traffic evidence. This experiment tests whether a real finite on-chip
cache responds to the placement ranking; it does not claim that B200 contains
the proposed 3D SRAM.
