import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

root = Path(__file__).resolve().parents[1]
data = json.loads((root / "assets/placement_sweep_summary.json").read_text())
out = root / "assets/figures"
out.mkdir(parents=True, exist_ok=True)

colors = {"persist_weight": "#d66f8f", "persist_kv": "#269e9d", "persist_state": "#318f61"}
labels = {"persist_weight": "persist weight", "persist_kv": "persist KV", "persist_state": "persist state"}
markers = {"persist_weight": "s", "persist_kv": "^", "persist_state": "o"}
sizes = [16, 32, 64, 96, 128, 256]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.5,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "pdf.fonttype": 42,
    "svg.fonttype": "none",
})

fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.95), sharex=True, sharey=True)
for ax, layers in zip(axes, [1, 36, 144]):
    cells = {c["size_mib_requested"]: c for c in data["cells"] if c["layers"] == layers}
    ax.axhspan(0.80, 1.0, color="#f7e9e9", alpha=0.72, zorder=0)
    ax.axvspan(79.1, 270, color="#f5eeee", alpha=0.6, zorder=0)
    ax.axhline(1.0, color="#343c45", lw=0.9, zorder=1)
    ax.axvline(42.2, color="#969da5", lw=0.8, ls=(0, (2, 2)), zorder=1)
    ax.axvline(79.1, color="#b26c55", lw=0.8, ls=(0, (4, 2)), zorder=1)
    for policy in ["persist_weight", "persist_kv", "persist_state"]:
        vals = [cells[s]["aggregate"][policy]["geomean_speedup"] for s in sizes]
        lo = [cells[s]["aggregate"][policy]["min_speedup"] for s in sizes]
        hi = [cells[s]["aggregate"][policy]["max_speedup"] for s in sizes]
        err = [[v - a for v, a in zip(vals, lo)], [b - v for v, b in zip(vals, hi)]]
        ax.errorbar(sizes, vals, yerr=err, color=colors[policy], marker=markers[policy],
                    ms=4.0 if policy != "persist_state" else 4.8,
                    lw=1.25 if policy != "persist_state" else 1.8,
                    elinewidth=0.55, capsize=1.5, alpha=0.96, zorder=3)
    ax.set_xscale("log", base=2)
    ax.set_xlim(13, 285)
    ax.set_ylim(0.80, 1.285)
    ax.set_xticks(sizes, [str(x) for x in sizes])
    ax.grid(axis="y", color="#d9dde1", lw=0.45)
    ax.set_title(f"{layers} layer slice" if layers == 1 else f"{layers} layer slices")
    ax.set_xlabel("Object size (MiB)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(16.5, 0.812, "slowdown", color="#8a4b4b", fontsize=7)
    if layers == 1:
        ax.set_ylabel("Speedup vs. matched default")
    if layers == 36:
        ax.annotate("state: 1.108×", xy=(64, cells[64]["aggregate"]["persist_state"]["geomean_speedup"]),
                    xytext=(50, 1.205), arrowprops=dict(arrowstyle="-", lw=.7, color="#318f61"),
                    color="#276f4c", fontsize=7.5)
        ax.annotate("31% coverage:\nall policies lose", xy=(256, cells[256]["aggregate"]["persist_state"]["geomean_speedup"]),
                    xytext=(125, .84), arrowprops=dict(arrowstyle="-", lw=.7, color="#8a4b4b"),
                    color="#8a4b4b", fontsize=7.2, ha="center")

legend = [Line2D([0], [0], color=colors[p], marker=markers[p], lw=1.6, label=labels[p]) for p in colors]
legend += [Line2D([0], [0], color="#969da5", lw=.8, ls=(0, (2, 2)), label="3 objects = L2"),
           Line2D([0], [0], color="#b26c55", lw=.8, ls=(0, (4, 2)), label="persisting limit")]
fig.legend(handles=legend, ncol=5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.015), columnspacing=1.0, handlelength=2.0)
fig.suptitle("B200 placement policy has an admission window", y=1.075, fontsize=12, fontweight="bold")
fig.text(0.5, -0.01, "Geometric mean of 18 matched order × repeat cells per marker; whiskers show min–max. 1,620 trials, 0 validation errors.", ha="center", fontsize=7.2, color="#4c545c")
fig.tight_layout(rect=[0, 0.055, 1, 0.93], w_pad=1.1)
for suffix, kwargs in [("svg", {}), ("pdf", {}), ("png", {"dpi": 300})]:
    fig.savefig(out / f"placement-policy-boundary.{suffix}", bbox_inches="tight", **kwargs)
plt.close(fig)
