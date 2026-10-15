"""Record dependency versions and verify CPLEX on a hand-solvable integer model."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import sys


def check(solver_smoke=False):
    result = {"python": sys.version, "platform": platform.platform(), "packages": {}}
    for name in ("numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "lightgbm", "cplex", "openpyxl"):
        result["packages"][name] = importlib.metadata.version(name)
    if solver_smoke:
        import cplex
        problem = cplex.Cplex()
        problem.set_log_stream(None)
        problem.set_results_stream(None)
        problem.variables.add(obj=[3.0], lb=[0.0], types=["I"], names=["x"])
        problem.linear_constraints.add(lin_expr=[[[0], [1.0]]], senses=["G"], rhs=[2.5])
        problem.solve()
        objective = problem.solution.get_objective_value()
        if abs(objective - 9.0) > 1e-9:
            raise RuntimeError("小规模整数规划结果错误：预期 x=3、目标值为 9")
        result["solver_smoke"] = {"cplex_version": problem.get_version(),
                                  "status": problem.solution.get_status_string(), "objective": objective,
                                  "scope": "Small-model check only; full project models may require a separate CPLEX license."}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solver-smoke", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.solver_smoke)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
