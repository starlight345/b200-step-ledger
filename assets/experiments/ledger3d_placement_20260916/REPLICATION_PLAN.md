# Frozen-code cross-device replication

Registered before the replication measurement on 2026-09-16 (Asia/Seoul), after
the primary physical-GPU-0 result was analyzed.

- Run the unchanged `placement_probe` binary and source on physical B200 GPU 1.
- Use the same six object orders, five policies, three repetitions, sizes,
  warm-up, timing, and validation.
- Save replication rows and analysis separately from the primary run.
- Primary replication check: zero validation errors and the aggregate ranking
  `persist_state` above both `persist_weight` and `persist_kv`.
- Report a reversal or failure; do not change the source or select orders.
- This tests device repeatability of the real-L2 proxy. It does not convert the
  proxy into a fabricated-3D-SRAM measurement.
