"""Independent combinatorial check for the confirmation-instance DP.

The DP memoises states; this script enumerates the only visit orders that can
be optimal on a line with one stockout shelf and two items. It does not import
the DP. Any disagreement is a failure, not a tolerance.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def brute_value(other_position: float, reply_delay: int, window: int, deadline: int,
                value_substitute: float, value_other: float):
    """Best (value, finish) over visit orders A->A'->B, A->B->A', A->A', A->B.

    The request is sent on first arrival at A; sending later is weakly worse.
    Waiting is only useful at A' until the reply arrives.
    """
    if other_position < 3:
        raise ValueError("other_position 必须不小于 3")
    availability = 1 + reply_delay
    available = availability <= window
    candidates = []

    # A only.
    candidates.append((0.0, 1.0))

    if available:
        # A -> A' (wait if early).
        finish = max(2.0, float(availability))
        if finish <= deadline:
            candidates.append((value_substitute, finish))
        # A -> A' -> B.
        finish_sub_then_other = finish + (other_position - 2)
        if finish_sub_then_other <= deadline:
            candidates.append((value_substitute + value_other, finish_sub_then_other))
        # A -> B -> A' (reply may already be available).
        finish_other = other_position
        if finish_other <= deadline:
            candidates.append((value_other, finish_other))
            finish_back = max(finish_other + (other_position - 2), float(availability))
            if finish_back <= deadline:
                candidates.append((value_substitute + value_other, finish_back))
    else:
        # A -> B only.
        if other_position <= deadline:
            candidates.append((value_other, float(other_position)))

    # Pick the best value, then the earliest finish.
    value, finish = max(candidates, key=lambda item: (item[0], -item[1]))
    return value, finish


def main():
    parser = argparse.ArgumentParser(description="独立核对确认实例的精确 DP")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.csv_path.open(encoding="utf-8")))
    mismatches = []
    for row in rows:
        value, finish = brute_value(
            float(row["other_position"]), int(row["reply_delay"]), int(row["window"]),
            int(row["deadline"]), float(row["value_substitute"]), float(row["value_other"]))
        if value != float(row["full_value"]) or float(row["full_finish"]) > finish + 1e-9:
            mismatches.append({
                "row": {key: row[key] for key in
                        ("other_position", "reply_delay", "window", "deadline",
                         "value_substitute", "value_other")},
                "dp": [float(row["full_value"]), float(row["full_finish"])],
                "brute": [value, finish],
            })
    report = {
        "checked": len(rows),
        "mismatches": len(mismatches),
        "first_mismatches": mismatches[:10],
        "method": "independent enumeration of visit orders; no import of the DP",
        "scope": "line metric, one stockout, one substitute, one other item, deterministic reply",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("checked", "mismatches")}, ensure_ascii=False))
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
