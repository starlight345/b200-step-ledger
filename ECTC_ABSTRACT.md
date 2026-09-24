# ECTC 2027 — Abstract draft

**Submission**: deadline 2026-10-05 · 700 words max · separate ≤50-word novelty paragraph · one figure.
**Subcommittees** (two, in order): 1st **Thermal/Mechanical Simulation & Characterization** — it solicits "thermal and mechanical simulation and characterization … novel modeling techniques: multi-scale physics, model order reduction … model verification". 2nd **Packaging Technologies** — "advances in electrical/optical design and thermal solutions of 2.xD, TSV and 3D".
**Figure** (v2, 2026-09-24): `assets/figures/ectc-abstract.pdf` — (a) one tier, three thermal treatments (5.0 / 77.3 / 18.6 TB/s at 20 W, 0.5 pJ/bit) with the literature E/bit band; (b) the macro-resolved MAPDL transient over six decode steps, tier plane as inset. In the `_rev.docx` with an English Fig. 1 caption.

---

## Title

**Duty-Cycle-Aware Thermal and Energy Budgeting for BEOL-Stacked SRAM on LLM Inference GPUs**

## Novelty paragraph (42 words)

We derive a BEOL-stacked SRAM tier's thermal and energy specification from measured LLM-decode traffic rather than an assumed power map, and show that the standard steady-state screening rule and its obvious transient correction miss the verified answer by 4× in opposite directions.

## Abstract (699 words)

Restructured 2026-09-24 after reader feedback that the previous draft was hard to follow. One job per paragraph: problem · the load (defines duty) · three answers · verification (Ansys appears here only) · what limits the tier (heat) · nor energy, and the device risk · contribution. **Revised the same day**, twice: (1) the macro-resolved 3D transient model (ECTC_STORY 5-M) — P4 now ends on the real macro rather than on the two bounds, and P5's "within 0.43 K … for any tier count" (uniform, 1D) became "at most 1.14 K", 90% of the read power in the periphery and the worst-case BEOL conductivity together; (2) the E/bit anchor — [7] is Dieny et al. 2020 Table 1, and the pessimistic end now uses Jouppi et al. 2021's 7 nm macro-level read energy at our 1 Mb macro size [8] (0.260 → 0.374 pJ/bit). Against the steady-state bar that leaves 4%, so P6 now also states the verified-model bar (1.45 pJ/bit, 3.9×). **Also (evening):** the lumped value is 77.3 TB/s (0.0647, current literature stack; 76.9 was the earlier 1 µm / 1 µm guess) and the verified E/bit bar uses peak fraction 0.2693 → 1.45 pJ/bit.

Stacking SRAM in the back end of line (BEOL) above a GPU logic die adds on-chip memory capacity that die area cannot otherwise buy. Whether such a tier is worth building is usually screened with a steady-state rule: deliverable bandwidth ≤ power budget / energy per bit. We show that for large-language-model (LLM) inference this rule is applied to a load it does not describe, and that its verdict can be wrong by a factor of four in either direction.

We derive the load from the workload itself. During decode, a GPU reads the entire model once for every generated token. Using a measured decode traffic ledger for Llama-3.1-8B on a B200-class GPU, a design point of two BEOL tiers holding 4.22 GB serves 24% of each step's 17.2 GB of memory traffic. Delivered at the 19 TB/s on-die fabric limit, that traffic takes 217 µs of a 4.515 ms step: the tier is active only 4.80% of the time. We call this fraction the duty cycle. Decode is the worst case; in prefill the duty cycle stays below 0.5%.

At a 20 W tier budget and the device model's example of 0.5 pJ/bit, three thermal treatments of the same device disagree. The steady-state rule gives 5.0 TB/s, below the 6.40 TB/s the HBM already delivers, and rejects the tier. A single-node lumped RC model, the obvious correction for a pulsed load, gives 77.3 TB/s and accepts it with wide margin. A layered one-dimensional transient model gives 18.6 TB/s: the tier is viable, and its thermal limit nearly coincides with the fabric limit. The lumped model is 4.16× optimistic because a 50 nm tier and a 500 µm silicon substrate do not heat as one node: the tier's peak is governed by the thin BEOL beside it, not by the heat capacity of the whole stack. Varying model order shows that about ten nodes suffice, provided tier and substrate are kept separate.

