import json, math, statistics, sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "placement.jsonl")
rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
trials = [x for x in rows if x.get("kind") == "trial"]
policies = ["reserved_normal", "persist_weight", "persist_kv", "persist_state"]
ratios = {p: [] for p in policies}
by_order = {}
for order in sorted({x["order"] for x in trials}):
    cells = [x for x in trials if x["order"] == order]
    med = {p: statistics.median(x["step_ms"] for x in cells if x["policy"] == p)
           for p in ["default"] + policies}
    by_order[order] = {p: med["default"] / med[p] for p in policies}
    for p in policies:
        ratios[p].extend(
            next(x["step_ms"] for x in cells if x["policy"] == "default" and x["pass"] == q) /
            next(x["step_ms"] for x in cells if x["policy"] == p and x["pass"] == q)
            for q in range(3)
        )

def gm(xs): return math.exp(sum(math.log(x) for x in xs) / len(xs))
summary = {
    "source": str(path),
    "trial_count": len(trials),
    "validation_errors": sum(x["validation_errors"] for x in trials),
    "orders": by_order,
    "aggregate": {p: {"geomean_speedup": gm(v), "median_speedup": statistics.median(v),
                       "min_speedup": min(v), "max_speedup": max(v),
                       "wins": sum(x > 1 for x in v), "cells": len(v)} for p, v in ratios.items()},
}
summary["ranking"] = sorted(policies, key=lambda p: summary["aggregate"][p]["geomean_speedup"], reverse=True)
print(json.dumps(summary, indent=2))
