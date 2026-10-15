"""Exact support and service-ratio rows for one-sided budgeted demand increases."""
import math


def budget_support(coefficients, budget):
    """max a*z subject to 0<=z<=1 and sum(z)<=budget; negative a are unused."""
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("budget must be finite and nonnegative")
    values = [float(value) for value in coefficients]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("coefficients must be finite")
    values = sorted((max(value, 0.0) for value in values), reverse=True)
    budget = min(budget, len(values))
    count = int(budget)
    return sum(values[:count]) + (budget-count)*values[count] if count < len(values) else sum(values)


def service_ratio_rows(nominal, deltas, v_indices, ratio, budget, p_index=None, q_indices=None):
    """Rows guaranteeing sum(v*d)>=ratio*sum(d) for every demand in the set.

    d=nominal+delta*z; 0<=z<=1; sum(z)<=budget.
    Dual: -sum(nominal*v)+budget*p+sum(q)<=-ratio*sum(nominal),
          p+q_i+delta_i*v_i>=ratio*delta_i; p,q>=0.
    All indices refer to solver variables; variable bounds are set by the caller.
    """
    n = len(nominal)
    if len(deltas) != n or len(v_indices) != n or not 0 <= ratio <= 1:
        raise ValueError("invalid dimensions or service ratio")
    if not all(math.isfinite(x) and x >= 0 for x in (*nominal, *deltas)):
        raise ValueError("demand and deviations must be finite and nonnegative")
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("invalid budget")
    indices = list(v_indices)
    coefficients = [-float(x) for x in nominal]
    rows = []
    if budget > 0:
        if p_index is None or q_indices is None or len(q_indices) != n:
            raise ValueError("positive budget requires dual variables")
        indices += [p_index] + list(q_indices)
        coefficients += [float(budget)] + [1.0]*n
        for delta, v, q in zip(deltas, v_indices, q_indices):
            rows.append(([p_index, q, v], [1.0, 1.0, float(delta)], "G", ratio*delta))
    rows.append((indices, coefficients, "L", -ratio*sum(nominal)))
    return rows
