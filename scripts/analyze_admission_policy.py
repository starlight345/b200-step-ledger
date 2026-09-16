#!/usr/bin/env python3
"""Derive the admission-policy table from the immutable B200 sweep JSONL files."""

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path


def geometric_mean(values):
    return math.exp(sum(math.log(value) for value in values) / len(values))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "assets/experiments/placement_sweep_20260916",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    per_size = defaultdict(
        lambda: {
            "conditions": 0,
            "paired_cells": 0,
            "state_beats_default_cells": 0,
            "state_beats_weight_and_kv_cells": 0,
            "state_speedups": [],
            "condition_details": [],
        }
    )
    trial_count = validation_errors = 0
    raw_sha256 = {}

    paths = sorted(
        args.root.glob("placement_m*_l*.jsonl"),
        key=lambda p: tuple(map(int, re.search(r"m(\d+)_l(\d+)", p.name).groups())),
    )
    if len(paths) != 18:
        raise SystemExit(f"expected 18 JSONL files, found {len(paths)}")

    for path in paths:
        size_mib, layers = map(
            int, re.search(r"m(\d+)_l(\d+)", path.name).groups()
        )
        raw_sha256[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows = [json.loads(line) for line in path.read_text().splitlines() if line]
        device = rows[0]
        trials = [row for row in rows if row.get("kind") == "trial"]
        if device.get("kind") != "device" or len(trials) != 90:
            raise SystemExit(f"incomplete condition: {path}")

        condition_state_speedups = []
        state_beats_default = state_beats_weight_and_kv = 0
        for order in sorted({row["order"] for row in trials}):
            for run in range(3):
                cell = {
                    row["policy"]: row
                    for row in trials
                    if row["order"] == order and row["pass"] == run
                }
                if len(cell) != 5:
                    raise SystemExit(f"incomplete matched cell: {path} {order} {run}")
                default_ms = cell["default"]["step_ms"]
                state_ms = cell["persist_state"]["step_ms"]
                condition_state_speedups.append(default_ms / state_ms)
                state_beats_default += state_ms < default_ms
                state_beats_weight_and_kv += state_ms < min(
                    cell["persist_weight"]["step_ms"],
                    cell["persist_kv"]["step_ms"],
                )

        bucket = per_size[size_mib]
        bucket["conditions"] += 1
        bucket["paired_cells"] += 18
        bucket["state_beats_default_cells"] += state_beats_default
        bucket["state_beats_weight_and_kv_cells"] += state_beats_weight_and_kv
        bucket["state_speedups"].extend(condition_state_speedups)
        bucket["condition_details"].append(
            {
                "layers": layers,
                "state_geomean_speedup": geometric_mean(condition_state_speedups),
                "state_beats_default_cells": state_beats_default,
                "state_beats_weight_and_kv_cells": state_beats_weight_and_kv,
            }
        )
        trial_count += len(trials)
        validation_errors += sum(row["validation_errors"] for row in trials)

    decisions = {
        16: "no_clear_forced_placement_benefit",
        32: "admit_state_first",
        64: "admit_state_first",
        96: "admit_state_first_under_this_proxy",
        128: "granularity_sensitive_remeasure",
        256: "reject_forced_placement",
    }
    sizes = []
    persisting_bytes = 82903040
    for size_mib in sorted(per_size):
        bucket = per_size[size_mib]
        sizes.append(
            {
                "size_mib": size_mib,
                "protected_fraction": min(
                    1.0, persisting_bytes / (size_mib * 2**20)
                ),
                "conditions": bucket["conditions"],
                "paired_cells": bucket["paired_cells"],
                "state_geomean_speedup": geometric_mean(bucket.pop("state_speedups")),
                "state_beats_default_cells": bucket["state_beats_default_cells"],
                "state_beats_weight_and_kv_cells": bucket[
                    "state_beats_weight_and_kv_cells"
                ],
                "decision": decisions[size_mib],
                "condition_details": sorted(
                    bucket["condition_details"], key=lambda x: x["layers"]
                ),
            }
        )

    result = {
        "schema_version": 1,
        "source": "B200 persisting-L2 placement proxy",
        "complete_conditions": len(paths),
        "trial_count": trial_count,
        "validation_errors": validation_errors,
        "paired_cell_definition": "one access order and one rotated policy pass; five policies are matched within the cell",
        "independence_caveat": "Counts are descriptive robustness checks over fixed orders and repetitions, not independent samples from all LLM workloads.",
        "sizes": sizes,
        "raw_sha256": raw_sha256,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
