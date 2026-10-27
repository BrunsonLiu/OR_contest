"""Two-dimensional confirmation check with a fair skip option.

A 4x4 grid: depot (0,0), stockout A (0,1), off-route substitute S (3,3), and
three other items. Every rule may skip A; the threshold rule decides by the
expected substitute value per extra travel minute. The exact DP is compared
with the strongest of wait, continue and the best threshold in the family.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import csv
import json
from functools import lru_cache

from src.runtime import results_root

NODES = [(0.0, 0.0), (0.0, 1.0), (3.0, 3.0), (2.0, 0.0), (3.0, 1.0), (2.0, 2.0)]
A, S = 1, 2
OTHERS = [3, 4, 5]
VALUES = {S: 2.0, 3: 1.0, 4: 1.0, 5: 1.0}
BIT = {node: index for index, node in enumerate([S] + OTHERS)}
THRESHOLDS = (0.0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0)


def distance(i, j):
    return abs(NODES[i][0] - NODES[j][0]) + abs(NODES[i][1] - NODES[j][1])


def survival(dist, age):
    return sum(probability for delay, probability in dist.items() if delay > age)


def solve_exact(dist, reject_probability, window, deadline):
    if not dist or abs(sum(dist.values()) - 1.0) > 1e-9:
        raise ValueError("回复分布不合法")
    if not 0.0 <= reject_probability <= 1.0 or window < 0 or deadline < 0:
        raise ValueError("拒绝概率或时间参数不合法")

    def delivered(mask):
        return sum(VALUES[node] for node in [S] + OTHERS if mask & (1 << BIT[node]))

    def normalise(t, pos, status, age):
        if pos == A and status == 0:
            status, age = 1, 0
        if status == 1 and (t >= window or survival(dist, age) <= 1e-12):
            status, age = 3, 0
        return status, age

    def advance(t, pos, mask, status, age, destination):
        duration = distance(pos, destination)
        t2 = t + duration
        if status != 1:
            return _best(t2, destination, mask, status, 0)
        if t >= window:
            return _best(t2, destination, mask, 3, 0)
        elapsed = min(t2, window) - t
        denominator = survival(dist, age)
        if elapsed <= 0 or denominator <= 1e-12:
            return _best(t2, destination, mask, 3, 0)
        no_reply = survival(dist, age + elapsed) / denominator
        reply = 1.0 - no_reply
        value = 0.0
        if reply > 0:
            value += (1.0 - reject_probability) * reply * _best(t2, destination, mask, 2, 0)
            value += reject_probability * reply * _best(t2, destination, mask, 3, 0)
        if no_reply > 0:
            if t2 < window:
                value += no_reply * _best(t2, destination, mask, 1, age + elapsed)
            else:
                value += no_reply * _best(t2, destination, mask, 3, 0)
        return value

    @lru_cache(maxsize=None)
    def _best(t, pos, mask, status, age):
        status, age = normalise(t, pos, status, age)
        best = delivered(mask)
        for destination in range(len(NODES)):
            if destination == pos:
                continue
            if t + distance(pos, destination) <= deadline:
                best = max(best, advance(t, pos, mask, status, age, destination))
        if pos == S and status == 2 and not (mask & (1 << BIT[S])):
            best = max(best, _best(t, pos, mask | (1 << BIT[S]), status, age))
        if pos in OTHERS and not (mask & (1 << BIT[pos])):
            best = max(best, _best(t, pos, mask | (1 << BIT[pos]), status, age))
        return best

    return max(0.0, _best(0, 0, 0, 0, 0))


def _nearest_value(t, pos, remaining, deadline):
    value = 0.0
    while remaining:
        target = min(remaining, key=lambda node: distance(pos, node))
        arrival = t + distance(pos, target)
        if arrival > deadline:
            break
        t, pos = arrival, target
        value += VALUES[target]
        remaining = [node for node in remaining if node != target]
    return t, pos, value


def _scenarios(dist, reject_probability):
    for delay, probability in dist.items():
        for approved in (True, False):
            yield delay, approved, probability * ((1.0 - reject_probability) if approved else reject_probability)


def _visit_A_then_others(dist, reject_probability, window, deadline):
    """Request at A, serve other items by nearest neighbour, then return to S."""
    total = 0.0
    for delay, approved, probability in _scenarios(dist, reject_probability):
        t, pos = distance(0, A), A
        request = t
        t, pos, value = _nearest_value(t, pos, list(OTHERS), deadline)
        arrival = t + distance(pos, S)
        finish = max(arrival, request + delay)
        if approved and request + delay <= window and finish <= deadline:
            value += VALUES[S]
        total += probability * value
    return total


def _skip_A_value(dist, reject_probability, window, deadline):
    _, _, value = _nearest_value(0, 0, list(OTHERS), deadline)
    return value


def wait_value(dist, reject_probability, window, deadline):
    total = 0.0
    for delay, approved, probability in _scenarios(dist, reject_probability):
        t, pos, value = distance(0, A), A, 0.0
        request = t
        if request + delay <= window:
            t = request + delay
            if approved and t + distance(A, S) <= deadline:
                t, pos = t + distance(A, S), S
                value += VALUES[S]
        else:
            t = max(t, window)
        _, _, others = _nearest_value(t, pos, list(OTHERS), deadline)
        total += probability * (value + others)
    return total


def threshold_value(dist, reject_probability, window, deadline, threshold):
    """Visit A only when expected substitute value per extra travel minute is enough."""
    arrival = distance(0, A)
    expected_reply = sum(probability for delay, probability in dist.items() if arrival + delay <= window)
    expected_sub = VALUES[S] * (1.0 - reject_probability) * expected_reply
    nearest_other_from_depot = min(distance(0, node) for node in OTHERS)
    detour = arrival + min(distance(A, node) for node in OTHERS) - nearest_other_from_depot
    if detour <= 0 or expected_sub / detour < threshold:
        return _skip_A_value(dist, reject_probability, window, deadline)
    return _visit_A_then_others(dist, reject_probability, window, deadline)


def grid():
    dist = {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}
    return [{"deadline": deadline, "window": window, "reject_probability": reject, "dist": dist}
            for deadline in (6, 7, 8, 10)
            for window in (deadline, deadline - 2)
            for reject in (0.0, 0.2)]


def evaluate(row):
    full = solve_exact(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    wait = wait_value(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    keep = _visit_A_then_others(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    skip = _skip_A_value(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    thresholds = {str(threshold): threshold_value(row["dist"], row["reject_probability"], row["window"],
                                                   row["deadline"], threshold)
                  for threshold in THRESHOLDS}
    best_threshold = max(thresholds.values())
    best_rule = max(wait, keep, best_threshold)
    return {"deadline": row["deadline"], "window": row["window"],
            "reject_probability": row["reject_probability"], "full_value": full,
            "wait_value": wait, "continue_value": keep, "skip_value": skip,
            "best_threshold_value": best_threshold, "best_rule": best_rule,
            "gap_vs_best_rule": full - best_rule,
            "gap_vs_wait": full - wait, "gap_vs_continue": full - keep}


def main():
    rows = [evaluate(row) for row in grid()]
    out_dir = results_root() / "confirm_grid"
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["deadline", "window", "reject_probability", "full_value", "wait_value",
              "continue_value", "skip_value", "best_threshold_value", "best_rule",
              "gap_vs_best_rule", "gap_vs_wait", "gap_vs_continue"]
    with (out_dir / "grid.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "instances": len(rows),
        "full_beats_best_rule": sum(1 for row in rows if row["gap_vs_best_rule"] > 1e-9),
        "max_gap_vs_best_rule": max(row["gap_vs_best_rule"] for row in rows),
        "by_reject_probability": {
            str(q): {
                "instances": sum(1 for row in rows if row["reject_probability"] == q),
                "beats": sum(1 for row in rows if row["reject_probability"] == q
                             and row["gap_vs_best_rule"] > 1e-9),
            } for q in sorted({row["reject_probability"] for row in rows})},
        "scope": "one stockout and an off-route substitute on a 4x4 grid; exact DP versus rules with a skip option",
        "limitations": [
            "One stockout; three other items; Manhattan distances and direct moves.",
            "The threshold family is tuned on the same instances, which favours the baseline.",
            "Exact DP only; no real store data.",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "full_beats_best_rule", "max_gap_vs_best_rule")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
