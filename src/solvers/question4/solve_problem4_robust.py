# ===========================================================================
# 问题4: 基于预算不确定集的静态鲁棒仓网优化
# Static Robust Warehouse Network Optimization
# with Bertsimas-Sim Budget-of-Uncertainty
#
# 技术路线:
#   1. 从历史需求减去星期均值，以残差样本标准差构建不确定集半径 δ
#   2. 建立静态鲁棒优化模型:
#      仓库开设(y)、系统采购(z)、配送(u)、调拨(f)和时效(v)均预先决定。
#      当前没有需求情景对应的可调整策略，不能直接解释为两阶段自适应模型。
#   3. Bertsimas-Sim对偶变换 → 等价单层MILP
#   4. CPLEX求解 + Γ参数扫描 → Price of Robustness分析
# ===========================================================================

from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _runtime_sys
_runtime_sys.path.insert(0, str(_REPO_ROOT))
from src.runtime import results_root as _results_root, read_forecast as _read_forecast, forecast_path as _forecast_path, configure_solver as _configure_solver, record_solver as _record_solver
_RESULTS_ROOT = _results_root()
from src.robust_support import budget_support, service_ratio_rows, discounted_route_row
import cplex
import pandas as pd
import numpy as np
import math
import os
import sys
import warnings
import json
from collections import defaultdict
from itertools import product
from datetime import datetime

warnings.filterwarnings('ignore')

# ===========================================================================
# 0. 配置
# ===========================================================================

BASE_DIR = str(_REPO_ROOT)
INPUT_DIR = os.path.join(BASE_DIR, 'data/raw')
OUTPUT_BASE = os.path.join(str(_RESULTS_ROOT), 'question4', 'problem4_robust')
FORECAST_FILE = str(_forecast_path())
PAST_ORDER_FILE = os.path.join(INPUT_DIR, 'df_past_order.csv')
WH_FILE = os.path.join(INPUT_DIR, 'df_wh.csv')
PROC_FILE = os.path.join(INPUT_DIR, 'df_proc.csv')
MATRIX_FILE = os.path.join(INPUT_DIR, 'df_matrix.csv')
CUSTOMER_FILE = os.path.join(INPUT_DIR, 'df_customer.csv')
LOC_FILE = os.path.join(INPUT_DIR, 'df_loc.csv')

TIMELINESS_THRESHOLD = 600.0
LOSS_THRESHOLD = 500.0
TIMELINESS_RATIO = 0.95
SMART_COST = 1.5
SMART_DISCOUNT = 0.4

GAMMA_VALUES = [float(value) for value in os.environ.get("OR_GAMMA_VALUES", "0,0.005,0.01,0.015,0.02,0.025,0.03,0.04,0.05").split(",")]

CPLEX_TIME_LIMIT = 1800
CPLEX_MIP_GAP = 0.005

os.makedirs(OUTPUT_BASE, exist_ok=True)

# ===========================================================================
# 1. 数据加载
# ===========================================================================

df_wh = pd.read_csv(WH_FILE)
df_proc = pd.read_csv(PROC_FILE)
df_matrix = pd.read_csv(MATRIX_FILE)
df_customer = pd.read_csv(CUSTOMER_FILE)
df_loc = pd.read_csv(LOC_FILE)
df_past_order = pd.read_csv(PAST_ORDER_FILE)
df_forecast = _read_forecast(FORECAST_FILE)

# --- 仓库信息 ---
cdc_names = list(df_wh[df_wh['Type'] == 'CDC']['Name'])
rdc_names = list(df_wh[df_wh['Type'] == 'RDC']['Name'])
factory_names = list(df_wh[df_wh['Type'] == 'Factory']['Name'])
all_wh_names = cdc_names + rdc_names

cap = {}
proc_cost = {}
open_cost = {}
wh_type = {}

for _, row in df_proc.iterrows():
    name = row['Name']
    cap[name] = row['Capacity']
    proc_cost[name] = row['Processing_fee']
    open_cost[name] = row['Opening_fee']

for _, row in df_wh.iterrows():
    wh_type[row['Name']] = row['Type']

# --- 仓库位置 ---
wh_loc = {}
for _, row in df_wh.iterrows():
    wh_loc[row['Name']] = row['Location']

customer_cities = list(df_customer['Name'])

# --- 距离矩阵 ---
dist_matrix = {}
dur_matrix = {}
for _, row in df_matrix.iterrows():
    origin = row['From']
    dest = row['To']
    dist_matrix[(origin, dest)] = row['Distance']
    dist_matrix[(dest, origin)] = row['Distance']
    dur_matrix[(origin, dest)] = row['Duration']
    dur_matrix[(dest, origin)] = row['Duration']

# --- 位置坐标 ---
loc_coords = {}
for _, row in df_loc.iterrows():
    loc_coords[row['Location']] = {'lng': row['Longitude'], 'lat': row['Latitude']}

# ===========================================================================
# 2. 不确定集构建：基于预测残差的δ（替代CV×α）
#    - 按星期几拆分历史数据，计算去周期残差
#    - δ = std_resid × RESIDUAL_BETA × weekday_factor
#    - 星期均值与残差使用同一历史样本估计，不能解释为独立回测误差或统计覆盖保证。
# ===========================================================================

print("=" * 70)
print("Step 1: 构建不确定集 (残差驱动 Budget-of-Uncertainty)")
print("=" * 70)

import datetime

RESIDUAL_BETA = 2.0

historical_date_cols = [c for c in df_past_order.columns
                        if c not in ['Name', 'SKU']]
historical_dates = pd.to_datetime(historical_date_cols)
historical_weekdays = [d.weekday() for d in historical_dates]

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
forecast_dates_parsed = pd.to_datetime(forecast_dates)
forecast_weekdays = [d.weekday() for d in forecast_dates_parsed]

WEEKDAY_FACTOR = {
    0: 1.15, 1: 0.90, 2: 0.90, 3: 0.90,
    4: 1.15, 5: 1.15, 6: 1.15
}
WEEKDAY_NAMES = {0: '周一', 1: '周二', 2: '周三', 3: '周四',
                 4: '周五', 5: '周六', 6: '周日'}

city_sku_resid_std = {}
city_sku_mean_val = {}

