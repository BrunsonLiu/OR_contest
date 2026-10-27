"""Stochastic policy comparison for the confirmation-instance problem.

The picker requests a substitute at the stockout shelf, keeps working while the
reply is pending, and can execute the substitute only if an approval arrives
before the order's confirmation window closes. Reply delay and outcome are
random. The exact finite-horizon DP is compared with two deployable rules:

* suspend: wait at the shelf until the reply, then continue;
* continue: walk to the other item first, then return to the substitute.

This is a small-instance mechanism and policy study, not a store policy and not
an algorithm for realistic order sizes.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import csv
import json
from functools import lru_cache
from pathlib import Path

from src.runtime import results_root

PICK_SUB = 1
PICK_OTHER = 2


def survival(dist, age):
    """P(reply delay > age) for a distribution keyed by positive integer delays."""
    return sum(probability for delay, probability in dist.items() if delay > age)


def _normalise(t, pos, mask, status, age, dist, window):
    if status == 0 and pos == 1:
        status, age = 1, 0
    if status == 1 and (t >= window or survival(dist, age) <= 1e-12):
        status, age = 3, 0
    return status, age


def solve_stochastic(other_position, dist, reject_probability, window, deadline,
                     value_substitute=1.0, value_other=1.0):
    """Exact expected-value DP over (time, position, picked mask, reply status, age)."""
    if not 0.0 <= reject_probability <= 1.0:
        raise ValueError("拒绝概率必须在 [0,1]")
    if not dist or any(delay < 1 or probability < 0 for delay, probability in dist.items()):
        raise ValueError("回复分布必须由正整数时延和非负概率组成")
    if abs(sum(dist.values()) - 1.0) > 1e-9:
        raise ValueError("回复分布概率之和必须为 1")
    if other_position < 3 or deadline < 0 or window < 0:
        raise ValueError("实例参数不合法")
    edges = {(0, 1): 1.0, (1, 0): 1.0, (1, 2): 1.0, (2, 1): 1.0,
             (2, other_position): float(other_position - 2), (other_position, 2): float(other_position - 2)}
    neighbours = {0: (1,), 1: (0, 2), 2: (1, other_position), other_position: (2,)}

    def delivered(mask):
        return (value_substitute if mask & PICK_SUB else 0.0) + (value_other if mask & PICK_OTHER else 0.0)

    def advance(t, pos, mask, status, age, duration, destination):
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
        approved = (1.0 - reject_probability) * reply
        rejected = reject_probability * reply
        value = 0.0
        if approved > 0:
            value += approved * _best(t2, destination, mask, 2, 0)
        if rejected > 0:
            value += rejected * _best(t2, destination, mask, 3, 0)
        if no_reply > 0:
            if t2 < window:
                value += no_reply * _best(t2, destination, mask, 1, age + elapsed)
            else:
                value += no_reply * _best(t2, destination, mask, 3, 0)
        return value

    @lru_cache(maxsize=None)
    def _best(t, pos, mask, status, age):
        status, age = _normalise(t, pos, mask, status, age, dist, window)
        best_value = delivered(mask)
        if t < deadline:
            best_value = max(best_value, advance(t, pos, mask, status, age, 1.0, pos))
        for nxt in neighbours[pos]:
            if t + edges[(pos, nxt)] <= deadline:
                best_value = max(best_value, advance(t, pos, mask, status, age, edges[(pos, nxt)], nxt))
        if pos == 2 and not (mask & PICK_SUB) and status == 2:
            best_value = max(best_value, _best(t, pos, mask | PICK_SUB, status, age))
        if pos == other_position and not (mask & PICK_OTHER):
            best_value = max(best_value, _best(t, pos, mask | PICK_OTHER, status, age))
        return best_value

    return max(-1.0, _best(0, 0, 0, 0, 0))


def suspend_value(other_position, dist, reject_probability, window, deadline,
                  value_substitute=1.0, value_other=1.0):
    """Wait at A until the reply (or the window), then act; no work while waiting."""
    def after_approval(delay):
        options = [0.0]
        if delay + 1 <= deadline:
            options.append(value_substitute)
        if delay + 1 + (other_position - 2) <= deadline:
            options.append(value_substitute + value_other)
        if delay + (other_position - 1) <= deadline:
            options.append(value_other)
        return max(options)

    total = 0.0
    for delay, probability in dist.items():
        if delay + 1 <= window:
            total += probability * (1.0 - reject_probability) * after_approval(delay)
            if delay + (other_position - 1) <= deadline:
                total += probability * reject_probability * value_other
        elif window + (other_position - 1) <= deadline:
            total += probability * value_other
    return total


def continue_value(other_position, dist, reject_probability, window, deadline,
                   value_substitute=1.0, value_other=1.0):
    """Walk to the other item first, then return to A' if the reply has arrived."""
    if other_position > deadline:
        approved = sum(probability for delay, probability in dist.items() if delay + 1 <= min(window, 2))
        return (1.0 - reject_probability) * approved * value_substitute
    value = value_other
    arrival = 2 * other_position - 2
    if arrival <= deadline:
        approved = sum(probability for delay, probability in dist.items()
                       if delay + 1 <= min(window, arrival))
        value += (1.0 - reject_probability) * approved * value_substitute
    return value


