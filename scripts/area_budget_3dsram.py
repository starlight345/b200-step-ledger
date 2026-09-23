#!/usr/bin/env python3
"""Conditional 3D SRAM area budget, with macro geometry and explicit unknowns.

An 800 mm² logic die is a planning outline, NOT a validated memory-placement
mask. The area-only macro count is an upper bound until legal polygons, macro
halos, PDN, routing, thermal exclusions and controller footprints are known.
The optional speedup curves reuse the repository's median-step fit; they are
not TPOT p99 predictions or measured post-3D performance.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import hierarchy_model as H


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "sweep"
FIG = ROOT / "assets" / "figures"
OUT.mkdir(exist_ok=True, parents=True)
FIG.mkdir(exist_ok=True, parents=True)

DIES = 2
GROSS_DIE_MM2 = 800.0  # Existing B200-class planning assumption, not a signed-off outline.
MACROS = {
    "C3_BEOL_2.5x": {"width_um": 183, "height_um": 656},
    "C2_BEOL_uncompensated": {"width_um": 153, "height_um": 518},
}
BITS_PER_MACRO = 1_000_000  # canon: device_3dsram.bits_per_macro. Matches Minho's stated MB; 2^20-bit ambiguity remains.
READ_CAP_TBS = 15.0  # canon: design_point_axes.read_delivery_cap_TBs (slack_r1). Alternatives 17.7 (deck_320), 19.0 (via_L2_fabric).
USABLE_FRACTION = (1 - .12) * (1 - .05)  # ECC/tag, redundancy/BIST; already deducted once.
BYTES_PER_MACRO = BITS_PER_MACRO / 8 * USABLE_FRACTION


def macro_area(case: str) -> float:
    m = MACROS[case]
    return m["width_um"] * m["height_um"] / 1e6


def area_only_capacity(case: str, area_mm2: float, layers: int) -> dict:
    """Optimistic count; it knows area but not shape or global integration."""
    if not (-1e-8 <= area_mm2 <= GROSS_DIE_MM2 + 1e-8) or layers not in (1, 2):
        raise ValueError("net area must be within the planning die outline; layers=1/2")
    area_mm2 = min(max(area_mm2, 0), GROSS_DIE_MM2)
    n = math.floor(area_mm2 / macro_area(case))
    c_bytes = DIES * layers * n * BYTES_PER_MACRO
    return {"macros_per_die_per_tier": n, "capacity_GB_gpu": c_bytes / 1e9,
            "capacity_GiB_gpu": c_bytes / 2**30,
            "occupied_macro_area_mm2_per_die_per_tier": n * macro_area(case)}


def rectangular_grid_capacity(case: str, width_mm: float, height_mm: float,
                              layers: int) -> dict:
    """Nonoverlapping axis-aligned macro grid in one legal rectangular region.

    For more than one legal region, sum each region's grid count. This ignores
    controller, PDN and macro halo: those must be subtracted from legal regions.
    """
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("legal rectangle dimensions must be positive")
    w, h = MACROS[case]["width_um"] / 1000, MACROS[case]["height_um"] / 1000
    a = math.floor(width_mm / w) * math.floor(height_mm / h)
    b = math.floor(width_mm / h) * math.floor(height_mm / w)
    n = max(a, b)
    return {"macros_per_die_per_tier": n,
            "capacity_GB_gpu": DIES * layers * n * BYTES_PER_MACRO / 1e9,
            "occupied_macro_area_mm2_per_die_per_tier": n * macro_area(case),
            "legal_rectangle_mm2": width_mm * height_mm}


def fitted_speedup(capacity_GB_gpu: float, bound: str) -> float:
    # canon: design_point_axes.read_delivery_cap_TBs — the read cap is a scenario axis, not one value.
    # 15.0 = Slack r=1; 17.7 = deck 320 mm2 projection; 19.0 = via-L2 fabric (Chips and Cheese).
    # At >=400 mm2 the array raw exceeds every cap by >20x, so capacity scales with area but
    # delivered bandwidth does not. Default stays 15.0 for continuity with earlier tables.
    r = H.ladder_bounds("llama", 8, 2048, capacity_GB_gpu * 1e9, READ_CAP_TBS)  # canon: design_point_axes.read_delivery_cap_TBs (scenario slack_r1)
    return r["M1"][0 if bound == "serial" else 1]


def first_area_for_speedup(case: str, layers: int, target: float,
                           bound: str) -> float | None:
    """Minimum area-only macro footprint; actual physical area can be larger."""
    lo, hi = 0, math.floor(GROSS_DIE_MM2 / macro_area(case))
    if fitted_speedup(DIES * layers * hi * BYTES_PER_MACRO / 1e9, bound) < target:
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        cap = DIES * layers * mid * BYTES_PER_MACRO / 1e9
        if fitted_speedup(cap, bound) >= target:
            hi = mid
        else:
            lo = mid + 1
    return lo * macro_area(case)


def main() -> None:
    assumptions = {
        "gross_die_area_mm2_per_die_planning": GROSS_DIE_MM2,
        "dies_per_gpu": DIES,
        "bits_per_macro": BITS_PER_MACRO,
        "usable_fraction_after_ecc_tag_and_redundancy": USABLE_FRACTION,
        "placement_area_status": "unknown; input axis, not estimated from public die diagram",
        "area_only_capacity_status": "optimistic geometry upper bound for given net macro-placeable area",
        "speedup_status": "conditional median-step fit of existing hierarchy model; not p99",
        "unknown_exclusions": ["memory-tier outline and edge/seal keepout",
                               "HBM/NV-HBI/other interface keepout or routing constraints",
                               "global power/clock distribution and controller/bank area",
                               "macro halo and placement fragmentation",
                               "tier-specific thermal and vertical-interconnect exclusions"],
    }
    scenarios = []
    for area in (400, 500, 600, 700, 800):
        for case in MACROS:
            for layers in (1, 2):
                value = area_only_capacity(case, area, layers)
                scenarios.append({"net_area_mm2_per_die_per_tier": area,
                                  "unallocated_from_800_mm2": GROSS_DIE_MM2 - area,
                                  "case": case, "layers": layers, **value,
                                  "serial_speedup_at_assumed_15_tbps": fitted_speedup(value["capacity_GB_gpu"], "serial"),
                                  "overlap_speedup_at_assumed_15_tbps": fitted_speedup(value["capacity_GB_gpu"], "overlap")})
    thresholds = []
    for case in MACROS:
        for layers in (1, 2):
            for target in (1.05, 1.085):
                for bound in ("serial", "overlap"):
                    thresholds.append({"case": case, "layers": layers,
                                       "target_speedup": target, "bound": bound,
                                       "min_area_only_mm2_per_die_per_tier":
                                       first_area_for_speedup(case, layers, target, bound)})
    square = math.sqrt(GROSS_DIE_MM2)
    edge_examples = []
    for e in (0, .5, 1, 1.5, 2):
        a = max(0, (square - 2 * e)**2)
        edge_examples.append({"edge_band_width_mm_illustrative": e,
                              "remaining_area_mm2": a,
                              "C3_two_tier_capacity_GB_gpu_upper":
                              area_only_capacity("C3_BEOL_2.5x", a, 2)["capacity_GB_gpu"]})
    output = {"assumptions": assumptions, "macros": MACROS,
              "illustrative_area_scenarios": scenarios,
              "area_only_performance_thresholds": thresholds,
              "square_die_edge_band_illustrations": edge_examples,
              "edge_band_equivalent_to_600mm2_if_square_mm":
                  (square - math.sqrt(600)) / 2}
    (OUT / "area_budget_3dsram.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    with (OUT / "area_budget_3dsram.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(scenarios[0]))
        w.writeheader(); w.writerows(scenarios)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    xs = np.linspace(0, GROSS_DIE_MM2, 401)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.9), constrained_layout=True)
    colors = {"C3_BEOL_2.5x": "#155f84", "C2_BEOL_uncompensated": "#c1762f"}
    for case, color in colors.items():
        for layers, style in ((1, "--"), (2, "-")):
            caps = [area_only_capacity(case, float(a), layers)["capacity_GB_gpu"] for a in xs]
            axes[0].plot(xs, caps, color=color, linestyle=style, linewidth=2,
                         label=f"{case[:2]} · {layers} tier{'s' if layers == 2 else ''}")
    axes[0].set(xlim=(0, 800), ylim=(0, 4.6), xlabel="Net macro-placeable area per die per tier (mm²)",
                ylabel="Extra usable SRAM per GPU (GB, decimal)",
                title="A  Capacity upper bound from macro geometry")
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper left")
    axes[0].grid(alpha=.18)
    for case, color in colors.items():
        caps = np.array([area_only_capacity(case, float(a), 2)["capacity_GB_gpu"] for a in xs])
        ser = np.array([fitted_speedup(float(c), "serial") for c in caps])
        ovl = np.array([fitted_speedup(float(c), "overlap") for c in caps])
        axes[1].fill_between(xs, ser, ovl, color=color, alpha=.14)
        axes[1].plot(xs, ser, color=color, linewidth=2, label=f"{case[:2]} 2-tier serial")
        axes[1].plot(xs, ovl, color=color, linestyle="--", linewidth=1.5,
                     label=f"{case[:2]} 2-tier overlap")
    for ax in axes:
        ax.axvline(600, color="#6c7279", linewidth=1, linestyle=":")
        ax.text(608, ax.get_ylim()[1] * .94, "600: old input", color="#555e65", fontsize=8.5)
    for y in (1.05, 1.085):
        axes[1].axhline(y, color="#777", linewidth=.8, linestyle=":")
    axes[1].set(xlim=(0, 800), ylim=(1, 1.19),
                xlabel="Net macro-placeable area per die per tier (mm²)",
                ylabel="Conditional median-step speedup",
                title="B  Effect of area on the existing model (15 TB/s)")
    axes[1].legend(frameon=False, fontsize=8.2, loc="upper left", ncol=2)
    axes[1].grid(alpha=.18)
    fig.suptitle("800 mm² gross die is an outline; legal 3D macro area remains unmeasured",
                 fontsize=12, fontweight="bold")
    fig.savefig(FIG / "sram-area-budget.png", dpi=220, bbox_inches="tight")
    fig.savefig(FIG / "sram-area-budget.svg", bbox_inches="tight")
    plt.close(fig)
    print(json.dumps({"scenarios": scenarios, "thresholds": thresholds,
                      "edge_band_equivalent_to_600mm2_if_square_mm":
                      output["edge_band_equivalent_to_600mm2_if_square_mm"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
