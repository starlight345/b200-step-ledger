import json, math, re, statistics, sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
files = sorted(root.glob("placement_m*_l*.jsonl"), key=lambda p: tuple(map(int, re.search(r"m(\d+)_l(\d+)", p.name).groups())))
policies = ["reserved_normal", "persist_weight", "persist_kv", "persist_state"]

def gm(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs))

cells = []
for path in files:
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    if not rows or rows[0].get("kind") != "device":
        continue
    dev = rows[0]
    tr = [x for x in rows if x.get("kind") == "trial"]
    if len(tr) != 90:
        continue
    ratios = {p: [] for p in policies}
    for order in sorted({x["order"] for x in tr}):
        for run in range(3):
            xs = [x for x in tr if x["order"] == order and x["pass"] == run]
            base = next(x["step_ms"] for x in xs if x["policy"] == "default")
            for policy in policies:
                value = next(x["step_ms"] for x in xs if x["policy"] == policy)
                ratios[policy].append(base / value)
    size_mib, layers = map(int, re.search(r"m(\d+)_l(\d+)", path.name).groups())
    obj = dev["object_bytes"]
    aggregate = {p: {"geomean_speedup": gm(v), "median_speedup": statistics.median(v),
                     "min_speedup": min(v), "max_speedup": max(v),
                     "wins": sum(x > 1 for x in v), "cells": len(v)}
                 for p, v in ratios.items()}
    cells.append({
        "file": path.name, "size_mib_requested": size_mib, "layers": layers,
        "object_bytes": obj, "working_set_bytes": 3 * obj,
        "working_set_over_l2": 3 * obj / dev["l2_bytes"],
        "protected_fraction_of_target": min(1.0, dev["reserve_bytes"] / obj),
        "trial_count": len(tr),
        "validation_errors": sum(x["validation_errors"] for x in tr),
        "aggregate": aggregate,
        "ranking": sorted(policies, key=lambda p: aggregate[p]["geomean_speedup"], reverse=True),
    })

out = {
    "complete_files": len(cells),
    "expected_files": 18,
    "trial_count": sum(x["trial_count"] for x in cells),
    "validation_errors": sum(x["validation_errors"] for x in cells),
    "cells": cells,
}
print(json.dumps(out, indent=2))
