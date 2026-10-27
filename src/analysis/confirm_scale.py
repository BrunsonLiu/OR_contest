"""Scaling check: more items on the pick line, exact DP versus two rules.

One stockout at node 1, its substitute at node 2, and n other items at nodes
3..n+2. Travel is a line metric; the picker may move directly to any node.
The exact finite-horizon DP is compared with the same two deployable rules as
the four-node study. This is still a small-instance check, not a store policy.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import csv
import json
from functools import lru_cache

from src.runtime import results_root

EPS = 0.0


def positions_for(n_items):
    """Depot, stockout, substitute, then n other shelves on a line."""
    if n_items < 1:
        raise ValueError("至少需要一个其它商品")
    return [0.0, 1.0, 2.0] + [3.0 + 2.0 * index for index in range(n_items)]


def survival(dist, age):
    return sum(probability for delay, probability in dist.items() if delay > age)


def solve_exact(nodes, dist, reject_probability, window, deadline, values):
    """Exact expected value over (time, position, picked mask, status, age)."""
    if not nodes or nodes[0] != 0.0:
        raise ValueError("节点必须从仓库 0 开始")
    if len(nodes) < 4 or len(values) != len(nodes):
        raise ValueError("至少需要仓库、缺货货架、替代货架和一个其它商品，且 values 长度需匹配")
    if not dist or abs(sum(dist.values()) - 1.0) > 1e-9:
        raise ValueError("回复分布不合法")
    if not 0.0 <= reject_probability <= 1.0:
        raise ValueError("拒绝概率必须在 [0,1]")
    item_nodes = list(range(2, len(nodes)))  # substitute and other items
    bit = {node: index for index, node in enumerate(item_nodes)}
    full_mask = (1 << len(item_nodes)) - 1

    def delivered(mask):
        return sum(values[node] for node in item_nodes if mask & (1 << bit[node]))

    def normalise(t, pos, mask, status, age):
        if status == 0 and pos == 1:
            status, age = 1, 0
        if status == 1 and (t >= window or survival(dist, age) <= 1e-12):
            status, age = 3, 0
        return status, age

    def advance(t, pos, mask, status, age, destination):
        duration = abs(nodes[pos] - nodes[destination])
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
        status, age = normalise(t, pos, mask, status, age)
        best = delivered(mask)
        if mask != full_mask:
            for destination in (pos - 1, pos + 1):
                if not 0 <= destination < len(nodes):
                    continue
                if t + abs(nodes[pos] - nodes[destination]) <= deadline:
                    best = max(best, advance(t, pos, mask, status, age, destination))
        if pos == 2 and status == 2 and not (mask & (1 << bit[pos])):
            best = max(best, _best(t, pos, mask | (1 << bit[pos]), status, age))
        if pos >= 3 and not (mask & (1 << bit[pos])):
            best = max(best, _best(t, pos, mask | (1 << bit[pos]), status, age))
        return best

    return max(0.0, _best(0, 0, 0, 0, 0))


def _serve_nearest(t, pos, remaining, nodes, deadline, values):
    """Visit shelves in increasing distance order from the current position."""
    picked = 0.0
    while remaining:
        target = min(remaining, key=lambda node: abs(nodes[node] - nodes[pos]))
        arrival = t + abs(nodes[target] - nodes[pos])
        if arrival > deadline:
            break
        t, pos = arrival, target
        picked += values[target]
        remaining = [node for node in remaining if node != target]
    return t, pos, picked


def _suspend_trial(nodes, values, reply_delay, approved, window, deadline):
    t, pos = 1, 1  # at the stockout shelf, request sent
    remaining = list(range(3, len(nodes)))
    if reply_delay + 1.0 <= window:
        t = reply_delay + 1
        if approved and t + 1 <= deadline:
            t, pos = t + 1, 2
            picked_sub = values[2]
        else:
            picked_sub = 0
        t, _, picked_other = _serve_nearest(t, pos, remaining, nodes, deadline, values)
        return picked_sub + picked_other
    t = max(t, window)
    _, _, picked_other = _serve_nearest(t, pos, remaining, nodes, deadline, values)
    return picked_other


def _continue_trial(nodes, values, reply_delay, approved, window, deadline):
    t, pos = 1, 1
    remaining = list(range(3, len(nodes)))
    t, pos, picked_other = _serve_nearest(t, pos, remaining, nodes, deadline, values)
    arrival = t + abs(nodes[2] - nodes[pos])
    finish = max(arrival, reply_delay + 1.0)
    if approved and reply_delay + 1.0 <= window and finish <= deadline:
        return picked_other + values[2]
    return picked_other


def rule_value(trial, nodes, values, dist, reject_probability, window, deadline):
    total = 0.0
    for delay, probability in dist.items():
        total += probability * ((1.0 - reject_probability) * trial(nodes, values, delay, True, window, deadline)
                                + reject_probability * trial(nodes, values, delay, False, window, deadline))
    return total


def solve_rules(nodes, values, dist, reject_probability, window, deadline):
    return (rule_value(_suspend_trial, nodes, values, dist, reject_probability, window, deadline),
            rule_value(_continue_trial, nodes, values, dist, reject_probability, window, deadline))


def instance_grid():
    distributions = {"slow": {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}}
    rows = []
    for n_items in (1, 2, 3, 4):
        nodes = positions_for(n_items)
        last = nodes[-1]
        values = [0.0] * len(nodes)
        values[2] = 2.0  # the approved substitute is worth more than one ordinary item
        for node in range(3, len(nodes)):
            values[node] = 1.0
        for name, dist in distributions.items():
            for reject in (0.0, 0.2):
                for deadline in (last - 2, last - 1, last + 1):
                    for window in (deadline, deadline - 2):
                        rows.append({"n_items": n_items, "distribution": name, "dist": dist,
                                     "reject_probability": reject,
                                     "deadline": deadline, "window": window,
                                     "nodes": nodes, "values": values})
    return rows


def evaluate(row):
    full = solve_exact(row["nodes"], row["dist"], row["reject_probability"],
                       row["window"], row["deadline"], row["values"])
    suspend, keep = solve_rules(row["nodes"], row["values"], row["dist"],
                                row["reject_probability"], row["window"], row["deadline"])
    return {"n_items": row["n_items"], "distribution": row["distribution"],
            "reject_probability": row["reject_probability"],
            "deadline": row["deadline"], "window": row["window"],
            "items": row["n_items"] + 1, "full_value": full,
            "suspend_value": suspend, "continue_value": keep,
            "best_baseline": max(suspend, keep), "gap": full - max(suspend, keep)}


def main():
    rows = [evaluate(row) for row in instance_grid()]
    out_dir = results_root() / "confirm_scale"
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["n_items", "distribution", "reject_probability", "deadline", "window", "items",
              "full_value", "suspend_value", "continue_value", "best_baseline", "gap"]
    with (out_dir / "scale.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "instances": len(rows),
        "full_beats_best_baseline": sum(1 for row in rows if row["gap"] > 1e-9),
        "max_gap": max(row["gap"] for row in rows),
        "by_n_items": {
            str(n): {
                "instances": sum(1 for row in rows if row["n_items"] == n),
                "beats": sum(1 for row in rows if row["n_items"] == n and row["gap"] > 1e-9),
                "max_gap": max((row["gap"] for row in rows if row["n_items"] == n), default=0.0),
                "mean_gap": (sum(row["gap"] for row in rows if row["n_items"] == n)
                             / max(1, sum(1 for row in rows if row["n_items"] == n))),
            } for n in sorted({row["n_items"] for row in rows})},
        "by_reject_probability": {
            str(q): {
                "instances": sum(1 for row in rows if row["reject_probability"] == q),
                "beats": sum(1 for row in rows if row["reject_probability"] == q and row["gap"] > 1e-9),
            } for q in sorted({row["reject_probability"] for row in rows})},
        "scope": "line metric, one stockout, one substitute, 1-4 other items; exact DP and two rules",
        "limitations": [
            "Reply delay and rejection remain independent; no customer-choice correlation.",
            "Rules are greedy nearest-neighbour and are not tuned per instance.",
            "No real store data; the largest instance is still a small exact DP.",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("instances", "full_beats_best_baseline", "max_gap")},
                     ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
