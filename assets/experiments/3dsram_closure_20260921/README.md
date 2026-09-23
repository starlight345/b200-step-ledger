# 3D SRAM closure replay, 2026-09-21

This experiment is a logical object-tile replay. It does not emulate GPU cache sets, measure HBM counters, or measure post-3D latency.

## Reproduce

```bash
python3 replay_area_policy.py
python3 analyze_baseline_p99.py
```

`replay_area_policy.py` requires Python and Matplotlib. `analyze_baseline_p99.py` requires NumPy.

## Inputs

- `inputs/llama-b8-l2048-events.jsonl`: 96 weight/KV read and append-write events copied from the preserved 2026-09-16 ledger.
- `inputs/baseline_b8_l2048_first32.json`: first 32 decode completion timestamps for B=8, initial context 2048 from three clean identical-prompt runs. This is enough to reproduce the exploratory baseline quantiles, not a reliable p99 campaign.

## Outputs

- `outputs/closure_area_policy.csv`: C2/C3, 1/2 layer, 400–800 mm², sL2 topology and policy sweep.
- `outputs/closure_summary.json`: 600 mm², 2-layer summary.
- `outputs/closure_area_policy.{png,svg}`: HBM logical-byte reduction figure.
- `outputs/baseline_p99_sensitivity.{csv,json}`: baseline interval quantiles and warmup sensitivity.

The `optimistic_p99_*` columns in the area-policy CSV are Amdahl sensitivity columns. They are excluded from paper claims because the HBM-critical fraction and new-tier service have not been measured.

## Terms

- **sL2** — the existing *silicon* L2 on the B200 die, 132,644,864 B as measured by `cudaDeviceProp`. Named to distinguish it from the stacked 3D tier. Not an NVIDIA or device-team term.
- **LIP** — LRU-Insertion Policy: a new line enters at the LRU position rather than MRU, so a streaming scan cannot evict the whole cache. `integrated LRU` is the plain-LRU control.

## Revision 2026-09-21 (Claude, after Codex hit its usage limit)

Presentation only. `closure_area_policy.csv` and `closure_summary.json` are byte-identical to the previous run, so no number changed; only `replay_area_policy.py` and the two rendered images differ, and `SHA256SUMS` was regenerated for those three.

The figure previously drew five series, three of which coincide, so only three were visible. The coincidences are the result, so they are now drawn with distinct widths and dashes and annotated in place:

| Coincidence | Value (600 mm², C2, 2 tiers) | What it means |
|---|---|---|
| `keep_sL2_separate_3D` == `remove_sL2_3D_only` | 18.3771 % both, to 4 decimals | The existing 126 MB sL2 contributes zero bytes to this 15 GiB/step stream. Deleting it changes nothing. |
| `integrated_sL2_plus_3D_LIP` ≈ `ideal_nonoverlap_retention_bound` | 19.1844 vs 19.1912 %, 0.007 %p apart | One merged scan-resistant cache already reaches the managed non-overlap upper bound. |
| `integrated_LRU` | flat −0.7946 % at every area | Capacity cannot fix the replacement policy. |

The y axis is HBM logical-byte reduction, not speedup; the corresponding model speedup for the same point is 1.073–1.115×. See `../../../WORKLOG_3DSRAM.md` for how these rows feed the paper claims.