for _, row in df_past_order.iterrows():
    city = row['Name']
    sku = row['SKU']
    vals = row[historical_date_cols].values.astype(float)

    weekday_groups = {w: [] for w in range(7)}
    for i, v in enumerate(vals):
        wd = historical_weekdays[i]
        weekday_groups[wd].append(v)

    weekday_means = {}
    for wd, group in weekday_groups.items():
        weekday_means[wd] = np.mean(group) if len(group) > 0 else np.mean(vals)

    residuals = []
    for i, v in enumerate(vals):
        wd = historical_weekdays[i]
        residuals.append(v - weekday_means[wd])

    std_resid = np.std(residuals, ddof=1) if len(residuals) > 1 else 0.0
    city_sku_resid_std[(city, sku)] = max(std_resid, 0.01)
    city_sku_mean_val[(city, sku)] = np.mean(vals)

resid_stds = list(city_sku_resid_std.values())
mean_resid_std = np.mean(resid_stds)
print(f"  残差STD: min={np.min(resid_stds):.2f}, max={np.max(resid_stds):.2f}, "
      f"mean={mean_resid_std:.2f}, median={np.median(resid_stds):.2f}")

rel_unc = [city_sku_resid_std[k] / city_sku_mean_val[k]
           for k in city_sku_resid_std if city_sku_mean_val[k] > 1]
print(f"  δ/ŷ 均值: {np.mean(rel_unc)*100:.1f}% (残差驱动, β={RESIDUAL_BETA})")

T = len(forecast_dates)
demand_nominal = {}
demand_delta = {}

for t_idx, date_col in enumerate(forecast_dates):
    demand_nominal[t_idx] = {}
    demand_delta[t_idx] = {}
    wd = forecast_weekdays[t_idx]
    wf = WEEKDAY_FACTOR.get(wd, 1.0)

    for _, row in df_forecast.iterrows():
        city = row['Customer']
        sku = row['SKU']
        qty = float(row[date_col])
        demand_nominal[t_idx][(city, sku)] = qty

        std_r = city_sku_resid_std.get((city, sku), mean_resid_std)
        demand_delta[t_idx][(city, sku)] = std_r * RESIDUAL_BETA * wf

print(f"  周期权重: " + ", ".join(
    f"{WEEKDAY_NAMES[wd]}×{WEEKDAY_FACTOR[wd]}" for wd in forecast_weekdays))

all_demand_keys_period = {}
for t in range(T):
    all_demand_keys_period[t] = list(demand_nominal[t].keys())

total_nominal_demand = sum(sum(demand_nominal[t].values()) for t in range(T))
print(f"  周期数: {T} 天, 总名义需求: {total_nominal_demand:.2f} 吨")
print(f"  日期范围: {forecast_dates[0]} ~ {forecast_dates[-1]}")

# ===========================================================================
# 3. 损耗成本矩阵
# ===========================================================================

def calculate_loss_cost(minutes):
    if minutes <= LOSS_THRESHOLD:
        return 0.0
    else:
        loss_yuan = 0.2 * (minutes - LOSS_THRESHOLD) ** 2
        return loss_yuan / 10000.0

loss_cost_matrix = {}
for wh_name in all_wh_names:
    for c_city in customer_cities:
        travel_time = dur_matrix.get((wh_name, c_city), 10000)
        loss_cost_matrix[(wh_name, c_city)] = calculate_loss_cost(travel_time)

for cdc in cdc_names:
    for rdc in rdc_names:
        travel_time = dur_matrix.get((cdc, rdc), 10000)
        loss_cost_matrix[(cdc, rdc)] = calculate_loss_cost(travel_time)

# 用于时效判断的运输时间
travel_time_matrix = {}
for wh_name in all_wh_names:
    for c_city in customer_cities:
        travel_time_matrix[(wh_name, c_city)] = dur_matrix.get((wh_name, c_city), 10000)

# CDC → SKU映射
cdc_sku = {'gang-kou-CDC': 'im', 'nei-lu-CDC': 'dm'}
sku_cdc = {'im': 'gang-kou-CDC', 'dm': 'nei-lu-CDC'}

# ===========================================================================
# 4. Bertsimas-Sim鲁棒对等变换工具函数
# ===========================================================================

def compute_worst_case_total_demand(t, gamma_fraction, sku_filter=None):
    """
    计算最坏情况下总需求
    D_worst = Σ ŷ + max_{Σz≤Γ} Σ δ·z
    """
    keys = all_demand_keys_period[t]
    if sku_filter:
        keys = [k for k in keys if k[1] == sku_filter]

    nominal_sum = sum(demand_nominal[t][k] for k in keys)
    deltas = [demand_delta[t][k] for k in keys]
    # One daily budget covers all customer/SKU entries, including a filtered CDC row.
    budget = gamma_fraction * len(all_demand_keys_period[t])
    return nominal_sum + budget_support(deltas, budget)


# ===========================================================================
# 5. 构建鲁棒MIP模型
# ===========================================================================

