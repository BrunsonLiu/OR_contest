"""Exercise the real model builder on hand-checkable, Community-compatible cases."""
import argparse
import contextlib
import io
import itertools
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify():
    with contextlib.redirect_stdout(io.StringIO()):
        loaded = runpy.run_path(str(ROOT / "src/solvers/question4/solve_problem4_robust.py"))
    build = loaded["build_robust_model"]
    env = build.__globals__
    city, rdc = "example-customer", "example-RDC"
    cdcs = ["gang-kou-CDC", "nei-lu-CDC"]
    keys = [(city, "im"), (city, "dm")]
    env.update(T=1, customer_cities=[city], rdc_names=[rdc], cdc_names=cdcs,
               all_wh_names=cdcs+[rdc], demand_nominal={0: dict.fromkeys(keys, 50.0)},
               demand_delta={0: dict.fromkeys(keys, 20.0)}, all_demand_keys_period={0: keys},
               proc_cost=dict.fromkeys(cdcs+[rdc], 1.0), open_cost=dict.fromkeys(cdcs+[rdc], 0.0),
               SMART_COST=0.0, CPLEX_TIME_LIMIT=5, CPLEX_MIP_GAP=0)
    env["dist_matrix"] = {(source, dest): 10.0 for source in cdcs+[rdc] for dest in [city, rdc]}
    env["travel_time_matrix"] = {(source, city): 100 if source == rdc else 700 for source in cdcs+[rdc]}
    env["loss_cost_matrix"] = dict.fromkeys(env["dist_matrix"], 0.0)
    reports = []
    cases = [("all_deliveries_timely", 200, 100, True),
             ("RDC_insufficient_under_growth", 110, 100, False),
             ("CDC_shared_budget_exceeds_capacity", 200, 65, False),
             ("no_eligible_route_cannot_drop_demand", 200, 100, False),
             ("unavailable_transfer_cannot_supply_RDC", 200, 100, False)]
    for name, rdc_cap, cdc_cap, expected_feasible in cases:
        env["cap"] = {rdc: rdc_cap, **dict.fromkeys(cdcs, cdc_cap)}
        env["dist_matrix"] = dict.fromkeys(env["dist_matrix"], 6000.0 if name.startswith("no_eligible") else 10.0)
        if name.startswith("unavailable_transfer"):
            for cdc in cdcs:
                env["dist_matrix"][cdc, rdc] = 6000.0
        with contextlib.redirect_stdout(io.StringIO()):
            problem, indices = build(0.5)  # Gamma=0.5*2=1, shared across both SKUs.
        problem.set_log_stream(None)
        problem.set_results_stream(None)
        if not name.startswith(("no_eligible", "unavailable_transfer")):
            problem.variables.set_lower_bounds([(indices[f"u_0_{rdc}_{city}_{sku}"], 1.0) for sku in ("im", "dm")])
        problem.solve()
        feasible = bool(problem.solution.is_primal_feasible())
        if feasible != expected_feasible:
            raise AssertionError(f"{name}: expected feasible={expected_feasible}, actual={feasible}")
        if feasible:
            for sku in ("im", "dm"):
                if problem.solution.get_values(indices[f"v_0_{city}_{sku}"]) < 0.999:
                    raise AssertionError("All selected routes are timely, so both v variables must be one")
        reports.append({"case": name, "expected_feasible": expected_feasible, "actual_feasible": feasible,
                        "status": problem.solution.get_status_string(), "variables": problem.variables.get_num(),
                        "Gamma": 1, "worst_RDC_demand": 120, "worst_demand_per_CDC": 70})
    # Exhaust all three system purchases and three uncertainty budgets against hand arithmetic.
    env["dist_matrix"] = dict.fromkeys(env["dist_matrix"], 10.0)
    env["cap"] = {rdc: 200, **dict.fromkeys(cdcs, 100)}
    env["proc_cost"] = {rdc: 5.0, cdcs[0]: 2.0, cdcs[1]: 3.0}
    env["SMART_COST"] = 1.5
    for systems in itertools.product((0, 1), repeat=3):
        for fraction in (0, 0.5, 1):
            with contextlib.redirect_stdout(io.StringIO()):
                problem, indices = build(fraction)
            problem.set_log_stream(None)
            problem.set_results_stream(None)
            fixed = [(indices[f"u_0_{rdc}_{city}_{sku}"], 1.0) for sku in ("im", "dm")]
            fixed += [(indices[f"z_{wh}"], state) for wh, state in zip(cdcs+[rdc], systems)]
            problem.variables.set_lower_bounds(fixed)
            problem.variables.set_upper_bounds(fixed)
            problem.solve()
            units = [0.00235 + fee*(1-0.4*systems[i]) + 5*(1-0.4*systems[2])
                     for i, fee in enumerate((2.0, 3.0))]
            nominal = 50*sum(units)
            extra = 0 if fraction == 0 else 20*max(units) if fraction == 0.5 else 20*sum(units)
            expected = nominal + extra + 1.5*sum(systems)
            actual = problem.solution.get_objective_value()
            if abs(actual-expected) > 1e-6:
                raise AssertionError(f"Cost mismatch for systems={systems}, gamma={fraction}: {actual} != {expected}")
            reports.append({"case": "discounted_worst_cost", "systems_CDC_im_CDC_dm_RDC": systems,
                            "budget_fraction": fraction, "expected_objective": expected,
                            "actual_objective": actual, "absolute_error": abs(actual-expected)})
    # With the systems fixed on, setting handled volume below actual throughput must fail.
    problem.variables.set_upper_bounds(indices[f"w_0_{rdc}"], 0.0)
    problem.solve()
    if problem.solution.is_primal_feasible():
        raise AssertionError("Nominal handling volume can understate actual system throughput")
    reports.append({"case": "discount_volume_cannot_be_underreported", "actual_feasible": False})
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = verify()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
