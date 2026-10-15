"""Exact minimum timely-demand ratio over a one-sided budget uncertainty set."""
import math
import numpy as np
from scipy.optimize import linprog


def worst_service_ratio(nominal, deltas, timely, budget):
    nominal, deltas, timely = (np.asarray(values, dtype=float) for values in (nominal, deltas, timely))
    if nominal.ndim != 1 or not nominal.size or nominal.shape != deltas.shape or nominal.shape != timely.shape:
        raise ValueError("需求、偏差和准时标记必须是等长非空向量")
    if (not np.isfinite(nominal).all() or not np.isfinite(deltas).all()
            or (nominal < 0).any() or (deltas < 0).any() or nominal.sum() <= 0
            or not np.isin(timely, [0, 1]).all() or not math.isfinite(budget) or budget < 0):
        raise ValueError("需求、偏差、准时标记或预算无效")
    n = nominal.size
    # Let t=1/total_demand and y=z*t. Then y_i<=t and sum(y)<=budget*t.
    matrix = np.zeros((n+1, n+1))
    matrix[:n, :n] = np.eye(n)
    matrix[:n, -1] = -1
    matrix[-1, :n] = 1
    matrix[-1, -1] = -budget
    solution = linprog(np.r_[deltas*timely, nominal @ timely], A_ub=matrix, b_ub=np.zeros(n+1),
                       A_eq=[np.r_[deltas, nominal.sum()]], b_eq=[1.0], bounds=(0, None), method="highs")
    if not solution.success or solution.x[-1] <= 0:
        raise RuntimeError("最坏服务比例线性规划未成功")
    scenario = solution.x[:n]/solution.x[-1]
    if scenario.min() < -1e-7 or scenario.max() > 1+1e-7 or scenario.sum() > budget+1e-7:
        raise RuntimeError("还原的不确定情景不满足预算集合")
    demand = nominal + deltas*scenario
    actual_ratio = float((demand @ timely)/demand.sum())
    if abs(actual_ratio-solution.fun) > 1e-7:
        raise RuntimeError("比例重建结果与线性规划不一致")
    return {"worst_ratio": actual_ratio, "scenario_total_demand": float(demand.sum()),
            "scenario_timed_demand": float(demand @ timely), "budget_used": float(scenario.sum())}
