"""
验证：确定性模型是否真的没找到最优解？
测试1: 用确定性模型代码，强制只用鲁棒模型的13个RDC
测试2: 对比两个模型的约束差异
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import cplex
import pandas as pd
import numpy as np
import time

BASE = str(_REPO_ROOT)

df_wh = pd.read_csv(f'{BASE}/data/raw/df_wh.csv')
df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
df_proc = pd.read_csv(f'{BASE}/data/raw/df_proc.csv')
df_forecast = pd.read_csv(f'{BASE}/results/question3/订单需求量预测结果文件_sota.csv')

dist = {}; dur = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

cap = {}; open_cost = {}; proc_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    open_cost[row['Name']] = row['Opening_fee']
    proc_cost[row['Name']] = row['Processing_fee']

def loss_per_ton(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000

loss_cost_matrix = {(f, t): loss_per_ton(d) for (f, t), d in dur.items()}

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names_all = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)

demand_multi = {}
for t_idx, period in enumerate(forecast_dates):
    demand_multi[t_idx] = {}
    for _, row in df_forecast.iterrows():
        demand_multi[t_idx][(row['Customer'], row['SKU'])] = float(row[period])


def solve_deterministic(rdc_subset, label, time_limit=600):
    """用确定性模型的逻辑求解，但限制RDC子集"""
    print(f"\n{'='*70}")
    print(f"求解: {label}")
    print(f"  RDC数: {len(rdc_subset)}, 时间限制: {time_limit}s")
    print(f"{'='*70}")

    t0 = time.time()
    problem = cplex.Cplex()
    problem.set_log_stream(None)
    problem.set_warning_stream(None)
    problem.set_results_stream(None)
    problem.objective.set_sense(problem.objective.sense.minimize)
    problem.parameters.mip.tolerances.mipgap.set(0.001)
    problem.parameters.timelimit.set(time_limit)

    var_count = 0
    var_indices = {}

    # y variables
    for t in range(T):
        for wh in rdc_subset:
            vn = f'y_{t}_{wh}'
            problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[vn])
            var_indices[vn] = var_count; var_count += 1

    # open_new variables
    for t in range(T):
        for wh in rdc_subset:
            vn = f'open_new_{t}_{wh}'
            problem.variables.add(obj=[open_cost.get(wh, 0)], lb=[0], ub=[1], types=['B'], names=[vn])
            var_indices[vn] = var_count; var_count += 1

    # w variables
    for t in range(T):
        for wh in rdc_subset:
            vn = f'w_{t}_{wh}'
            problem.variables.add(obj=[1.5 - 0.8 * proc_cost.get(wh, 0)], lb=[0], ub=[1], types=['B'], names=[vn])
            var_indices[vn] = var_count; var_count += 1

    # u variables
    for t in range(T):
        for (store, sku), qty in demand_multi[t].items():
            eligible_whs = [port_cdc] + rdc_subset if sku == 'im' else [inland_cdc] + rdc_subset
            for wh in eligible_whs:
                vn = f'u_{t}_{wh}_{store}_{sku}'
                d_val = dist.get((wh, store), 0)
                l_val = loss_cost_matrix.get((wh, store), 0.0)
                p_val = 2.0 * proc_cost.get(wh, 0.0)
                obj = 1.45e-4 * d_val * qty + l_val * qty + p_val * qty
                problem.variables.add(obj=[obj], lb=[0], ub=[1], types=['B'], names=[vn])
                var_indices[vn] = var_count; var_count += 1

    # f variables
    for t in range(T):
        for cdc in cdc_names:
            for rdc in rdc_subset:
                for sku in ['im', 'dm']:
                    if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                        vn = f'f_{t}_{cdc}_{rdc}_{sku}'
                        d_val = dist.get((cdc, rdc), 0)
                        l_val = loss_cost_matrix.get((cdc, rdc), 0.0)
                        p_val = 2.0 * proc_cost.get(cdc, 0.0)
                        obj = 0.9e-4 * d_val + l_val + p_val
                        problem.variables.add(obj=[obj], lb=[0], ub=[cplex.infinity], types=['C'], names=[vn])
                        var_indices[vn] = var_count; var_count += 1

    # v variables
    for t in range(T):
        for (store, sku), _ in demand_multi[t].items():
            vn = f'v_{t}_{store}_{sku}'
            problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[vn])
            var_indices[vn] = var_count; var_count += 1

    # ===== 约束 =====
    # 1. 单源
    for t in range(T):
        for (store, sku), _ in demand_multi[t].items():
            eligible_whs = [port_cdc] + rdc_subset if sku == 'im' else [inland_cdc] + rdc_subset
            indices = [var_indices[f'u_{t}_{wh}_{store}_{sku}'] for wh in eligible_whs if f'u_{t}_{wh}_{store}_{sku}' in var_indices]
            if indices:
                problem.linear_constraints.add(lin_expr=[[indices, [1]*len(indices)]], senses=['E'], rhs=[1])

    # 2. u <= y
    for t in range(T):
        for (store, sku), _ in demand_multi[t].items():
            eligible_whs = [port_cdc] + rdc_subset if sku == 'im' else [inland_cdc] + rdc_subset
            for wh in eligible_whs:
                u_var = f'u_{t}_{wh}_{store}_{sku}'
                if u_var in var_indices and wh in rdc_subset:
                    y_var = f'y_{t}_{wh}'
                    if y_var in var_indices:
                        problem.linear_constraints.add(
                            lin_expr=[[[var_indices[u_var], var_indices[y_var]], [1, -1]]],
                            senses=['L'], rhs=[0])

    # 3. 流量平衡
    for t in range(T):
        for rdc in rdc_subset:
            for sku in ['im', 'dm']:
                cdc = port_cdc if sku == 'im' else inland_cdc
                f_var = f'f_{t}_{cdc}_{rdc}_{sku}'
                indices = []
                values = []
                for (store, s), qty in demand_multi[t].items():
                    if s == sku:
                        u_var = f'u_{t}_{rdc}_{store}_{sku}'
                        if u_var in var_indices:
                            indices.append(var_indices[u_var])
                            values.append(qty)
                if f_var in var_indices:
                    indices.append(var_indices[f_var])
                    values.append(-1)
                if indices:
                    problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['E'], rhs=[0])

    # 4. 容量
    for t in range(T):
        for wh in rdc_subset:
            indices = [var_indices[f'y_{t}_{wh}']]
            values = [-cap.get(wh, 5000)]
            for (store, sku), qty in demand_multi[t].items():
                u_var = f'u_{t}_{wh}_{store}_{sku}'
                if u_var in var_indices:
                    indices.append(var_indices[u_var])
                    values.append(qty)
            if len(indices) > 1:
                problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['L'], rhs=[0])

    # 5. 时效
    for t in range(T):
        for (store, sku), _ in demand_multi[t].items():
            v_var = f'v_{t}_{store}_{sku}'
            if v_var not in var_indices:
                continue
            eligible_whs = [port_cdc] + rdc_subset if sku == 'im' else [inland_cdc] + rdc_subset
            for wh in eligible_whs:
                u_var = f'u_{t}_{wh}_{store}_{sku}'
                if u_var in var_indices:
                    travel = dur.get((wh, store), 99999)
                    if travel > 600:
                        problem.linear_constraints.add(
                            lin_expr=[[[var_indices[v_var], var_indices[u_var]], [1, -1]]],
                            senses=['G'], rhs=[0])

        total_demand = sum(qty for (s, sku), qty in demand_multi[t].items())
        indices_v = [var_indices[f'v_{t}_{store}_{sku}'] for (store, sku) in demand_multi[t] if f'v_{t}_{store}_{sku}' in var_indices]
        values_v = [demand_multi[t][(store, sku)] for (store, sku) in demand_multi[t] if f'v_{t}_{store}_{sku}' in var_indices]
        if indices_v:
            problem.linear_constraints.add(
                lin_expr=[[indices_v, values_v]], senses=['G'], rhs=[0.95 * total_demand])

    # 6. 仅开不关
    for t in range(1, T):
        for wh in rdc_subset:
            y_cur = f'y_{t}_{wh}'
            y_prev = f'y_{t-1}_{wh}'
            if y_cur in var_indices and y_prev in var_indices:
                problem.linear_constraints.add(
                    lin_expr=[[[var_indices[y_cur], var_indices[y_prev]], [1, -1]]],
                    senses=['G'], rhs=[0])

    # 7. open_new = y_t - y_{t-1}
    for t in range(T):
        for wh in rdc_subset:
            y_var = f'y_{t}_{wh}'
            on_var = f'open_new_{t}_{wh}'
            if y_var in var_indices and on_var in var_indices:
                if t == 0:
                    problem.linear_constraints.add(
                        lin_expr=[[[var_indices[on_var], var_indices[y_var]], [1, -1]]],
                        senses=['E'], rhs=[0])
                else:
                    y_prev = f'y_{t-1}_{wh}'
                    if y_prev in var_indices:
                        problem.linear_constraints.add(
                            lin_expr=[[[var_indices[on_var], var_indices[y_var], var_indices[y_prev]], [1, -1, 1]]],
                            senses=['E'], rhs=[0])

    # 8. 智能系统
    for t in range(T):
        for wh in rdc_subset:
            w_var = f'w_{t}_{wh}'
            y_var = f'y_{t}_{wh}'
            if w_var in var_indices and y_var in var_indices:
                problem.linear_constraints.add(
                    lin_expr=[[[var_indices[w_var], var_indices[y_var]], [1, -1]]],
                    senses=['L'], rhs=[0])

    build_time = time.time() - t0
    print(f"  建模: {build_time:.1f}s, 变量: {var_count}")

    t1 = time.time()
    problem.solve()
    solve_time = time.time() - t1

    status = problem.solution.get_status()
    obj = problem.solution.get_objective_value()

    open_rdcs = set()
    for t in range(T):
        for wh in rdc_subset:
            if problem.solution.get_values(var_indices[f'y_{t}_{wh}']) > 0.5:
                open_rdcs.add(wh)

    print(f"  求解: {solve_time:.1f}s")
    print(f"  状态: {status}, 目标值: {obj:.2f}")
    print(f"  开仓数: {len(open_rdcs)}, 仓库: {sorted(open_rdcs)}")

    return obj, open_rdcs


# ========== 测试1: 全部19个RDC ==========
obj_all, rdcs_all = solve_deterministic(rdc_names_all, "确定性模型 (全部19 RDC)", time_limit=600)

# ========== 测试2: 只用鲁棒模型的13个RDC ==========
rob_rdcs = ['bei-jing-DC', 'chang-sha-DC', 'chong-qing-DC', 'da-lian-DC',
            'guang-zhou-DC', 'ha-er-bin-DC', 'nan-jing-DC', 'ning-bo-DC',
            'qing-dao-DC', 'tian-jin-DC', 'wu-han-DC', 'xi-an-DC', 'zheng-zhou-DC']
obj_13, rdcs_13 = solve_deterministic(rob_rdcs, "确定性模型 (只用鲁棒的13 RDC)", time_limit=600)

# ========== 对比 ==========
print(f"\n{'='*70}")
print(f"对比结果")
print(f"{'='*70}")
print(f"  全部19 RDC: 目标值 = {obj_all:.2f}, 开仓 = {len(rdcs_all)}")
print(f"  只用13 RDC: 目标值 = {obj_13:.2f}, 开仓 = {len(rdcs_13)}")
print(f"  鲁棒Γ=0%:   目标值 = 79807.10")
print(f"  差距(19vs13): {obj_all - obj_13:.2f}")
if obj_all > obj_13 + 100:
    print(f"\n  ❗ 确定性模型用全部19个RDC反而更差！说明它没找到最优解")
    print(f"  或者说：搜索空间太大(19个RDC)反而让CPLEX迷路了")
elif obj_all < obj_13 - 100:
    print(f"\n  ✅ 确定性模型用全部19个RDC确实更好（有更多选择）")
