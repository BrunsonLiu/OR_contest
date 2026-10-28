"""Same-neighbourhood comparison for the cold-chain LRP kill test.

Both initial solutions (repaired sequential and joint insertion) are improved
by the same local search: store relocation, store swap, 2-opt, and opening or
closing an RDC. If the final costs converge, the LRP line has no algorithm gap.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
import random

from src.runtime import results_root

CDC = (400.0, 400.0)
RDCS = [(150.0, 150.0), (150.0, 650.0), (650.0, 150.0), (650.0, 650.0)]
N_STORES = 12
CAPACITY = 3
OPEN_COST = 400.0
VEHICLE_COST = 80.0
PROCESSING = 1.0
LAST_KM = 1.45
TRUNK_KM = 0.9
ON_TIME = 600.0
LOSS_START = 500.0
LATE_SHARE = 0.05
EPS = 1e-7


def make_instance(seed):
    rng = random.Random(seed)
    stores = [(rng.uniform(0, 800), rng.uniform(0, 800), rng.uniform(0.05, 0.08)) for _ in range(N_STORES - 1)]
    stores.append((760.0, 760.0, 0.03))
    total = sum(w for _, _, w in stores)
    return [(x, y, w / total) for x, y, w in stores]


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def point_of(server):
    return CDC if server == -1 else RDCS[server]


def route_cost(point, order, stores):
    t = 0.0
    previous = point
    cost = VEHICLE_COST
    for index in order:
        x, y, w = stores[index]
        leg = distance(previous, (x, y))
        t += leg
        cost += LAST_KM * leg * w
        if leg > LOSS_START:
            cost += 0.2 * (leg - LOSS_START) ** 2 * w
        previous = (x, y)
    return cost


def evaluate(routes, stores):
    total = 0.0
    late = 0.0
    for server, route_list in routes.items():
        if not route_list:
            continue
        point = point_of(server)
        weight = 0.0
        for order in route_list:
            total += route_cost(point, order, stores)
            t = 0.0
            previous = point
            for index in order:
                x, y, w = stores[index]
                t += distance(previous, (x, y))
                if t > ON_TIME:
                    late += w
                previous = (x, y)
                weight += w
        if server >= 0:
            total += OPEN_COST + TRUNK_KM * distance(CDC, RDCS[server]) * weight
        total += (1.0 if server == -1 else 2.0) * PROCESSING * weight
    return total, late


def feasible(routes, stores):
    return evaluate(routes, stores)[1] <= LATE_SHARE + 1e-9


def clean(routes):
    return {server: [order[:] for order in route_list if order] for server, route_list in routes.items()
            if any(route_list)}


def build_routes(point, indices, stores):
    routes = [[i] for i in indices]
    savings = []
    for a in range(len(indices)):
        for b in range(a + 1, len(indices)):
            i, j = indices[a], indices[b]
            saving = (distance(point, stores[i][:2]) + distance(point, stores[j][:2])
                      - distance(stores[i][:2], stores[j][:2]))
            savings.append((saving, i, j))
    savings.sort(reverse=True)
    for _, i, j in savings:
        route_i = next((r for r in routes if i in r), None)
        route_j = next((r for r in routes if j in r), None)
        if route_i is None or route_j is None or route_i is route_j:
            continue
        if len(route_i) + len(route_j) > CAPACITY:
            continue
        if route_i[-1] == i and route_j[0] == j:
            merged = route_i + route_j
        elif route_i[0] == i and route_j[-1] == j:
            merged = route_j + route_i
        elif route_i[-1] == i and route_j[-1] == j:
            merged = route_i + route_j[::-1]
        elif route_i[0] == i and route_j[0] == j:
            merged = route_i[::-1] + route_j
        else:
            continue
        routes.remove(route_i)
        routes.remove(route_j)
        routes.append(merged)
    ordered = []
    for route in routes:
        remaining = route[:]
        current = point
        order = []
        while remaining:
            nxt = min(remaining, key=lambda idx: distance(current, stores[idx][:2]))
            order.append(nxt)
            current = stores[nxt][:2]
            remaining.remove(nxt)
        ordered.append(order)
    return ordered


def direct_cost(server, index, stores):
    x, y, w = stores[index]
    processing = 1.0 if server == -1 else 2.0
    return LAST_KM * distance(point_of(server), (x, y)) * w + processing * PROCESSING * w


def sequential(stores):
    best = None
    for mask in range(1 << len(RDCS)):
        open_set = [rdc for rdc in range(len(RDCS)) if mask & (1 << rdc)]
        assignment = []
        total = 0.0
        weight = {rdc: 0.0 for rdc in open_set}
        for index in range(len(stores)):
            options = [(-1, direct_cost(-1, index, stores))]
            options += [(rdc, direct_cost(rdc, index, stores)) for rdc in open_set]
            server, cost = min(options, key=lambda item: item[1])
            assignment.append(server)
            total += cost
            if server >= 0:
                weight[server] += stores[index][2]
        for rdc in open_set:
            total += OPEN_COST + TRUNK_KM * distance(CDC, RDCS[rdc]) * weight[rdc]
        late_direct = 0.0
        for index, server in enumerate(assignment):
            if distance(point_of(server), stores[index][:2]) > ON_TIME:
                late_direct += stores[index][2]
        if late_direct > LATE_SHARE + 1e-9:
            continue
        if best is None or total < best[0]:
            best = (total, assignment)
    assignment = best[1]
    routes = {}
    for server in set(assignment):
        indices = [index for index, chosen in enumerate(assignment) if chosen == server]
        routes[server] = build_routes(point_of(server), indices, stores)
    return routes


def repair(routes, stores, max_iterations=30):
    routes = clean(routes)
    for _ in range(max_iterations):
        if feasible(routes, stores):
            return routes
        _, current_late = evaluate(routes, stores)
        late = {}
        for server, route_list in routes.items():
            point = point_of(server)
            for order in route_list:
                t = 0.0
                previous = point
                for index in order:
                    x, y, w = stores[index]
                    t += distance(previous, (x, y))
                    if t > ON_TIME:
                        late[index] = w
                    previous = (x, y)
        store = max(late, key=lambda index: late[index])
        current = next(server for server, route_list in routes.items()
                       if any(store in order for order in route_list))
        best = None
        for server in [-1] + list(range(len(RDCS))):
            if server == current:
                continue
            base = clean(routes)
            for order in base.get(current, []):
                if store in order:
                    order.remove(store)
            base = clean(base)
            options = []
            trial = clean(base)
            trial.setdefault(server, []).append([store])
            options.append(trial)
            for route_index, order in enumerate(base.get(server, [])):
                if len(order) < CAPACITY:
                    trial = clean(base)
                    trial[server][route_index] = [store] + order
                    options.append(trial)
            trial = clean(base)
            point = point_of(server)
            indices = [index for order in base.get(server, []) for index in order] + [store]
            trial[server] = build_routes(point, indices, stores)
            options.append(trial)
            for candidate in options:
                new_late = evaluate(candidate, stores)[1]
                if new_late < current_late - 1e-9:
                    cost = evaluate(candidate, stores)[0]
                    if best is None or (new_late, cost) < (best[0], best[1]):
                        best = (new_late, cost, candidate)
        if best is None:
            return None
        routes = best[2]
    return None


def insert_order(order, index, point, stores):
    best = None
    for position in range(len(order) + 1):
        candidate = order[:position] + [index] + order[position:]
        cost = route_cost(point, candidate, stores)
        if best is None or cost < best[0]:
            best = (cost, candidate)
    return best


def joint(stores):
    order = sorted(range(len(stores)), key=lambda i: -stores[i][2])
    routes = {}
    for index in order:
        x, y, w = stores[index]
        best = None
        for server, route_list in routes.items():
            point = point_of(server)
            for route_index, current in enumerate(route_list):
                if len(current) >= CAPACITY:
                    continue
                cost, candidate = insert_order(current, index, point, stores)
                old_cost = route_cost(point, current, stores)
                trial = clean(routes)
                trial[server][route_index] = candidate
                if not feasible(trial, stores):
                    continue
                if best is None or cost - old_cost < best[0]:
                    best = (cost - old_cost, server, route_index, candidate, trial)
        for server in [-1] + list(range(len(RDCS))):
            point = point_of(server)
            cost = route_cost(point, [index], stores)
            extra = 0.0
            if server >= 0:
                extra += TRUNK_KM * distance(CDC, RDCS[server]) * w
                if server not in routes:
                    extra += OPEN_COST
            trial = clean(routes)
            trial.setdefault(server, []).append([index])
            if not feasible(trial, stores):
                continue
            if best is None or cost + extra < best[0]:
                best = (cost + extra, server, None, [index], trial)
        if best is None:
            return None
        routes = best[4]
    return routes


def move_store(routes, store, target, stores):
    routes = clean(routes)
    current = next((server for server, route_list in routes.items()
                    if any(store in order for order in route_list)), None)
    if current == target:
        return None
    for order in routes.get(current, []):
        if store in order:
            order.remove(store)
    routes = clean(routes)
    point = point_of(target)
    best = None
    if routes.get(target):
        for route_index, order in enumerate(routes[target]):
            if len(order) >= CAPACITY:
                continue
            cost, candidate = insert_order(order, store, point, stores)
            trial = clean(routes)
            trial[target][route_index] = candidate
            if feasible(trial, stores):
                value = evaluate(trial, stores)[0]
                if best is None or value < best[0]:
                    best = (value, trial)
    trial = clean(routes)
    trial.setdefault(target, []).append([store])
    if feasible(trial, stores):
        value = evaluate(trial, stores)[0]
        if best is None or value < best[0]:
            best = (value, trial)
    return best


def swap_stores(routes, first, second, stores):
    routes = clean(routes)
    first_server = next(server for server, route_list in routes.items() if any(first in order for order in route_list))
    second_server = next(server for server, route_list in routes.items() if any(second in order for order in route_list))
    for order in routes.get(first_server, []):
        if first in order:
            order.remove(first)
    for order in routes.get(second_server, []):
        if second in order:
            order.remove(second)
    routes = clean(routes)
    for server, store in ((first_server, second), (second_server, first)):
        point = point_of(server)
        indices = [index for order in routes.get(server, []) for index in order] + [store]
        routes[server] = build_routes(point, indices, stores)
    routes = clean(routes)
    if not feasible(routes, stores):
        return None
    return evaluate(routes, stores)[0], routes


def two_opt(routes, stores):
    routes = clean(routes)
    best = None
    for server, route_list in routes.items():
        point = point_of(server)
        for route_index, order in enumerate(route_list):
            for start in range(len(order) - 1):
                for end in range(start + 2, len(order) + 1):
                    candidate = order[:start] + order[start:end][::-1] + order[end:]
                    trial = clean(routes)
                    trial[server][route_index] = candidate
                    if not feasible(trial, stores):
                        continue
                    value = evaluate(trial, stores)[0]
                    if best is None or value < best[0]:
                        best = (value, trial)
    return best


def local_search(routes, stores, max_rounds=20):
    routes = clean(routes)
    current = evaluate(routes, stores)[0]
    for _ in range(max_rounds):
        improved = False
        for store in range(len(stores)):
            for target in [-1] + list(range(len(RDCS))):
                candidate = move_store(routes, store, target, stores)
                if candidate and candidate[0] < current - EPS:
                    routes = candidate[1]
                    current = candidate[0]
                    improved = True
        for first in range(len(stores)):
            for second in range(first + 1, len(stores)):
                candidate = swap_stores(routes, first, second, stores)
                if candidate and candidate[0] < current - EPS:
                    routes = candidate[1]
                    current = candidate[0]
                    improved = True
        candidate = two_opt(routes, stores)
        if candidate and candidate[0] < current - EPS:
            routes = candidate[1]
            current = candidate[0]
            improved = True
        if not improved:
            break
    return current, routes


def main():
    rows = []
    for seed in range(10):
        stores = make_instance(seed)
        seq = repair(sequential(stores), stores)
        jnt = joint(stores)
        seq_final = None if seq is None else local_search(seq, stores)
        jnt_final = None if jnt is None else local_search(jnt, stores)
        rows.append({
            "seed": seed,
            "sequential_before": None if seq is None else evaluate(seq, stores)[0],
            "sequential_after": None if seq_final is None else seq_final[0],
            "joint_before": None if jnt is None else evaluate(jnt, stores)[0],
            "joint_after": None if jnt_final is None else jnt_final[0],
            "final_gap": None if (seq_final is None or jnt_final is None) else seq_final[0] - jnt_final[0],
        })
    valid = [row for row in rows if row["final_gap"] is not None]
    summary = {
        "instances": len(rows),
        "valid": len(valid),
        "joint_better": sum(1 for row in valid if row["final_gap"] > 1e-6),
        "sequential_better": sum(1 for row in valid if row["final_gap"] < -1e-6),
        "mean_final_gap": sum(row["final_gap"] for row in valid) / len(valid) if valid else None,
        "max_abs_final_gap": max((abs(row["final_gap"]) for row in valid), default=None),
        "rows": rows,
        "scope": "twelve stores, four RDC candidates, one CDC, capacity three; synthetic",
        "limitations": [
            "Same local search is applied to both initial solutions, but it is first-improvement and may stop at different local optima.",
            "The instance is synthetic and single-product.",
        ],
    }
    out_dir = results_root() / "lrp_localsearch"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "valid", "joint_better", "sequential_better",
                       "mean_final_gap", "max_abs_final_gap")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
