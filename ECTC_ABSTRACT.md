# ECTC 2027 — Abstract draft

**Submission**: deadline 2026-10-05 · 700 words max · separate ≤50-word novelty paragraph · one figure.
**Subcommittees** (two, in order): 1st **Thermal/Mechanical Simulation & Characterization** — it solicits "thermal and mechanical simulation and characterization … novel modeling techniques: multi-scale physics, model order reduction … model verification". 2nd **Packaging Technologies** — "advances in electrical/optical design and thermal solutions of 2.xD, TSV and 3D".
**Figure**: `assets/figures/ectc-abstract.pdf`.

---

## Title

**Duty-Cycle-Aware Thermal and Energy Budgeting for BEOL-Stacked SRAM on LLM Inference GPUs**

## Novelty paragraph (42 words)

We derive a BEOL-stacked SRAM tier's thermal and energy specification from measured LLM-decode traffic rather than an assumed power map, and show that the standard steady-state screening rule and its obvious transient correction miss the verified answer by 4× in opposite directions.

## Abstract (650 words)

Restructured 2026-09-24 after reader feedback that the previous draft was hard to follow. One job per paragraph: problem · the load (defines duty) · three answers · verification (Ansys appears here only) · what limits the tier (heat) · nor energy, and the device risk · contribution.

Stacking SRAM in the back end of line (BEOL) above a GPU logic die adds on-chip memory capacity that die area cannot otherwise buy. Whether such a tier is worth building is usually screened with a steady-state rule: deliverable bandwidth ≤ power budget / energy per bit. We show that for large-language-model (LLM) inference this rule is applied to a load it does not describe, and that its verdict can be wrong by a factor of four in either direction.

We derive the load from the workload itself. During decode, a GPU reads the entire model once for every generated token. Using a measured decode traffic ledger for Llama-3.1-8B on a B200-class GPU, a design point of two BEOL tiers holding 4.22 GB serves 24% of each step's 17.2 GB of memory traffic. Delivered at the 19 TB/s on-die fabric limit, that traffic takes 217 µs of a 4.515 ms step: the tier is active only 4.80% of the time. We call this fraction the duty cycle. Decode is the worst case; in prefill the duty cycle stays below 0.5%.

At a 20 W tier budget and the device model's example of 0.5 pJ/bit, three thermal treatments of the same device disagree. The steady-state rule gives 5.0 TB/s, below the 6.40 TB/s the HBM already delivers, and rejects the tier. A single-node lumped RC model, the obvious correction for a pulsed load, gives 76.9 TB/s and accepts it with wide margin. A layered one-dimensional transient model gives 18.6 TB/s: the tier is viable, and its thermal limit nearly coincides with the fabric limit. The lumped model is 4.16× optimistic because a 50 nm tier and a 500 µm silicon substrate do not heat as one node: the tier's peak is governed by the thin BEOL beside it, not by the heat capacity of the whole stack. Varying model order shows that about ten nodes suffice, provided tier and substrate are kept separate.

The one-dimensional model matches two analytic solutions (0.07% and 2.30% error) and Ansys MAPDL on the identical stack, which returns the same 18.6 TB/s. A three-dimensional MAPDL model then covers what one dimension cannot. With the tier power spread uniformly, which is the decode case because weights stream from every memory macro, it agrees with the 1D model to 1.3%. Concentrating the same power into a 100 µm patch instead raises the peak 502×, owing to the low-conductivity BEOL beneath the tier. That is an upper bound: realistic anisotropic BEOL wiring lowers it, while leaving the uniform case unchanged.

What, then, limits the tier? Not heat: on a logic plane dissipating the measured 349 W per die at a 100 °C junction, the tier's peak stays within 0.43 K of the junction for any tier count. A sensitivity ranking shows that the surrounding BEOL moves the result by 95% and the tier material by 0.3% [3], [4], so thermal effort belongs in integration rather than in the memory device. Setting all five unmeasured stack parameters to their literature extremes at once, all 32 combinations still outperform the HBM.

Nor energy: a literature-based budget of 0.019–0.260 pJ/bit [5], [7] stays below the 0.391 pJ/bit that even the steady-state rule requires, with 1.5× margin at the pessimistic corner. The remaining device risk is read margin. With published 300 mm IGZO threshold spreads of 20–40 mV [2], the pass/fail boundary for a 4.22 GB array falls inside the range that typical 6T cells occupy, which makes it a cell-design question rather than an open one.

Prior thermal co-optimization of HBM-on-GPU stacks assumes power maps and sustained training loads [1], and architecture studies that stack the same oxide-transistor memory on GPUs do not analyze heat [6]. This work derives the tier's thermal and energy specification from measured decode traffic, and identifies which reduced-order thermal model can safely produce it. Stack geometry and materials form a parametric design study, not a fabricated device.

## Word counts

- Novelty paragraph: 44 / 50
- Abstract body: 700 / 700

## Closed since drafting

| # | Item | Result |
|---|---|---|
| **V-1** | **Commercial-solver correlation** | **Done.** Ansys MAPDL 26.1 (Mechanical Enterprise) on the identical stack: steady tier rise 0.8249 vs 0.8363 K (1.4%), periodic **peak fraction 0.2693 vs 0.2693 (0.02%)**. Both give the lumped-model error as 4.16× |
| **V-2** | **Hotspot / lateral spreading** | **Done.** 3D MAPDL, 4 mm repeating cell, same total watts: uniform 0.848 K (1.3% from the 1D solver, a third independent check), 100 µm patch 425 K — 502×, scaling as 1/area because the 8 µm low-k BEOL dominates before the heat spreads |
| **G-1** | **Causal validation of the traffic-to-time coefficient** | **Done, structurally.** On an RTX PRO 5000 Blackwell running Llama-3.1-8B under vLLM, two independent knobs -- context length at fixed batch, and batch at fixed context -- give slopes of 1.211 and 1.110 TB/s (R2 0.9998, 0.9999). An independent bandwidth probe of the same part measures 1.211 TB/s read-only and 1.105 TB/s copy, so each knob lands on the mode it should to 0.00% and 0.42%. The coefficient is the memory path, not a fitting artefact; B200's 6.40 TB/s is the same quantity with that part's bandwidth substituted |
| **T-3** | **BEOL device Tj limit** | **Bounded, not closed.** No published maximum operating junction temperature exists for BEOL oxide-semiconductor devices; the often-quoted 400 °C is a *process* budget, not an operating limit. The binding evidence is bias-temperature instability: the best reported temperature stability is ΔVth ≈ −1.5 V across −25 to 105 °C, and our tier sits at the logic junction (≈ 90–105 °C). That shift is large against the device deck's own 155 mV read SNM |

## Open items before the manuscript (due ~Feb 2027)

| # | Item | Why it matters |
|---|---|---|
| T-1 | Measured E/bit | **Literature-anchored**, per the device team's own direction. Margin is now 1.5× at the pessimistic corner. A measured BEOL-array number would replace the gain-cell ratio |
| T-2 | Real stack cross-section | **Literature-anchored**: 300 nm PECVD SiO2 interlayer dielectric, 6 nm IGZO / 10 nm HfO2 device, a-IGZO k = 1.4–2.6 W/m/K measured. Replaced the earlier 1 um / 1 um guess; conclusions moved by under 2% |
| T-3 | BEOL device absolute Tj limit | The binding constraint we identify but cannot evaluate |