def build_robust_model(gamma_fraction):
    """
    构建Bertsimas-Sim鲁棒优化模型

    保护对象:
      1) RDC容量约束: Σ u·d ≤ cap·y → 鲁棒对等
      2) CDC容量约束: 预计算最坏总需求
      3) 目标函数中运输+处置+损耗成本 → 鲁棒对等
      4) 时效满足率: 预计算最坏总需求作为RHS
    """
    print(f"\n  [Building] gamma = {gamma_fraction:.2%}")

    problem = cplex.Cplex()
    problem.set_problem_name(f"robust_gamma_{gamma_fraction:.2f}")
    problem.objective.set_sense(problem.objective.sense.minimize)

    # ---- 变量定义 ----
    var_names = []
    var_types = []
    var_lb = []
    var_ub = []
    var_obj_coeffs = []

    def add_var(name, vtype, lb, ub, obj):
        var_names.append(name)
        var_types.append(vtype)
        var_lb.append(lb)
        var_ub.append(ub)
        var_obj_coeffs.append(obj)
        return len(var_names) - 1

    var_indices = {}

    skus = ['im', 'dm']

    # y_t^w: 仓库w在周期t是否开设
    for t in range(T):
        for wh in rdc_names:
            idx = add_var(f'y_{t}_{wh}', 'B', 0, 1, 0)
            var_indices[f'y_{t}_{wh}'] = idx

    # open_new_t^w: 仓库w在周期t是否新开设
    for t in range(T):
        for wh in rdc_names:
            idx = add_var(f'open_new_{t}_{wh}', 'B', 0, 1, open_cost.get(wh, 0.0))
            var_indices[f'open_new_{t}_{wh}'] = idx

    # z^w: 智能系统采购 (包括CDC和RDC)
    for wh in rdc_names:
        idx = add_var(f'z_{wh}', 'B', 0, 1, SMART_COST)
        var_indices[f'z_{wh}'] = idx
    # [FIX] 添加CDC的z变量，使Γ=0%时与确定性模型等价
    for cdc in cdc_names:
        idx = add_var(f'z_{cdc}', 'B', 0, 1, SMART_COST)
        var_indices[f'z_{cdc}'] = idx

    # u_t^(w,c,s): 仓库w在周期t配送门店c的SKU s
    # [BUG FIX] 限制CDC-SKU对应：im只能由port_cdc+RDC服务，dm只能由inland_cdc+RDC服务
    for t in range(T):
        for c in customer_cities:
            for s in skus:
                if (c, s) not in demand_nominal[t]:
                    continue
                eligible_whs = [sku_cdc[s]] + rdc_names
                for wh in eligible_whs:
                    if wh in rdc_names and dist_matrix.get((sku_cdc[s], wh), 99999) > 5000:
                        continue
                    dist_km = dist_matrix.get((wh, c), 99999)
                    if dist_km > 5000:
                        continue
                    idx = add_var(f'u_{t}_{wh}_{c}_{s}', 'B', 0, 1, 0)
                    var_indices[f'u_{t}_{wh}_{c}_{s}'] = idx

    # f_t^(cdc,rdc,s): 调拨量
    for t in range(T):
        for cdc in cdc_names:
            s = cdc_sku[cdc]
            for rdc in rdc_names:
                dist_km = dist_matrix.get((cdc, rdc), 99999)
                if dist_km > 5000:
                    continue
                idx = add_var(f'f_{t}_{cdc}_{rdc}_{s}', 'C', 0, 100000, 0)
                var_indices[f'f_{t}_{cdc}_{rdc}_{s}'] = idx

    # v_t^(c,s): 是否满足时效
    for t in range(T):
        for c in customer_cities:
            for s in skus:
                if (c, s) not in demand_nominal[t]:
                    continue
                idx = add_var(f'v_{t}_{c}_{s}', 'B', 0, 1, 0)
                var_indices[f'v_{t}_{c}_{s}'] = idx

    # w_t^w: 智能系统适用总量 (包括RDC和CDC)
    for t in range(T):
        for wh in rdc_names:
            idx = add_var(f'w_{t}_{wh}', 'C', 0, 100000, 0)
            var_indices[f'w_{t}_{wh}'] = idx
    # [FIX] 添加CDC的w变量，使Γ=0%时与确定性模型等价
    for t in range(T):
        for cdc in cdc_names:
            idx = add_var(f'w_{t}_{cdc}', 'C', 0, 100000, 0)
            var_indices[f'w_{t}_{cdc}'] = idx

    # ---- 鲁棒优化辅助变量 ----
    # p_cap_t_wh: RDC容量鲁棒保护的Gamma乘子 (合并im+dm)
    p_cap_vars = {}
    for t in range(T):
        for wh in rdc_names:
            idx = add_var(f'p_cap_{t}_{wh}', 'C', 0, 100000, 0)
            var_indices[f'p_cap_{t}_{wh}'] = idx
            p_cap_vars[(t, wh)] = idx

    # q_cap_t_wh_s_c: RDC容量鲁棒保护的各城市松弛变量
    q_cap_vars = {}
    for t in range(T):
        for wh in rdc_names:
            for s in skus:
                for c in customer_cities:
                    if (c, s) not in demand_nominal[t]:
                        continue
                    idx = add_var(f'q_cap_{t}_{wh}_{s}_{c}', 'C', 0, 100000, 0)
                    var_indices[f'q_cap_{t}_{wh}_{s}_{c}'] = idx
                    q_cap_vars[(t, wh, s, c)] = idx

    # p_obj_t: 目标函数鲁棒保护的Gamma乘子
    p_obj_vars = {}
    for t in range(T):
        idx = add_var(f'p_obj_{t}', 'C', 0, cplex.infinity, 0)
        var_indices[f'p_obj_{t}'] = idx
        p_obj_vars[t] = idx

    # q_obj_t_c_s: 目标函数鲁棒保护的各城市松弛变量
    q_obj_vars = {}
    for t in range(T):
        for c in customer_cities:
            for s in skus:
                if (c, s) not in demand_nominal[t]:
                    continue
                idx = add_var(f'q_obj_{t}_{c}_{s}', 'C', 0, cplex.infinity, 0)
                var_indices[f'q_obj_{t}_{c}_{s}'] = idx
                q_obj_vars[(t, c, s)] = idx

    # Exact robust service-ratio duals for the same daily one-sided uncertainty set.
    p_time_vars, q_time_vars = {}, {}
    if gamma_fraction > 0:
        for t in range(T):
            p_time_vars[t] = add_var(f'p_time_{t}', 'C', 0, cplex.infinity, 0)
            for c, sku in all_demand_keys_period[t]:
                q_time_vars[t, c, sku] = add_var(f'q_time_{t}_{c}_{sku}', 'C', 0, cplex.infinity, 0)

    # ---- 应用变量定义 ----
    problem.variables.add(
        obj=var_obj_coeffs,
        lb=var_lb,
        ub=var_ub,
        types=var_types,
        names=var_names
    )

    # ---- 约束构建 ----
    lin_exprs = []
    senses = []
    rhs_vals = []

    def add_constraint(indices, coeffs, sense, rhs):
        lin_exprs.append([[int(i) for i in indices], [float(c) for c in coeffs]])
        senses.append(sense)
        rhs_vals.append(float(rhs))

    # ---- (1) 仅开不关: y_t^w >= y_{t-1}^w ----
    for wh in rdc_names:
        for t in range(1, T):
            idx_t = var_indices[f'y_{t}_{wh}']
            idx_tm1 = var_indices[f'y_{t-1}_{wh}']
            add_constraint([idx_t, idx_tm1], [1, -1], 'G', 0)

    # ---- (2) 新开设标识: open_new_t^w = y_t^w - y_{t-1}^w ----
    for wh in rdc_names:
        idx_0 = var_indices[f'y_0_{wh}']
        idx_new0 = var_indices[f'open_new_0_{wh}']
        add_constraint([idx_new0, idx_0], [1, -1], 'E', 0)
        for t in range(1, T):
            idx_t = var_indices[f'y_{t}_{wh}']
            idx_tm1 = var_indices[f'y_{t-1}_{wh}']
            idx_newt = var_indices[f'open_new_{t}_{wh}']
            add_constraint([idx_newt, idx_t, idx_tm1], [1, -1, 1], 'E', 0)

    # ---- (3) 单源配送: Σ_w u_t^(w,c,s) = 1 ----
    for t in range(T):
        for c in customer_cities:
            for s in skus:
                if (c, s) not in demand_nominal[t]:
                    continue
                indices = []
                coeffs = []
                for wh in all_wh_names:
                    var_name = f'u_{t}_{wh}_{c}_{s}'
                    if var_name in var_indices:
                        indices.append(var_indices[var_name])
                        coeffs.append(1)
                # An empty set of candidate routes must be infeasible, not silently skipped.
                add_constraint(indices, coeffs, 'E', 1)

    # ---- (4) u ≤ y (服务-开设约束) ----
    for t in range(T):
        for wh in rdc_names:
            idx_y = var_indices[f'y_{t}_{wh}']
            for c in customer_cities:
                for s in skus:
                    var_name = f'u_{t}_{wh}_{c}_{s}'
                    if var_name in var_indices:
                        add_constraint(
                            [var_indices[var_name], idx_y],
                            [1, -1], 'L', 0
                        )

    # ---- (5) RDC流量平衡: Σ_c u·ŷ + transfer_in = transfer_out ----
    for t in range(T):
        for rdc in rdc_names:
            for s in skus:
                if s not in cdc_sku.values():
                    continue
                cdc_name = sku_cdc[s]
                f_var = f'f_{t}_{cdc_name}_{rdc}_{s}'
                if f_var not in var_indices:
                    continue

                indices = [var_indices[f_var]]
                coeffs = [-1.0]

                for c in customer_cities:
                    u_var = f'u_{t}_{rdc}_{c}_{s}'
                    if u_var in var_indices and (c, s) in demand_nominal[t]:
                        qty = demand_nominal[t][(c, s)]
                        indices.append(var_indices[u_var])
                        coeffs.append(qty)

                if len(indices) > 1:
                    add_constraint(indices, coeffs, 'E', 0)

    # ---- (6) 鲁棒 RDC容量约束（合并 im + dm） ----
    # Nominal: Σ_{s} Σ_c u·ŷ ≤ cap·y
    # Robust:  Σ_{s}(Σ_c u·ŷ + Γ·p + Σ_c q_{s,c}) ≤ cap·y
    #           p + q_{s,c} ≥ u·δ_{s,c}  ∀s,c
    #           p ≥ 0, q_{s,c} ≥ 0
    # 每周期每SKU的参数数 (per-day)
    n_params_per_day = {}
    for t in range(T):
        n_params_per_day[t] = {}
        for s in skus:
            n_params_per_day[t][s] = len([k for k in all_demand_keys_period[t] if k[1] == s])

    for t in range(T):
        for wh in rdc_names:
            idx_y = var_indices[f'y_{t}_{wh}']
            cap_wh = cap.get(wh, 5000)

            n_im = n_params_per_day[t].get('im', 0)
            n_dm = n_params_per_day[t].get('dm', 0)
            n_params = n_im + n_dm
            gamma_int = min(int(gamma_fraction * n_params), n_params)
            gamma_frac_val = (gamma_fraction * n_params) - gamma_int
            gamma_used = float(gamma_int) + gamma_frac_val

            indices_rhs = [idx_y]
            coeffs_rhs = [cap_wh]

            indices_lhs = []
            coeffs_lhs = []

            if gamma_used > 1e-8:
                p_idx = p_cap_vars.get((t, wh))
                if p_idx is not None:
                    indices_lhs.append(p_idx)
                    coeffs_lhs.append(gamma_used)

            for s in skus:
                for c in customer_cities:
                    u_var = f'u_{t}_{wh}_{c}_{s}'
                    if u_var not in var_indices or (c, s) not in demand_nominal[t]:
                        continue

                    qty_nominal = demand_nominal[t][(c, s)]
                    indices_lhs.append(var_indices[u_var])
                    coeffs_lhs.append(qty_nominal)

                    if gamma_used > 1e-8:
                        q_idx = q_cap_vars.get((t, wh, s, c))
                        if q_idx is not None:
                            indices_lhs.append(q_idx)
                            coeffs_lhs.append(1.0)

            if indices_lhs:
                all_indices = indices_lhs + indices_rhs
                all_coeffs = coeffs_lhs + [-c for c in coeffs_rhs]
                add_constraint(all_indices, all_coeffs, 'L', 0)

    # ---- (7) 鲁棒 RDC容量辅助约束: p + q_c ≥ u·δ (仅 Γ>0) ----
    if gamma_fraction > 1e-8:
        for t in range(T):
            for wh in rdc_names:
                p_idx = p_cap_vars.get((t, wh))
                if p_idx is None:
                    continue
                for s in skus:
                    for c in customer_cities:
                        q_idx = q_cap_vars.get((t, wh, s, c))
                        u_var = f'u_{t}_{wh}_{c}_{s}'
                        if q_idx is None or u_var not in var_indices:
                            continue
                        if (c, s) not in demand_nominal[t]:
                            continue
                        delta_val = demand_delta[t][(c, s)]
                        add_constraint(
                            [p_idx, q_idx, var_indices[u_var]],
                            [1, 1, -delta_val], 'G', 0
                        )

    # ---- (8) CDC capacity: every unit of its SKU passes through the mandatory CDC.
    # Transfers are accounting flows at nominal demand; actual transfers follow fixed assignments.
    for t in range(T):
        for cdc in cdc_names:
            worst_total = compute_worst_case_total_demand(t, gamma_fraction, cdc_sku[cdc])
            add_constraint([], [], 'L', cap[cdc] - worst_total)

    # ---- (9) 时效满足 v 约束: 与确定性模型等价 ----
    # [FIX] 修改为与确定性模型相同的约束形式
    # 对于每个(wh, c, s):
    #   如果 travel_time <= 600: v >= u (即 u - v <= 0)
    #   如果 travel_time > 600:  v + u <= 1
    for t in range(T):
        for c in customer_cities:
            for s in skus:
                v_var = f'v_{t}_{c}_{s}'
                if v_var not in var_indices or (c, s) not in demand_nominal[t]:
                    continue
                
                eligible_whs = [sku_cdc[s]] + rdc_names
                for wh in eligible_whs:
                    u_var = f'u_{t}_{wh}_{c}_{s}'
                    if u_var not in var_indices:
                        continue
                    travel_time = travel_time_matrix.get((wh, c), 99999)
                    if travel_time <= TIMELINESS_THRESHOLD:
                        # 快速仓库: v >= u (即 u - v <= 0)
                        add_constraint([var_indices[u_var], var_indices[v_var]], [1, -1], 'L', 0)
                    else:
                        # 慢速仓库: v + u <= 1
                        add_constraint([var_indices[v_var], var_indices[u_var]], [1, 1], 'L', 1)

    # ---- (10) Exact robust ratio under d=nominal+delta*z, 0<=z<=1, sum(z)<=Gamma.
    for t in range(T):
        keys = all_demand_keys_period[t]
        rows = service_ratio_rows(
            [demand_nominal[t][key] for key in keys],
            [demand_delta[t][key] for key in keys],
            [var_indices[f'v_{t}_{c}_{sku}'] for c, sku in keys],
            TIMELINESS_RATIO, gamma_fraction * len(keys),
            p_time_vars.get(t),
            [q_time_vars[t, c, sku] for c, sku in keys] if gamma_fraction > 0 else None,
        )
        for indices, coefficients, sense, rhs in rows:
            add_constraint(indices, coefficients, sense, rhs)

    # ---- (11) 智能系统采购 z^w ≤ Σ_t y_t^w (包括CDC和RDC) ----
    for wh in rdc_names:
        idx_z = var_indices[f'z_{wh}']
        indices_zy = [idx_z]
        coeffs_zy = [1]
        for t in range(T):
            idx_yt = var_indices[f'y_{t}_{wh}']
            indices_zy.append(idx_yt)
            coeffs_zy.append(-1)
        add_constraint(indices_zy, coeffs_zy, 'L', 0)
    # [FIX] 添加CDC的z约束 (CDC是必开的，y=1)
    for cdc in cdc_names:
        idx_z = var_indices[f'z_{cdc}']
        indices_zy = [idx_z]
        coeffs_zy = [1]
        # CDC是必开的，y_t=1对所有t，所以约束简化为 z_cdc ≤ 1
        add_constraint(indices_zy, coeffs_zy, 'L', 1)

    # ---- (12) w_t^w 智能系统用量 ----
    for t in range(T):
        for wh in rdc_names:
            w_var = f'w_{t}_{wh}'
            if w_var not in var_indices:
                continue

            # w ≤ 总出库量
            indices_w = [var_indices[w_var]]
            coeffs_w = [1.0]
            for c in customer_cities:
                for s in skus:
                    u_var = f'u_{t}_{wh}_{c}_{s}'
                    if u_var in var_indices and (c, s) in demand_nominal[t]:
                        indices_w.append(var_indices[u_var])
                        coeffs_w.append(-demand_nominal[t][(c, s)])
            add_constraint(indices_w, coeffs_w, 'L', 0)

            # w ≤ z^w · cap
            idx_z = var_indices[f'z_{wh}']
            add_constraint(
                [var_indices[w_var], idx_z],
                [1, -cap.get(wh, 100000)], 'L', 0
            )
            add_constraint(indices_w + [idx_z], coeffs_w + [-cap[wh]], 'G', -cap[wh])

    # [FIX] 添加CDC的w约束 (与RDC类似，但包括调拨量)
    for t in range(T):
        for cdc in cdc_names:
            w_var = f'w_{t}_{cdc}'
            if w_var not in var_indices:
                continue
            s = cdc_sku[cdc]

            # w ≤ 总出库量 (包括直接服务门店 + 调拨到RDC)
            indices_w = [var_indices[w_var]]
            coeffs_w = [1.0]
            for c in customer_cities:
                u_var = f'u_{t}_{cdc}_{c}_{s}'
                if u_var in var_indices and (c, s) in demand_nominal[t]:
                    indices_w.append(var_indices[u_var])
                    coeffs_w.append(-demand_nominal[t][(c, s)])
            # CDC调拨到RDC的量
            for rdc in rdc_names:
                f_var = f'f_{t}_{cdc}_{rdc}_{s}'
                if f_var in var_indices:
                    indices_w.append(var_indices[f_var])
                    coeffs_w.append(-1.0)
            add_constraint(indices_w, coeffs_w, 'L', 0)

            # w ≤ z^cdc · cap
            idx_z = var_indices[f'z_{cdc}']
            add_constraint(
                [var_indices[w_var], idx_z],
                [1, -cap.get(cdc, 100000)], 'L', 0
            )
            add_constraint(indices_w + [idx_z], coeffs_w + [-cap[cdc]], 'G', -cap[cdc])

    # ---- 应用所有基础约束 ----
    existing_count = len(lin_exprs)
    for i in range(len(lin_exprs)):
        indices_list, coeff_list = lin_exprs[i]
        sense = senses[i]
        rhs = rhs_vals[i]
        try:
            problem.linear_constraints.add(
                lin_expr=[cplex.SparsePair(ind=indices_list, val=coeff_list)],
                senses=[sense],
                rhs=[rhs]
            )
        except Exception as e:
            raise RuntimeError(f"基础约束 {i} 添加失败，停止求解") from e

    # 清空暂存列表，为后续鲁棒约束重新使用
    lin_exprs.clear()
    senses.clear()
    rhs_vals.clear()

    # ---- (14) 设置变量目标系数（运输+处置+损耗） ----
    obj_contributions = {}

    # 基础目标: u变量(名义) + w变量(折扣)
    for t in range(T):
        for wh in all_wh_names:
            for c in customer_cities:
                for s in skus:
                    u_var = f'u_{t}_{wh}_{c}_{s}'
                    if u_var not in var_indices or (c, s) not in demand_nominal[t]:
                        continue

                    qty = demand_nominal[t][(c, s)]
                    dist_val = dist_matrix.get((wh, c), 99999)
                    trans_cost = 1.45e-4 * dist_val * qty
                    loss_cost = loss_cost_matrix.get((wh, c), 0.0) * qty
                    proc_val = proc_cost.get(wh, 0.0) * qty
                    obj_val = trans_cost + loss_cost + proc_val

                    obj_contributions[u_var] = obj_contributions.get(u_var, 0) + obj_val

        # f变量
        for cdc in cdc_names:
            s = cdc_sku[cdc]
            for rdc in rdc_names:
                f_var = f'f_{t}_{cdc}_{rdc}_{s}'
                if f_var not in var_indices:
                    continue
                dist_val = dist_matrix.get((cdc, rdc), 99999)
                trans_cost = 0.9e-4 * dist_val
                loss_cost = loss_cost_matrix.get((cdc, rdc), 0.0)
                proc_val = proc_cost.get(cdc, 0.0)
                obj_val = trans_cost + loss_cost + proc_val
                obj_contributions[f_var] = obj_contributions.get(f_var, 0) + obj_val

        # w折扣 (包括RDC和CDC)
        for wh in rdc_names:
            w_var = f'w_{t}_{wh}'
            if w_var in var_indices:
                obj_contributions[w_var] = obj_contributions.get(w_var, 0) - 0.4 * proc_cost.get(wh, 0.0)
        # [FIX] 添加CDC的w折扣
        for cdc in cdc_names:
            w_var = f'w_{t}_{cdc}'
            if w_var in var_indices:
                obj_contributions[w_var] = obj_contributions.get(w_var, 0) - 0.4 * proc_cost.get(cdc, 0.0)

    # 应用基础目标系数
    for var_name, coeff in obj_contributions.items():
        if var_name in var_indices:
            problem.objective.set_linear(var_indices[var_name], coeff)

    # ---- (15) 鲁棒目标函数项: Γ·p_obj + Σ q_obj (仅 Γ>0) ----
    if gamma_fraction > 1e-8:
        for t in range(T):
            n_params = len(all_demand_keys_period[t])
            gamma_int = min(int(gamma_fraction * n_params), n_params)
            gamma_f_val = (gamma_fraction * n_params) - gamma_int
            gamma_used = float(gamma_int) + gamma_f_val

            if gamma_used > 1e-8:
                p_idx = p_obj_vars.get(t)
                if p_idx is not None:
                    try:
                        current = problem.objective.get_linear(p_idx)
                        problem.objective.set_linear(p_idx, current + gamma_used)
                    except Exception:
                        problem.objective.set_linear(p_idx, gamma_used)

            for c, s in all_demand_keys_period[t]:
                q_idx = q_obj_vars.get((t, c, s))
                if q_idx is not None:
                    try:
                        current = problem.objective.get_linear(q_idx)
                        problem.objective.set_linear(q_idx, current + 1.0)
                    except Exception:
                        problem.objective.set_linear(q_idx, 1.0)

    # ---- (16) Net marginal cost of actual demand growth, including both systems.
    # Each row is active only for its selected route. Unselected rows are redundant.
    if gamma_fraction > 1e-8:
        for t in range(T):
            for c, sku in all_demand_keys_period[t]:
                cdc = sku_cdc[sku]
                for wh in all_wh_names:
                    u_name = f'u_{t}_{wh}_{c}_{sku}'
                    if u_name not in var_indices:
                        continue
                    gross = (1.45e-4 * dist_matrix.get((wh, c), 99999)
                             + loss_cost_matrix.get((wh, c), 0.0) + proc_cost[wh])
                    rdc_smart = None
                    rdc_discount = 0.0
                    if wh in rdc_names:
                        gross += (0.9e-4 * dist_matrix.get((cdc, wh), 99999)
                                  + loss_cost_matrix.get((cdc, wh), 0.0) + proc_cost[cdc])
                        rdc_smart = var_indices[f'z_{wh}']
                        rdc_discount = 0.4 * proc_cost[wh]
                    row = discounted_route_row(
                        p_obj_vars[t], q_obj_vars[t, c, sku], var_indices[u_name],
                        var_indices[f'z_{cdc}'], rdc_smart, gross,
                        0.4 * proc_cost[cdc], rdc_discount, demand_delta[t][c, sku])
                    add_constraint(*row)

    # ---- 应用鲁棒约束（新添加的） ----
    for i in range(len(lin_exprs)):
        indices_list, coeff_list = lin_exprs[i]
        sense = senses[i]
        rhs = rhs_vals[i]
        try:
            problem.linear_constraints.add(
                lin_expr=[cplex.SparsePair(ind=indices_list, val=coeff_list)],
                senses=[sense],
                rhs=[rhs]
            )
        except Exception as e:
            raise RuntimeError(f"鲁棒约束 {i} 添加失败，停止求解") from e

    # ---- 设置求解参数 ----
    problem.parameters.timelimit.set(CPLEX_TIME_LIMIT)
    problem.parameters.mip.tolerances.mipgap.set(CPLEX_MIP_GAP)
    problem.parameters.threads.set(4)

    return problem, var_indices

