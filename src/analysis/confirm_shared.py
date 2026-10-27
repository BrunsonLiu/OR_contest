"""Two orders competing for one substitute unit.

Nodes: depot, stockout A1, stockout A2, shared substitute S. Each order has a
value for the substitute; the single unit can satisfy only one. Replies are
independent. The exact DP is compared with a family of visit-order, waiting
and assignment rules. This is a small mechanism check, not a store policy.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import csv
import json
from functools import lru_cache
from itertools import product

from src.runtime import results_root

NODES = [(0.0, 0.0), (0.0, 1.0), (3.0, 0.0), (1.0, 0.0)]
A1, A2, S = 1, 2, 3
VALUES = {1: 2.0, 2: 3.0}
WAITS = (0, 1, 2, 3)


def distance(i, j):
    return abs(NODES[i][0] - NODES[j][0]) + abs(NODES[i][1] - NODES[j][1])


def survival(dist, age):
    return sum(probability for delay, probability in dist.items() if delay > age)


def _outcomes(t, d, status, age, dist, reject, window):
    if status != 1:
        return [(status, age, 1.0)]
    if t >= window:
        return [(3, 0, 1.0)]
    elapsed = min(t + d, window) - t
    denominator = survival(dist, age)
    if elapsed <= 0 or denominator <= 1e-12:
        return [(3, 0, 1.0)]
    no_reply = survival(dist, age + elapsed) / denominator
    reply = 1.0 - no_reply
    outcomes = []
    if reply > 0:
        outcomes.append((2, 0, (1.0 - reject) * reply))
        outcomes.append((3, 0, reject * reply))
    if no_reply > 0:
        if t + d < window:
            outcomes.append((1, age + elapsed, no_reply))
        else:
            outcomes.append((3, 0, no_reply))
    return outcomes


def solve_exact(dist, reject_probability, window, deadline):
    if not dist or abs(sum(dist.values()) - 1.0) > 1e-9:
        raise ValueError("回复分布不合法")
    if not 0.0 <= reject_probability <= 1.0 or window < 0 or deadline < 0:
        raise ValueError("拒绝概率或时间参数不合法")

    def normalise(t, pos, s1, a1, s2, a2):
        if pos == A1 and s1 == 0:
            s1, a1 = 1, 0
        if pos == A2 and s2 == 0:
            s2, a2 = 1, 0
        if s1 == 1 and (t >= window or survival(dist, a1) <= 1e-12):
            s1, a1 = 3, 0
        if s2 == 1 and (t >= window or survival(dist, a2) <= 1e-12):
            s2, a2 = 3, 0
        return s1, a1, s2, a2

    def advance(t, pos, s1, a1, s2, a2, assigned, destination, duration=None):
        duration = distance(pos, destination) if duration is None else duration
        t2 = t + duration
        total = 0.0
        for (ns1, na1, p1), (ns2, na2, p2) in product(_outcomes(t, duration, s1, a1, dist, reject_probability, window),
                                                      _outcomes(t, duration, s2, a2, dist, reject_probability, window)):
            if p1 * p2 > 0:
                total += p1 * p2 * _best(t2, destination, ns1, na1, ns2, na2, assigned)
        return total

    @lru_cache(maxsize=None)
    def _best(t, pos, s1, a1, s2, a2, assigned):
        s1, a1, s2, a2 = normalise(t, pos, s1, a1, s2, a2)
        best = VALUES[assigned] if assigned else 0.0
        if assigned == 0 and pos == S:
            approved = [order for order, status in ((1, s1), (2, s2)) if status == 2]
            if approved:
                order = max(approved, key=lambda item: VALUES[item])
                best = max(best, _best(t, pos, s1, a1, s2, a2, order))
        for destination in range(len(NODES)):
            if destination == pos:
                continue
            if t + distance(pos, destination) <= deadline:
                best = max(best, advance(t, pos, s1, a1, s2, a2, assigned, destination))
        if t < deadline:
            best = max(best, advance(t, pos, s1, a1, s2, a2, assigned, pos, duration=1.0))
        return best

    return max(0.0, _best(0, 0, 0, 0, 0, 0, 0))


def _scenarios(dist, reject_probability):
    for delay1, p1 in dist.items():
        for delay2, p2 in dist.items():
            for approve1 in (True, False):
                for approve2 in (True, False):
                    probability = (p1 * (1.0 - reject_probability if approve1 else reject_probability)
                                   * p2 * (1.0 - reject_probability if approve2 else reject_probability))
                    yield delay1, approve1, delay2, approve2, probability


def rule_value(dist, reject_probability, window, deadline, visit, order, wait_k, assignment):
    """visit: both, 1, or 2; order: 1 then 2, or 2 then 1; assignment: first or high."""
    total = 0.0
    if visit == "both":
        first, second = (A1, A2) if order == 1 else (A2, A1)
        shelves = (first, second)
    else:
        shelves = (A1,) if visit == "1" else (A2,)
    for delay1, approve1, delay2, approve2, probability in _scenarios(dist, reject_probability):
        replies = {A1: (delay1, approve1), A2: (delay2, approve2)}
        t, pos, request_times = 0, 0, {}
        for shelf in shelves:
            t += distance(pos, shelf)
            pos = shelf
            request_times[shelf] = t
            t += wait_k
        approved, reply_times = {}, {}
        for shelf in shelves:
            delay, approve = replies[shelf]
            reply_time = request_times[shelf] + delay
            approved[shelf] = approve and reply_time <= window
            reply_times[shelf] = reply_time
        t += distance(pos, S)
        if t <= deadline:
            candidates = [shelf for shelf in shelves if approved[shelf]]
            if candidates:
                if assignment == "high":
                    shelf = max(candidates, key=lambda item: VALUES[item])
                else:
                    shelf = min(candidates, key=lambda item: reply_times[item])
                total += probability * VALUES[shelf]
    return total


def family_values(dist, reject_probability, window, deadline):
    return {(visit, order, wait_k, assignment): rule_value(dist, reject_probability, window, deadline,
                                                           visit, order, wait_k, assignment)
            for visit in ("both", "1", "2") for order in (1, 2)
            for wait_k in WAITS for assignment in ("first", "high")}


def grid():
    dist = {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}
    return [{"deadline": deadline, "window": window, "reject_probability": reject, "dist": dist}
            for deadline in (6, 8, 10)
            for window in (deadline, deadline - 2)
            for reject in (0.0, 0.2)]


def evaluate(row):
    full = solve_exact(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    family = family_values(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    best_key, best_value = max(family.items(), key=lambda item: item[1])
    return {"deadline": row["deadline"], "window": row["window"],
            "reject_probability": row["reject_probability"], "full_value": full,
            "best_rule_value": best_value, "gap": full - best_value,
            "best_visit": best_key[0], "best_order": best_key[1],
            "best_wait": best_key[2], "best_assignment": best_key[3]}


def main():
    rows = [evaluate(row) for row in grid()]
    out_dir = results_root() / "confirm_shared"
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["deadline", "window", "reject_probability", "full_value", "best_rule_value",
              "gap", "best_visit", "best_order", "best_wait", "best_assignment"]
    with (out_dir / "shared.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "instances": len(rows),
        "full_beats_best_rule": sum(1 for row in rows if row["gap"] > 1e-9),
        "max_gap": max(row["gap"] for row in rows),
        "by_reject_probability": {
            str(q): {
                "instances": sum(1 for row in rows if row["reject_probability"] == q),
                "beats": sum(1 for row in rows if row["reject_probability"] == q and row["gap"] > 1e-9),
            } for q in sorted({row["reject_probability"] for row in rows})},
        "scope": "two orders, one shared substitute unit, four nodes; exact DP versus rules",
        "limitations": [
            "No other items; the only conflict is the shared substitute.",
            "Replies are independent; values are fixed.",
            "Rules are tuned per instance, which favours the baseline.",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("instances", "full_beats_best_rule", "max_gap")},
                     ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
