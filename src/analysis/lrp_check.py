"""Minimal cold-chain LRP check.

One CDC, two candidate RDCs, four stores, one vehicle with capacity two.
Compares direct delivery, sequential assignment-then-routing, and joint
location-routing under a 95% demand-weighted on-time constraint and the
500-minute quadratic loss. The instance is deliberately small and synthetic.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
from itertools import permutations, product

from src.runtime import results_root

CDC = (0.0, 0.0)
RDCS = [(100.0, 0.0), (0.0, 100.0)]
STORES = [(120.0, 20.0, 0.32), (130.0, 0.0, 0.32), (400.0, 300.0, 0.32), (500.0, 500.0, 0.04)]
OPEN_COST = 400.0
VEHICLE_COST = 50.0
PROCESSING = 1.0
LAST_KM = 1.45
TRUNK_KM = 0.9
ON_TIME = 600.0
LOSS_START = 500.0


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def partitions(items):
    if not items:
        yield []
        return
    first = items[0]
    for rest in partitions(items[1:]):
        yield [[first]] + [block[:] for block in rest]
        for index, block in enumerate(rest):
            if len(block) == 1:
                merged = [b[:] for b in rest]
                merged[index] = [first] + block
                yield merged


def route_options(server, stores):
    """Yield (cost, on_time dict, route list) for every partition/order."""
    for partition in partitions(list(stores)):
        blocks = [list(permutations(block)) for block in partition]
        for orders in product(*blocks):
            cost = 0.0
            on_time = {}
            routes = []
            for order in orders:
                t = 0.0
                previous = server
                route_cost = VEHICLE_COST
                for store in order:
                    leg = distance(previous, STORES[store][:2])
                    t += leg
                    weight = STORES[store][2]
                    route_cost += LAST_KM * leg * weight
                    if leg > LOSS_START:
                        route_cost += 0.2 * (leg - LOSS_START) ** 2 * weight
                    on_time[store] = t <= ON_TIME
                    previous = STORES[store][:2]
                cost += route_cost
                routes.append(list(order))
            yield cost, on_time, routes


def assignment_cost(open_set, assignment, allow_pairing, require_service):
    total = 0.0
    on_time = {}
    routes_out = {}
    served = {rdc: 0.0 for rdc in open_set}
    for store, server in enumerate(assignment):
        weight = STORES[store][2]
        if server == 0:
            total += PROCESSING * weight
        else:
            total += 2.0 * PROCESSING * weight
            served[server - 1] += weight
    for rdc in open_set:
        total += OPEN_COST
        total += TRUNK_KM * distance(CDC, RDCS[rdc]) * served[rdc]
    for server in [-1] + list(open_set):
        stores = [store for store, chosen in enumerate(assignment) if chosen == server + 1]
        if not stores:
            continue
        point = CDC if server == -1 else RDCS[server]
        options = [(cost, on_time, routes) for cost, on_time, routes in route_options(point, stores)
                   if allow_pairing or all(len(route) == 1 for route in routes)]
        if not options:
            return None
        best = None
        for cost, times, routes in options:
            if require_service:
                late_weight = sum(STORES[s][2] for s, ok in times.items() if not ok)
                if late_weight > 0.05 * sum(STORES[s][2] for s in range(len(STORES))) + 1e-9:
                    continue
            if best is None or cost < best[0]:
                best = (cost, times, routes)
        if best is None:
            return None
        total += best[0]
        on_time.update(best[1])
        routes_out[server] = best[2]
    return total, on_time, routes_out


def best_for(allow_pairing, require_service):
    best = None
    for mask in range(4):
        open_set = [rdc for rdc in range(2) if mask & (1 << rdc)]
        choices = [0] + [rdc + 1 for rdc in open_set]
        for assignment in product(choices, repeat=len(STORES)):
            result = assignment_cost(open_set, assignment, allow_pairing, require_service)
            if result is None:
                continue
            cost, on_time, routes = result
            if best is None or cost < best["cost"]:
                best = {"cost": cost, "open": open_set, "assignment": list(assignment),
                        "on_time": on_time, "routes": routes}
    return best


def main():
    direct = best_for(allow_pairing=False, require_service=True)
    joint = best_for(allow_pairing=True, require_service=True)
    sequential = None
    if direct:
        sequential = assignment_cost(direct["open"], direct["assignment"], True, False)
    summary = {
        "stores": [{"x": x, "y": y, "weight": w} for x, y, w in STORES],
        "direct_cost": direct["cost"] if direct else None,
        "direct_open": direct["open"] if direct else None,
        "direct_assignment": direct["assignment"] if direct else None,
        "joint_cost": joint["cost"] if joint else None,
        "joint_open": joint["open"] if joint else None,
        "joint_assignment": joint["assignment"] if joint else None,
        "joint_routes": {str(k): v for k, v in joint["routes"].items()} if joint else None,
        "joint_late_stores": [s for s, ok in joint["on_time"].items() if not ok] if joint else None,
        "sequential_cost_after_routing": sequential[0] if sequential else None,
        "design_changed": bool(direct and joint and (direct["open"] != joint["open"] or direct["assignment"] != joint["assignment"])),
        "scope": "one CDC, two RDC candidates, four stores, one vehicle capacity two; synthetic coordinates",
        "limitations": [
            "Transport cost charges each store for the leg into it, not the whole vehicle load.",
            "No vehicle return cost; capacity is two stores, not weight.",
            "Only one product class is modelled.",
        ],
    }
    out_dir = results_root() / "lrp_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("direct_cost", "joint_cost", "sequential_cost_after_routing", "design_changed")},
                     ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