# ===========================================================================
# 6. 求解与结果提取
# ===========================================================================

def solve_and_extract(problem, var_indices, gamma_fraction):
    """求解模型并提取结果"""
    skus = ['im', 'dm']

    print(f"  [Solving] gamma = {gamma_fraction:.2%} ...")

    try:
        _configure_solver(problem)
        problem.solve()
        evidence = _record_solver(problem)
    except Exception as e:
        raise RuntimeError("CPLEX 求解失败") from e

    status = problem.solution.get_status()
    status_str = problem.solution.get_status_string()
    has_solution = bool(problem.solution.is_primal_feasible())
    if not has_solution:
        print(f"  Status: {status_str}, 无可用可行解")
        return {'gamma': gamma_fraction, 'status': status_str, 'total_cost': None,
                'has_incumbent': False, 'status_code': status}

    print(f"  Status: {status_str}, Objective: {problem.solution.get_objective_value():.4f}")

    sol = problem.solution.get_values()

    # ---- 提取结果 ----
    results = {
        **evidence,
        'gamma': gamma_fraction,
        'uncertainty_set': 'per-day shared budget; d=nominal+delta*z, 0<=z<=1',
        'service_ratio_formulation': 'exact_one_sided_budget_dual',
        'status': status_str,
        'objective': problem.solution.get_objective_value(),
    }

    # 仓库开设情况
    open_warehouses = set()
    open_by_day = {}
    for t in range(T):
        open_by_day[t] = []
        for wh in rdc_names:
            key = f'y_{t}_{wh}'
            if key in var_indices and sol[var_indices[key]] > 0.5:
                open_warehouses.add(wh)
                open_by_day[t].append(wh)

    # 费用分解
    total_transport_cust = 0
    total_transport_wh = 0
    total_proc = 0
    total_loss = 0
    total_open = 0
    total_smart = 0
    total_discount = 0
    daily_costs = []

    for t in range(T):
        transport_cust_t = 0
        transport_wh_t = 0
        proc_t = 0
        loss_t = 0
        discount_t = 0

        for wh in all_wh_names:
            for c in customer_cities:
                for s in skus:
                    u_key = f'u_{t}_{wh}_{c}_{s}'
                    if u_key not in var_indices:
                        continue
                    if sol[var_indices[u_key]] < 0.5:
                        continue
                    qty = demand_nominal[t].get((c, s), 0)
                    if qty <= 0:
                        continue
                    dist_val = dist_matrix.get((wh, c), 99999)
                    transport_cust_t += 1.45e-4 * dist_val * qty
                    loss_t += loss_cost_matrix.get((wh, c), 0.0) * qty
                    proc_t += proc_cost.get(wh, 0.0) * qty

        for cdc in cdc_names:
            s = cdc_sku[cdc]
            for rdc in rdc_names:
                f_key = f'f_{t}_{cdc}_{rdc}_{s}'
                if f_key not in var_indices:
                    continue
                flow = sol[var_indices[f_key]]
                if flow < 1e-6:
                    continue
                dist_val = dist_matrix.get((cdc, rdc), 99999)
                transport_wh_t += 0.9e-4 * dist_val * flow
                loss_t += loss_cost_matrix.get((cdc, rdc), 0.0) * flow
                proc_t += proc_cost.get(cdc, 0.0) * flow

        # 智能系统折扣
        for wh in all_wh_names:
            w_key = f'w_{t}_{wh}'
            if w_key in var_indices and sol[var_indices[w_key]] > 1e-6:
                discount_t += 0.4 * proc_cost.get(wh, 0.0) * sol[var_indices[w_key]]

        actual_proc_t = proc_t - discount_t

        total_transport_cust += transport_cust_t
        total_transport_wh += transport_wh_t
        total_proc += actual_proc_t
        total_loss += loss_t
        total_discount += discount_t

        daily_costs.append({
            'day': t,
            'transport_cust': transport_cust_t,
            'transport_wh': transport_wh_t,
            'proc': actual_proc_t,
            'loss': loss_t,
            'discount': discount_t,
            'total_daily': transport_cust_t + transport_wh_t + actual_proc_t + loss_t,
        })

    # 开仓成本
    for wh in all_wh_names:
        for t in range(T):
            key = f'open_new_{t}_{wh}'
            if key in var_indices and sol[var_indices[key]] > 0.5:
                total_open += open_cost.get(wh, 0.0)

    # 智能系统成本
    for wh in all_wh_names:
        key = f'z_{wh}'
        if key in var_indices and sol[var_indices[key]] > 0.5:
            total_smart += SMART_COST

    total_all = problem.solution.get_objective_value()

    robust_premium = total_all - (
        total_transport_cust + total_transport_wh + total_proc
        + total_loss + total_open + total_smart
    )

    # Independently recompute the selected policy's actual net worst-case cost.
    smart_warehouses = [wh for wh in all_wh_names if sol[var_indices[f'z_{wh}']] > 0.5]
    smart_set = set(smart_warehouses)
    assignment_policy = []
    policy_nominal = 0.0
    policy_extra = 0.0
    for t in range(T):
        deviations = []
        for c, sku in all_demand_keys_period[t]:
            selected = [wh for wh in all_wh_names
                        if f'u_{t}_{wh}_{c}_{sku}' in var_indices
                        and sol[var_indices[f'u_{t}_{wh}_{c}_{sku}']] > 0.5]
            if len(selected) != 1:
                raise RuntimeError(f'Invalid selected route for day {t}: {c}/{sku}')
            wh = selected[0]
            cdc = sku_cdc[sku]
            unit_cost = (1.45e-4 * dist_matrix[wh, c] + loss_cost_matrix[wh, c]
                         + proc_cost[wh] * (0.6 if wh in smart_set else 1.0))
            if wh in rdc_names:
                unit_cost += (0.9e-4 * dist_matrix[cdc, wh] + loss_cost_matrix[cdc, wh]
                              + proc_cost[cdc] * (0.6 if cdc in smart_set else 1.0))
            qty, delta = demand_nominal[t][c, sku], demand_delta[t][c, sku]
            policy_nominal += qty * unit_cost
            deviations.append(delta * unit_cost)
            assignment_policy.append({'day': t, 'customer': c, 'sku': sku, 'warehouse': wh,
                                      'nominal': qty, 'delta': delta,
                                      'on_time': travel_time_matrix[wh, c] <= TIMELINESS_THRESHOLD})
        policy_extra += budget_support(deviations, gamma_fraction * len(all_demand_keys_period[t]))
    policy_cost = policy_nominal + policy_extra + total_open + total_smart
    nominal_components = (total_transport_cust + total_transport_wh + total_proc + total_loss)
    tolerance = max(1e-5, 1e-8 * max(1.0, abs(policy_cost)))
    if abs(policy_nominal - nominal_components) > tolerance:
        raise RuntimeError('Nominal discount accounting does not match the selected policy')
    if total_all < policy_cost - tolerance:
        raise RuntimeError('Model objective understates the selected policy worst-case cost')

    results.update({
        'gamma': gamma_fraction,
        'uncertainty_set': 'per-day shared budget; d=nominal+delta*z, 0<=z<=1',
        'service_ratio_formulation': 'exact_one_sided_budget_dual',
        'status': status_str,
        'objective': total_all,
        'robust_premium': robust_premium,
        'objective_formulation': 'exact_discounted_selected_route_support',
        'policy_worst_case_cost': policy_cost,
        'policy_nominal_variable_cost': policy_nominal,
        'policy_robust_extra': policy_extra,
        'objective_policy_residual': total_all - policy_cost,
        'smart_warehouses': smart_warehouses,
        'assignment_policy': assignment_policy,
        'open_warehouses': sorted(open_warehouses),
        'num_open': len(open_warehouses),
        'open_by_day': open_by_day,
        'transport_cost_customer': total_transport_cust,
        'transport_cost_warehouse': total_transport_wh,
        'proc_cost': total_proc + total_discount,
        'proc_discount': total_discount,
        'proc_cost_actual': total_proc,
        'loss_cost': total_loss,
        'open_cost': total_open,
        'smart_cost': total_smart,
        'total_cost': total_all,
        'daily_costs': daily_costs,
    })

    return results