The one-dimensional model matches two analytic solutions (0.07% and 2.30% error) and Ansys MAPDL on the identical stack, which returns the same 18.6 TB/s. In three dimensions, MAPDL agrees to 1.3% when tier power is uniform across memory macros, as in decode, which reads weights from all of them. Concentrating the same power into a 100 µm patch raises the peak 502×, owing to the low-conductivity BEOL beneath the tier, but decode produces no such patch. Within each macro, however, read power gathers in the peripheral circuits. A transient model resolving a 153 × 518 µm macro reproduces the 1D peak to 0.32%; placing 90% of the read power in its periphery raises the local power density 3.2× and the tier peak by only 0.41 K.

What, then, limits the tier? Not heat: on a logic plane dissipating the measured 349 W per die at a 100 °C junction, the tier peaks at most 1.14 K above the logic beneath it, even combining that periphery concentration with the worst-case BEOL conductivity. A sensitivity ranking shows that the surrounding BEOL moves the result by 95% and the tier material by 0.3% [3], [4], so thermal effort belongs in integration rather than in the memory device. Setting all five unmeasured stack parameters to their literature extremes at once, all 32 combinations still outperform the HBM.

Nor energy: a literature-based budget of 0.019–0.374 pJ/bit [5], [7], [8], whose pessimistic end uses 7 nm macro-level data for our 1 Mb macro, stays below even the 0.391 pJ/bit steady-state requirement and 3.9× below the 1.45 pJ/bit the verified model allows. The remaining device risk is read margin. With published 300 mm IGZO threshold spreads of 20–40 mV [2], the pass/fail boundary for a 4.22 GB array falls inside the range that typical 6T cells occupy, which makes it a cell-design question rather than an open one.

Prior thermal co-optimization of HBM-on-GPU stacks assumes power maps and sustained training loads [1], and architecture studies that stack the same oxide-transistor memory on GPUs do not analyze heat [6]. This work derives the tier's thermal and energy specification from measured decode traffic, and identifies which reduced-order thermal model can safely produce it. Stack geometry and materials form a parametric design study, not a fabricated device.

## References added 2026-09-24

- [7] B. Dieny et al., "Opportunities and challenges for spintronics in the microelectronics industry," *Nat. Electron.* 3(8), 446–459 (2020), doi:10.1038/s41928-020-0461-5 — Table 1: read energy/bit 17 (HP-SRAM 5 nm), 55 (HD-SRAM 5 nm), 50 fJ (HD-SRAM 7 nm). Its own source (a 2018 roadmap post) gives no energies, so these are estimates; cite the journal version, not arXiv 1908.10584 (no table).
- [8] N. P. Jouppi et al., "Ten lessons from three generations shaped Google's TPUv4i," *Proc. ISCA* 2021, pp. 1–14, doi:10.1109/ISCA52012.2021.00010 — Table 2: 64-bit SRAM read at ~7 nm, 8 KB 7.5 pJ, 32 KB 8.5 pJ, 1 MB 14 pJ (117 / 133 / 219 fJ/bit). Log-interpolated to the 1 Mb (128 KB) macro: 0.167 pJ/bit.

## Word counts

- Novelty paragraph: 42 / 50
- Abstract body: 699 / 700

## Closed since drafting

