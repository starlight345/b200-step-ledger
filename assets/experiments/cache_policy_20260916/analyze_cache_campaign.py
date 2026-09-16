import json, math, statistics, sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "campaign.jsonl")
rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
dev = next(x for x in rows if x.get("kind") == "device")
tr = [x for x in rows if x.get("kind") == "trial"]
policies = ["reserved_normal", "persist_state_1", "persist_state_tuned"]
cells = []
for B, gap in sorted({(x["B"], x["pollution_mib_per_layer"]) for x in tr}):
    xs = [x for x in tr if x["B"] == B and x["pollution_mib_per_layer"] == gap]
    med = {p: statistics.median(x["step_ms"] for x in xs if x["policy"] == p)
           for p in ["default"] + policies}
    sample = xs[0]
    cells.append({
        "B": B, "pollution_mib_per_layer": gap,
        "state_bytes": sample["state_bytes"],
        "window_coverage": next(x["window_coverage"] for x in xs if x["policy"] == "persist_state_tuned"),
        "hit_ratio_hint": next(x["hit_ratio_hint"] for x in xs if x["policy"] == "persist_state_tuned"),
        "median_step_ms": med,
        "speedup_vs_default": {p: med["default"] / med[p] for p in policies},
    })

def gm(xs): return math.exp(sum(math.log(x) for x in xs) / len(xs))
aggregate = {}
for p in policies:
    vals = [c["speedup_vs_default"][p] for c in cells]
    aggregate[p] = {"geomean_speedup": gm(vals), "median_speedup": statistics.median(vals),
                    "min_speedup": min(vals), "max_speedup": max(vals),
                    "wins": sum(x > 1 for x in vals), "cells": len(vals)}
out = {"device": dev, "trial_count": len(tr),
       "validation_errors": sum(x["validation_errors"] for x in tr),
       "aggregate": aggregate, "cells": cells}
print(json.dumps(out, indent=2))