# ===========================================================================
# 7. Γ参数扫描主函数
# ===========================================================================

def main():
    print("=" * 70)
    print("问题4: 静态鲁棒仓网优化 (Bertsimas-Sim Budget-of-Uncertainty)")
    print("=" * 70)

    all_results = []

    for gamma in GAMMA_VALUES:
        print(f"\n{'='*60}")
        print(f"  Gamma = {gamma:.2%}")
        print(f"{'='*60}")

        problem, var_indices = build_robust_model(gamma)

        n_vars = problem.variables.get_num()
        n_constraints = problem.linear_constraints.get_num()
        print(f"  变量数: {n_vars}, 约束数: {n_constraints}")

        result = solve_and_extract(problem, var_indices, gamma)

        if result.get('total_cost') is None:
            print(f"  [NO INCUMBENT] gamma={gamma:.2%}, status={result.get('status')}")
            all_results.append(result)
            continue

        if result.get('total_cost') is not None:
            all_results.append(result)
            print(f"  开仓数: {result['num_open']}")
            print(f"  仓库: {result['open_warehouses']}")
            print(f"  运输(门): {result['transport_cost_customer']:.4f}")
            print(f"  运输(仓): {result['transport_cost_warehouse']:.4f}")
            print(f"  处置费: {result['proc_cost_actual']:.4f}")
            print(f"  损耗: {result['loss_cost']:.4f}")
            print(f"  开仓费: {result['open_cost']:.4f}")
            print(f"  智能费: {result['smart_cost']:.4f}")
            print(f"  总成本: {result['total_cost']:.4f}")
        else:
            print(f"  [SKIP] gamma={gamma:.2%} 无可行解")
            all_results.append({
                'gamma': gamma,
                'status': 'INFEASIBLE',
                'total_cost': None,
            })

    # ---- 输出结果汇总 ----
    print("\n" + "=" * 70)
    print("  结果汇总: Price of Robustness")
    print("=" * 70)

    base_cost = next((result['total_cost'] for result in all_results
                      if result['gamma'] == 0 and result.get('total_cost') is not None), None)

    print(f"{'Gamma':>8s}  {'开仓数':>6s}  {'运输(门)':>10s}  {'运输(仓)':>10s}  "
          f"{'处置':>10s}  {'损耗':>10s}  {'开仓':>10s}  {'智能':>8s}  "
          f"{'总成本':>12s}  {'vs Gamma0':>10s}")
    print("-" * 110)

    for r in all_results:
        if r.get('total_cost') is None:
            print(f"  {r['gamma']:.2%}  {r.get('status')}")
            continue

        tc = r.get('total_cost', 0)
        if base_cost and base_cost > 0:
            por = f"{(tc - base_cost) / base_cost * 100:.2f}%"
        else:
            por = 'n/a'

        print(f"  {r['gamma']:7.1%}  {r.get('num_open', 0):6d}  "
              f"{r.get('transport_cost_customer', 0):10.4f}  "
              f"{r.get('transport_cost_warehouse', 0):10.4f}  "
              f"{r.get('proc_cost_actual', 0):10.4f}  "
              f"{r.get('loss_cost', 0):10.4f}  "
              f"{r.get('open_cost', 0):10.4f}  "
              f"{r.get('smart_cost', 0):8.4f}  "
              f"{tc:12.4f}  {por:>10s}")

    # ---- 保存结果 ----
    output_file = os.path.join(OUTPUT_BASE, 'robust_results.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str, allow_nan=False)
    print(f"\n  结果已保存: {output_file}")

    # ---- 保存汇总CSV ----
    summary_rows = []
    for r in all_results:
        if r.get('total_cost') is None:
            continue
        summary_rows.append({
            'Gamma': f"{r['gamma']:.2%}",
            '开仓数量': r.get('num_open', 0),
            '仓库列表': ';'.join(r.get('open_warehouses', [])),
            '运输成本_门': f"{r.get('transport_cost_customer', 0):.4f}",
            '运输成本_仓': f"{r.get('transport_cost_warehouse', 0):.4f}",
            '处置成本': f"{r.get('proc_cost_actual', 0):.4f}",
            '损耗成本': f"{r.get('loss_cost', 0):.4f}",
            '开仓成本': f"{r.get('open_cost', 0):.4f}",
            '智能系统成本': f"{r.get('smart_cost', 0):.4f}",
            '总成本': f"{r.get('total_cost', 0):.4f}",
            '求解状态': r.get('status', ''),
        })

    df_summary = pd.DataFrame(summary_rows)
    csv_path = os.path.join(OUTPUT_BASE, '仓网业务表现文件_汇总.csv')
    df_summary.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"  汇总CSV已保存: {csv_path}")

    # ---- Price of Robustness 曲线 ----
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        gammas = [r['gamma'] for r in all_results if r.get('total_cost') is not None]
        costs = [r['total_cost'] for r in all_results if r.get('total_cost') is not None]
        open_nums = [r.get('num_open', 0) for r in all_results if r.get('total_cost') is not None]

        if gammas:
            fig, ax1 = plt.subplots(figsize=(10, 6))
            ax1.plot([g*100 for g in gammas], costs, 'b-o', linewidth=2, markersize=8)
            ax1.set_xlabel('Uncertainty Budget Γ (%)', fontsize=14)
            ax1.set_ylabel('Total Cost (万元)', fontsize=14, color='b')
            ax1.tick_params(axis='y', labelcolor='b')

            ax2 = ax1.twinx()
            ax2.plot([g*100 for g in gammas], open_nums, 'r-s', linewidth=2, markersize=8)
            ax2.set_ylabel('Number of Open RDCs', fontsize=14, color='r')
            ax2.tick_params(axis='y', labelcolor='r')

            plt.title('Feasible Incumbent Cost & Warehouse Count vs Γ', fontsize=16)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            fig_path = os.path.join(OUTPUT_BASE, 'price_of_robustness.png')
            plt.savefig(fig_path, dpi=150)
            plt.close()
            print(f"  图表已保存: {fig_path}")
    except Exception as e:
        print(f"  图表生成失败: {e}")

    print("\n" + "=" * 70)
    print("  实验完成!")
    print("=" * 70)

    return all_results


if __name__ == '__main__':
    main()