def grid():
    distributions = {
        "fast": {1: 0.5, 2: 0.3, 3: 0.2},
        "slow": {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2},
        "long": {3: 0.3, 4: 0.3, 5: 0.2, 6: 0.2},
    }
    rows = []
    for other_position in (8.0, 10.0, 12.0):
        for name, dist in distributions.items():
            for reject in (0.0, 0.2):
                for deadline in (10, 12, 14):
                    for window in sorted({deadline, max(deadline - 2, 1), max(deadline - 4, 1)}):
                        rows.append({"other_position": other_position, "distribution": name,
                                     "reject_probability": reject, "deadline": deadline,
                                     "window": window, "dist": dist})
    return rows


def evaluate(row):
    common = dict(other_position=row["other_position"], dist=row["dist"],
                  reject_probability=row["reject_probability"], window=row["window"],
                  deadline=row["deadline"])
    full = solve_stochastic(**common)
    suspend = suspend_value(**common)
    keep = continue_value(**common)
    return {**{key: row[key] for key in ("other_position", "distribution", "reject_probability",
                                         "deadline", "window")},
            "full_value": full, "suspend_value": suspend, "continue_value": keep,
            "best_baseline": max(suspend, keep), "gap": full - max(suspend, keep),
            "full_minus_suspend": full - suspend, "full_minus_continue": full - keep}


def summarise(rows):
    def count(predicate):
        return sum(1 for row in rows if predicate(row))
    return {
        "instances": len(rows),
        "full_beats_best_baseline": count(lambda r: r["gap"] > 1e-9),
        "full_beats_suspend": count(lambda r: r["full_minus_suspend"] > 1e-9),
        "full_beats_continue": count(lambda r: r["full_minus_continue"] > 1e-9),
        "max_gap": max((r["gap"] for r in rows), default=0.0),
        "by_distribution": {
            name: count(lambda r, n=name: r["distribution"] == n and r["gap"] > 1e-9)
            for name in sorted({r["distribution"] for r in rows})},
        "by_reject_probability": {
            str(q): count(lambda r, qq=q: r["reject_probability"] == qq and r["gap"] > 1e-9)
            for q in sorted({r["reject_probability"] for r in rows})},
        "scope": "small exact DP and two rules; no algorithm for realistic order sizes",
        "limitations": [
            "Line metric, one stockout, one substitute and one other item.",
            "Reply delay and rejection are independent; no customer-choice correlation.",
            "Rules are replayed under the same information and deadline; no real store data.",
        ],
    }


def main():
    rows = []
    for row in grid():
        rows.append(evaluate(row))
    out_dir = results_root() / "confirm_policy"
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["other_position", "distribution", "reject_probability", "deadline", "window",
              "full_value", "suspend_value", "continue_value", "best_baseline", "gap",
              "full_minus_suspend", "full_minus_continue"]
    with (out_dir / "policies.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = summarise(rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "full_beats_best_baseline", "full_beats_suspend",
                       "full_beats_continue", "max_gap")}, ensure_ascii=False))
    print("Exact DP and two rules only; no algorithm claim. Outputs:", out_dir)


if __name__ == "__main__":
    main()
