# ECTC 2027 — Abstract draft

**Submission**: deadline 2026-10-05 · 700 words max · separate ≤50-word novelty paragraph · one figure.
**Subcommittees** (two, in order): 1st **Thermal/Mechanical Simulation & Characterization** — it solicits "thermal and mechanical simulation and characterization … novel modeling techniques: multi-scale physics, model order reduction … model verification". 2nd **Packaging Technologies** — "advances in electrical/optical design and thermal solutions of 2.xD, TSV and 3D".
**Figure**: `assets/figures/ectc-abstract.pdf`.

---

## Title

**Duty-Cycle-Aware Thermal and Energy Budgeting for BEOL-Stacked SRAM on LLM Inference GPUs**

## Novelty paragraph (44 words)

We derive a BEOL-stacked SRAM tier's thermal and energy specification from a measured LLM-decode traffic ledger rather than an assumed power map, and show that the steady-state P/E screening rule and a single-node transient correction bracket the verified answer by 4× in opposite directions.

## Abstract (700 words)

Stacking SRAM in the back end of line (BEOL) above a GPU logic die adds fast memory capacity that reticle area cannot otherwise buy. Whether such a tier is worth building is usually screened with a steady-state relation, BW ≤ P_budget / E_bit. This work shows that for large-language-model (LLM) inference that rule is applied to a load it does not describe, and the verdict can be wrong in either direction by a factor of four.

We start from the workload rather than from an assumed power map. Using a measured decode traffic ledger for Llama-3.1-8B on a B200-class GPU (batch 8, 2048-token context; 4.5556 ms per step and 698.7 W package power, both measured), we account every byte the step moves. At a realizable design point — two BEOL tiers over 800 mm² per die, 4.22 GB — the tier supplies 24.0% of a 17.16 GB step demand. Delivered at the 19 TB/s fabric ceiling, that is a 217 µs burst once per 4.515 ms step: **a 4.80% duty cycle, not a steady load**. Decode, not prefill, is the thermal worst case; prefill duty is 0.08–0.41%.

We then compare three thermal treatments of the same device at a 20 W tier budget and 0.5 pJ/bit. The steady-state rule returns 5.0 TB/s, below the 6.40 TB/s effective HBM rate (a coefficient we validate causally on a Blackwell part, where two independent traffic knobs land on a measured bandwidth probe to 0.00% and 0.42%), and therefore condemns the tier outright. A single-node lumped RC correction — the natural first fix for a duty-cycled load — returns 76.9 TB/s and declares the tier fabric-bound with wide margin. A one-dimensional transient solver of the layered stack returns **18.6 TB/s**. That solver is verified against two analytic solutions (series resistance, 0.07% error; semi-infinite step response, 2.30%) and correlated against Ansys MAPDL 26.1 on the identical stack, which returns the same 18.6 TB/s and agrees to 0.02% on the peak fraction. The lumped model is optimistic by 4.16× because a thin, low-conductivity tier on a thick substrate is not one node: the tier heats locally within the 4.5 ms period even though the stack time constant is 6.8 ms. The verified ceiling lands essentially on the fabric limit, so thermal and interconnect are co-limiting rather than either dominating.

Two further results follow from the same model. First, the tier's peak temperature exceeds the logic junction by only 0.18–0.20 K and is almost independent of tier count, because the intervening BEOL is thin even at low conductivity. The binding device constraint is therefore not self-heating but the absolute junction temperature a BEOL device must tolerate while sitting on a 350 W/die logic plane. Second, a bottom-up energy budget — public 5 nm silicon SRAM array read energy of 17–55 fJ/bit, a BEOL-array energy ratio taken from the monolithically stackable gain-cell literature, periphery, and one vertical hop — gives an achievable band of **0.019–0.260 pJ/bit**, which clears the 0.391 pJ/bit bar set by the conservative steady-state rule at 20 W with 1.5× margin even at the pessimistic corner. The device model's own 0.5 pJ/bit example sits 1.9× above that corner.

A 3D model bounds what one dimension cannot see. Holding the same total tier power but concentrating it into a 100 µm patch raises the peak 502×, and the culprit is the 8 µm low-k BEOL directly beneath the tier, negligible under uniform power. Decode streams the resident weight set from every macro, so the uniform case is the operating point and the concentrated case is the bound.

A sensitivity ranking then points the remaining effort. The tier material's own thermal conductivity moves the ceiling by 0.3%; the BEOL around it moves it by 95%. The mitigations are correspondingly integration choices: a higher-conductivity interlayer and a 4 µm rather than 8 µm separation from the silicon recover 1.86× together. Stack geometry and materials are a stated parametric design study, not a fabricated device. The contribution is a reproducible path from a measured application traffic ledger to a packaging-actionable device specification, with a quantified warning about which reduced-order thermal model may be used to produce it.

---

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
