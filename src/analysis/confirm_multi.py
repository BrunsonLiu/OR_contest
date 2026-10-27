"""Two concurrent stockouts: exact DP versus two deployable rules.

Nodes on a line: depot 0, stockout A1 at 1, substitute S1 at 2, stockout A2
at 3, substitute S2 at 4, one other item at 5. Each stockout has its own
reply delay and rejection outcome. The exact finite-horizon DP tracks two
pending requests independently; the rules either wait at each shelf or keep
walking and return after the last item. This is still a small exact instance.
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

NODES = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
A1, S1, A2, S2, OTHER = 1, 2, 3, 4, 5
VALUES = {S1: 2.0, S2: 2.0, OTHER: 1.0}
ITEMS = [S1, S2, OTHER]
BIT = {node: index for index, node in enumerate(ITEMS)}


def survival(dist, age):
    return sum(probability for delay, probability in dist.items() if delay > age)


def _request_outcomes(t, d, status, age, dist, reject, window):
    """Distribution over (status, age) after duration d for one pending request."""
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
    def delivered(mask):
        return sum(VALUES[node] for node in ITEMS if mask & (1 << BIT[node]))

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

    def advance(t, pos, mask, s1, a1, s2, a2, destination):
        duration = abs(NODES[pos] - NODES[destination])
        t2 = t + duration
        outcomes1 = _request_outcomes(t, duration, s1, a1, dist, reject_probability, window)
        outcomes2 = _request_outcomes(t, duration, s2, a2, dist, reject_probability, window)
        total = 0.0
        for (ns1, na1, p1), (ns2, na2, p2) in product(outcomes1, outcomes2):
            if p1 * p2 > 0:
                total += p1 * p2 * _best(t2, destination, mask, ns1, na1, ns2, na2)
        return total

    @lru_cache(maxsize=None)
    def _best(t, pos, mask, s1, a1, s2, a2):
        s1, a1, s2, a2 = normalise(t, pos, s1, a1, s2, a2)
        best = delivered(mask)
        for destination in (pos - 1, pos + 1):
            if not 0 <= destination < len(NODES):
                continue
            if t + abs(NODES[pos] - NODES[destination]) <= deadline:
                best = max(best, advance(t, pos, mask, s1, a1, s2, a2, destination))
        if pos == S1 and s1 == 2 and not (mask & (1 << BIT[S1])):
            best = max(best, _best(t, pos, mask | (1 << BIT[S1]), s1, a1, s2, a2))
        if pos == S2 and s2 == 2 and not (mask & (1 << BIT[S2])):
            best = max(best, _best(t, pos, mask | (1 << BIT[S2]), s1, a1, s2, a2))
        if pos == OTHER and not (mask & (1 << BIT[OTHER])):
            best = max(best, _best(t, pos, mask | (1 << BIT[OTHER]), s1, a1, s2, a2))
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


def wait_each_value(dist, reject_probability, window, deadline):
    """At each stockout, wait for its reply (or the window), then continue."""
    total = 0.0
    for delay1, approve1, delay2, approve2, probability in _scenarios(dist, reject_probability):
        t, pos, value = 1, A1, 0.0
        request1 = 1
        if request1 + delay1 <= window:
            t = request1 + delay1
            if approve1 and t + 1 <= deadline:
                t, pos = t + 1, S1
                value += VALUES[S1]
        else:
            t = max(t, window)
        t += abs(NODES[A2] - NODES[pos])
        pos = A2
        if t > deadline:
            total += probability * value
            continue
        request2 = t
        if request2 + delay2 <= window:
            t = request2 + delay2
            if approve2 and t + 1 <= deadline:
                t, pos = t + 1, S2
                value += VALUES[S2]
        else:
            t = max(t, window)
        t += abs(NODES[OTHER] - NODES[pos])
        if t <= deadline:
            value += VALUES[OTHER]
        total += probability * value
    return total


def continue_all_value(dist, reject_probability, window, deadline):
    """Request at both shelves, walk to the last item, then return to substitutes."""
    total = 0.0
    for delay1, approve1, delay2, approve2, probability in _scenarios(dist, reject_probability):
        t, pos, value = 1, A1, 0.0
        t += abs(NODES[A2] - NODES[pos])
        pos = A2
        if t > deadline:
            total += probability * value
            continue
        request2 = t
        t += abs(NODES[OTHER] - NODES[pos])
        pos = OTHER
        if t <= deadline:
            value += VALUES[OTHER]
        for target, request_time, delay, approve in ((S2, request2, delay2, approve2),
                                                     (S1, 1, delay1, approve1)):
            arrival = t + abs(NODES[target] - NODES[pos])
            reply_time = request_time + delay
            finish = max(arrival, reply_time)
            if approve and reply_time <= window and finish <= deadline:
                value += VALUES[target]
                t, pos = finish, target
        total += probability * value
    return total


def grid():
    dist = {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}
    rows = []
    for deadline in (8, 9, 10):
        for window in (deadline, deadline - 2):
            for reject in (0.0, 0.2):
                rows.append({"deadline": deadline, "window": window,
                             "reject_probability": reject, "dist": dist})
    return rows


def evaluate(row):
    full = solve_exact(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    wait = wait_each_value(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    keep = continue_all_value(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    return {"deadline": row["deadline"], "window": row["window"],
            "reject_probability": row["reject_probability"],
            "full_value": full, "wait_value": wait, "continue_value": keep,
            "best_baseline": max(wait, keep), "gap": full - max(wait, keep),
            "full_minus_wait": full - wait, "full_minus_continue": full - keep}


def main():
    rows = [evaluate(row) for row in grid()]
    out_dir = results_root() / "confirm_multi"
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["deadline", "window", "reject_probability", "full_value", "wait_value",
              "continue_value", "best_baseline", "gap", "full_minus_wait", "full_minus_continue"]
    with (out_dir / "multi.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "instances": len(rows),
        "full_beats_best_baseline": sum(1 for row in rows if row["gap"] > 1e-9),
        "max_gap": max(row["gap"] for row in rows),
        "by_reject_probability": {
            str(q): {
                "instances": sum(1 for row in rows if row["reject_probability"] == q),
                "beats": sum(1 for row in rows if row["reject_probability"] == q and row["gap"] > 1e-9),
            } for q in sorted({row["reject_probability"] for row in rows})},
        "scope": "two stockouts and two pending requests on a six-node line; exact DP and two rules",
        "limitations": [
            "Independent replies across the two requests; no shared customer or basket effects.",
            "One other item only; the rules are not tuned.",
            "Exact DP only; this is not a scalable algorithm and has no real store data.",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("instances", "full_beats_best_baseline", "max_gap")},
                     ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
