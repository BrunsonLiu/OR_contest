"""Cross-model checks for the stochastic confirmation-policy experiment.

Two independent properties are asserted:

1. with a point-mass reply and no rejection, the stochastic DP must reproduce
   every value of the deterministic instance file (different code path);
2. the exact DP cannot be below either deployable rule, and a wider window
   cannot lower its expected value under the same other parameters.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src.analysis.confirm_policy_compare import solve_stochastic


def main():
    parser = argparse.ArgumentParser(description="核对随机确认策略实验")
    parser.add_argument("policy_csv", type=Path)
    parser.add_argument("deterministic_csv", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    deterministic = list(csv.DictReader(args.deterministic_csv.open(encoding="utf-8")))
    point_mass_mismatches = []
    for row in deterministic:
        value = solve_stochastic(
            float(row["other_position"]), {int(row["reply_delay"]): 1.0}, 0.0,
            int(row["window"]), int(row["deadline"]),
            float(row["value_substitute"]), float(row["value_other"]))
        if abs(value - float(row["full_value"])) > 1e-9:
            point_mass_mismatches.append({"row": row, "stochastic": value})

    policies = list(csv.DictReader(args.policy_csv.open(encoding="utf-8")))
    baseline_below = []
    for row in policies:
        if float(row["full_value"]) + 1e-9 < float(row["best_baseline"]):
            baseline_below.append(row)

    groups = {}
    for row in policies:
        key = (row["other_position"], row["distribution"], row["reject_probability"], row["deadline"])
        groups.setdefault(key, []).append(row)
    window_violations = []
    for key, rows in groups.items():
        ordered = sorted(rows, key=lambda item: int(item["window"]))
        for earlier, later in zip(ordered, ordered[1:]):
            if float(later["full_value"]) + 1e-9 < float(earlier["full_value"]):
                window_violations.append({"group": key, "earlier": earlier, "later": later})

    report = {
        "deterministic_rows": len(deterministic),
        "point_mass_mismatches": len(point_mass_mismatches),
        "policy_rows": len(policies),
        "baseline_above_full": len(baseline_below),
        "window_monotonicity_violations": len(window_violations),
        "examples": point_mass_mismatches[:5] + baseline_below[:5] + window_violations[:5],
        "method": "point-mass equivalence, baseline dominance and window monotonicity; no reuse of the experiment CSV arithmetic",
        "scope": "line metric, independent reply delay and rejection, no customer-choice correlation",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("deterministic_rows", "point_mass_mismatches", "policy_rows",
                       "baseline_above_full", "window_monotonicity_violations")}, ensure_ascii=False))
    return 1 if (point_mass_mismatches or baseline_below or window_violations) else 0


if __name__ == "__main__":
    raise SystemExit(main())