| # | Item | Result |
|---|---|---|
| **V-1** | **Commercial-solver correlation** | **Done.** Ansys MAPDL 26.1 (Mechanical Enterprise) on the identical stack: steady tier rise 0.8249 vs 0.8363 K (1.4%), periodic **peak fraction 0.2693 vs 0.2693 (0.02%)**. Both give the lumped-model error as 4.16× |
| **V-2** | **Hotspot / lateral spreading** | **Done.** 3D MAPDL, 4 mm repeating cell, same total watts: uniform 0.848 K (1.3% from the 1D solver, a third independent check), 100 µm patch 425 K — 502×, scaling as 1/area because the 8 µm low-k BEOL dominates before the heat spreads |
| **G-1** | **Causal validation of the traffic-to-time coefficient** | **Done, structurally.** On an RTX PRO 5000 Blackwell running Llama-3.1-8B under vLLM, two independent knobs -- context length at fixed batch, and batch at fixed context -- give slopes of 1.211 and 1.110 TB/s (R2 0.9998, 0.9999). An independent bandwidth probe of the same part measures 1.211 TB/s read-only and 1.105 TB/s copy, so each knob lands on the mode it should to 0.00% and 0.42%. The coefficient is the memory path, not a fitting artefact; B200's 6.40 TB/s is the same quantity with that part's bandwidth substituted |
| **V-3** | **Representative operating point** | **Done.** 3D MAPDL with the measured 349 W/die logic plane on, a finite convective sink calibrated to a 100 °C junction, and anisotropic BEOL: the tier's own heating is 7.5 mK on top of the logic. Uniform tier power is invariant to BEOL anisotropy (kxy/kz 1→50) to seven digits; the 100 µm patch falls 425→200 K, so 502× is the pessimistic end |
| **V-4** | **Macro-resolved 3D transient** | **Done.** C2 macro 153 × 518 µm with the L-shaped periphery (28.5% of the area) resolved, 6 duty cycles from an averaged steady start. Verification against 1D: periodic peak 0.224500 vs 0.225217 K (0.32%); mesh ×5.6 changes the local rise 0.10%. Periphery share 0.285 (uniform) → 0.9 raises density 3.16× and the tier peak 100.197 → 100.606 °C (+0.41 K); with the worst BEOL k = 1.0 as well, tier − logic = 1.144 K. BEOL anisotropy (kxy/kz = 10) moves it ≤ 6 mK at macro scale |
| **V-5** | **Second commercial solver** | **Done, steady.** Ansys Electronics Desktop 2026 R1, Icepak FEA (tetrahedral FEM, 4 µm length refinement in the thin layers), built independently from the same geometry and loads. Absolute temperatures agree with MAPDL to 0.97 K (1.6% of the 61 K stack rise); TIM and Si drops within 2% of analytic. The tier-over-logic local rise is 0.10 K against MAPDL's 0.03 K — tetrahedra in 50 nm layers overstate it, so MAPDL's hexahedral layering remains the reference |
| **T-3** | **Read margin at temperature** | **Closed with published σVth.** No operating Tj limit is published for BEOL oxide devices (400 °C is a process budget). The binding quantity is the mismatch component: with σVth 20–40 mV from 300 mm IGZO (Mitard et al., ECS Trans. 98, 205, 2020), a 4.22 GB array needs 7.20σ at 99% yield, giving an allowed SNM-to-σ ratio of 0.27–1.08 against 0.3–1.0 for typical 6T cells — a cell-design question, not an open one. Only dσ/dT remains unmeasured |

## Open items before the manuscript (due ~Feb 2027)

| # | Item | Why it matters |
|---|---|---|
| T-1 | Measured E/bit | **Literature-anchored**, per the device team's own direction: optimistic end 5 nm HP array (Dieny 2020, an estimate), pessimistic end 7 nm 1 Mb macro read with periphery (Jouppi 2021) × 2 BEOL penalty. Band 0.019–0.374 pJ/bit: under the steady-state bar 0.391 by only 4%, under the verified bar 1.45 by 3.9×. A measured BEOL-macro number would replace both anchors |
| T-2 | Real stack cross-section | **Literature-anchored**: 300 nm PECVD SiO2 interlayer dielectric, 6 nm IGZO / 10 nm HfO2 device, a-IGZO k = 1.4–2.6 W/m/K measured. Replaced the earlier 1 um / 1 um guess; conclusions moved by under 2% |
| T-3 | dσVth/dT | Room-temperature σ is published; how much it grows at the 90–105 °C tier temperature is the one measurement we would ask for |
