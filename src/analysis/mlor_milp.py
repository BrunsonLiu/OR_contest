"""Gurobi MILP baseline for the MLOR location-routing model.

The formulation follows the manuscript: binary arcs, vehicle use, opening,
arrival times, MTZ, and the MLOR big-M constraint. One thread and a time limit
are used so the runtime is comparable with the single-threaded heuristics.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

import gurobipy as gp
from gurobipy import GRB

from src.analysis.mlor_scale import (
    CAPACITY, COST_PER_KM, KM_PER_DAY, OPEN_COST, PENALTY, SHELF_LIFE,
    VEHICLE_COST, WAREHOUSES, distance, make_instance,
)
from src.runtime import results_root

VEHICLES_PER_WAREHOUSE = 6
TIME_LIMIT = 30.0
BIG_M = 1000.0


def solve(stores, time_limit=TIME_LIMIT, debug=False, force_served=None):
    n = len(stores)
    nodes = list(range(n + 1))
    store_nodes = list(range(1, n + 1))
    warehouse_points = [warehouse["point"] for warehouse in WAREHOUSES]
    store_points = [(store["x"], store["y"]) for store in stores]

    def point(warehouse_index, node):
        if node == 0:
            return warehouse_points[warehouse_index]
        return store_points[node - 1]

    def travel_time(warehouse_index, k, j):
        return distance(point(warehouse_index, k), point(warehouse_index, j)) / KM_PER_DAY

    def travel_cost(warehouse_index, k, j):
        return distance(point(warehouse_index, k), point(warehouse_index, j)) * COST_PER_KM

    model = gp.Model("mlor")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.TimeLimit = time_limit
    model.Params.MIPGap = 1e-4

    y = model.addVars(len(WAREHOUSES), vtype=GRB.BINARY, name="y")
    r = model.addVars(len(WAREHOUSES), VEHICLES_PER_WAREHOUSE, vtype=GRB.BINARY, name="r")
    x = model.addVars(len(WAREHOUSES), VEHICLES_PER_WAREHOUSE, nodes, nodes, vtype=GRB.BINARY, name="x")
    T = model.addVars(store_nodes, lb=0.0, name="T")
    s = model.addVars(store_nodes, vtype=GRB.BINARY, name="s")

    for i in range(len(WAREHOUSES)):
        for v in range(VEHICLES_PER_WAREHOUSE):
            for node in nodes:
                model.addConstr(x[i, v, node, node] == 0, name="diag")
            model.addConstr(gp.quicksum(x[i, v, 0, j] for j in store_nodes) == r[i, v], name="depart")
            model.addConstr(gp.quicksum(x[i, v, j, 0] for j in store_nodes) == r[i, v], name="return")
            model.addConstr(gp.quicksum(1.0 * gp.quicksum(x[i, v, k, j] for k in nodes)
                                        for j in store_nodes) <= CAPACITY * r[i, v], name="capacity")
            model.addConstr(y[i] >= r[i, v], name="open")

    for j in store_nodes:
        model.addConstr(gp.quicksum(x[i, v, k, j] for i in range(len(WAREHOUSES))
                                    for v in range(VEHICLES_PER_WAREHOUSE) for k in nodes) == s[j], name="visit")
        for i in range(len(WAREHOUSES)):
            for v in range(VEHICLES_PER_WAREHOUSE):
                model.addConstr(gp.quicksum(x[i, v, k, j] for k in nodes) ==
                                gp.quicksum(x[i, v, j, k] for k in nodes), name="flow")
                model.addConstr(T[j] >= travel_time(i, 0, j) - BIG_M * (1 - x[i, v, 0, j]), name="depot_time")
                model.addConstr(T[j] <= (SHELF_LIFE - WAREHOUSES[i]["age"] - stores[j - 1]["mlor"]) +
                                BIG_M * (1 - gp.quicksum(x[i, v, k, j] for k in nodes)), name="mlor")
                for k in store_nodes:
                    if k == j:
                        continue
                    model.addConstr(T[j] >= T[k] + travel_time(i, k, j) - BIG_M * (1 - x[i, v, k, j]),
                                    name="mtz")

    model.setObjective(
        gp.quicksum(OPEN_COST * y[i] for i in range(len(WAREHOUSES))) +
        gp.quicksum(VEHICLE_COST * r[i, v] for i in range(len(WAREHOUSES))
                    for v in range(VEHICLES_PER_WAREHOUSE)) +
        gp.quicksum(travel_cost(i, k, j) * x[i, v, k, j]
                    for i in range(len(WAREHOUSES)) for v in range(VEHICLES_PER_WAREHOUSE)
                    for k in nodes for j in nodes if k != j) +
        gp.quicksum(PENALTY * (1 - s[j]) for j in store_nodes),
        GRB.MINIMIZE)

    if force_served:
        for node in force_served:
            model.addConstr(s[node] == 1, name="force_served")
    model.optimize()
    solved = model.Status in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL)
    if debug and model.SolCount > 0:
        used_r = [(i, v) for i in range(len(WAREHOUSES)) for v in range(VEHICLES_PER_WAREHOUSE)
                  if r[i, v].X > 0.5]
        used_y = [i for i in range(len(WAREHOUSES)) if y[i].X > 0.5]
        arcs = [(i, v, k, j) for i in range(len(WAREHOUSES)) for v in range(VEHICLES_PER_WAREHOUSE)
                for k in nodes for j in nodes if k != j and x[i, v, k, j].X > 0.5]
        print("DEBUG r", used_r, "y", used_y)
        print("DEBUG arcs", arcs)
        print("DEBUG T", {j: round(T[j].X, 3) for j in store_nodes})
        print("DEBUG s", {j: s[j].X for j in store_nodes})
        opening = sum(OPEN_COST * y[i].X for i in range(len(WAREHOUSES)))
        vehicles = sum(VEHICLE_COST * r[i, v].X for i in range(len(WAREHOUSES)) for v in range(VEHICLES_PER_WAREHOUSE))
        transport = sum(travel_cost(i, k, j) * x[i, v, k, j].X for i in range(len(WAREHOUSES))
                        for v in range(VEHICLES_PER_WAREHOUSE) for k in nodes for j in nodes if k != j)
        penalty = sum(PENALTY * (1 - s[j].X) for j in store_nodes)
        print("DEBUG components", round(opening, 3), round(vehicles, 3), round(transport, 3), round(penalty, 3),
              "sum", round(opening + vehicles + transport + penalty, 3))
    return {
        "status": int(model.Status),
        "solved": solved,
        "objective": model.ObjVal if solved and model.SolCount > 0 else None,
        "bound": model.ObjBound if solved else None,
        "gap": model.MIPGap if solved and model.SolCount > 0 else None,
        "runtime": model.Runtime,
        "time_limit": time_limit,
    }


def main():
    rows = []
    cases = ((8, "mlor-dp-r2-20261031", range(3)), (12, "mlor-dp12-r2-20261031", range(3)),
             (20, None, range(1)))
    for size, exact_dir, seeds in cases:
        exact = {}
        if exact_dir is not None:
            exact_path = _REPO_ROOT / f"results/experiments/{exact_dir}/mlor_dp/summary.json"
            exact = {row["seed"]: row["aware_cost"]
                     for row in json.loads(exact_path.read_text(encoding="utf-8"))["rows"]}
        for seed in seeds:
            stores = make_instance(seed, size)
            result = solve(stores)
            rows.append({"size": size, "seed": seed, "exact": exact.get(seed), **result})
    summary = {
        "rows": rows,
        "scope": "Gurobi MILP, one thread, 30 s limit, 3 seeds per size",
        "limitations": ["The MILP uses six vehicles per warehouse.",
                        "A time limit means some rows may be feasible but not proven optimal."],
    }
    out_dir = results_root() / "mlor_milp"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    for row in rows:
        print(row)
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
