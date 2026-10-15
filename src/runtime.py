"""Shared paths, forecast contracts, and solver evidence for reproducible runs."""
from pathlib import Path
import json
import math
import os

ROOT = Path(__file__).resolve().parents[1]


def results_root():
    return Path(os.environ.get("OR_RESULTS_ROOT", ROOT / "results")).resolve()


def forecast_path():
    return Path(os.environ.get("OR_FORECAST_FILE", ROOT / "results/question3/订单需求量预测结果文件_sota.csv")).resolve()


def read_forecast(path=None):
    import numpy as np
    import pandas as pd

    path = Path(path) if path is not None else forecast_path()
    frame = pd.read_csv(path)
    if list(frame.columns[:2]) != ["Customer", "SKU"]:
        raise ValueError("预测文件前两列必须是 Customer、SKU")
    dates = pd.to_datetime(frame.columns[2:], format="mixed", errors="raise")
    expected_dates = pd.date_range("2016-06-24", "2016-06-30")
    if not dates.equals(expected_dates):
        raise ValueError("预测日期必须按顺序覆盖 2016-06-24 至 2016-06-30，且不能重复")
    if frame[["Customer", "SKU"]].isna().any().any() or frame.duplicated(["Customer", "SKU"]).any():
        raise ValueError("预测文件存在缺失或重复的 Customer/SKU")
    expected = pd.read_csv(ROOT / "data/raw/df_past_order.csv")
    expected_keys = set(zip(expected["Name"], expected["SKU"]))
    actual_keys = set(zip(frame["Customer"], frame["SKU"]))
    if actual_keys != expected_keys:
        raise ValueError(f"预测门店/SKU 不匹配：缺少 {len(expected_keys-actual_keys)}，多出 {len(actual_keys-expected_keys)}")
    values = frame.iloc[:, 2:].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("预测需求必须是有限、非负数值")
    frame.iloc[:, 2:] = values
    return frame


def configure_solver(problem):
    if os.environ.get("OR_SOLVER_TIME_LIMIT"):
        problem.parameters.timelimit.set(float(os.environ["OR_SOLVER_TIME_LIMIT"]))
    # Keep runs predictable on workstations; configurable through the launcher.
    if os.environ.get("OR_SOLVER_THREADS"):
        problem.parameters.threads.set(int(os.environ["OR_SOLVER_THREADS"]))


def solver_evidence(problem):
    feasible = bool(problem.solution.is_primal_feasible())
    evidence = {
        "status_code": problem.solution.get_status(),
        "status": problem.solution.get_status_string(),
        "has_incumbent": feasible,
        "variables": problem.variables.get_num(),
        "constraints": problem.linear_constraints.get_num(),
    }
    if feasible:
        evidence["objective"] = problem.solution.get_objective_value()
    if problem.get_problem_type() in (problem.problem_type.MILP, problem.problem_type.MIQP, problem.problem_type.MIQCP):
        try:
            bound = problem.solution.MIP.get_best_objective()
            evidence["best_bound"] = bound if math.isfinite(bound) else None
            evidence["relative_gap"] = problem.solution.MIP.get_mip_relative_gap() if feasible else None
        except Exception:
            evidence["relative_gap"] = None
    return evidence


def record_solver(problem):
    evidence = solver_evidence(problem)
    folder = os.environ.get("OR_RUN_DIR")
    if folder:
        with (Path(folder) / "solver_metrics.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(evidence, ensure_ascii=False, allow_nan=False) + "\n")
    return evidence
