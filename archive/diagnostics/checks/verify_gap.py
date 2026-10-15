# -*- coding: utf-8 -*-
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import sys, io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd, json, os
import cplex
from cplex.exceptions import CplexError

BASE = str(_REPO_ROOT)
INPUT = os.path.join(BASE, 'data/raw')

# ========== 快速验证: 用鲁棒模型的Γ=0%公式重跑确定性模型 ==========
# 目标: 确认gap是否来自求解质量

df_wh = pd.read_csv(os.path.join(INPUT, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(INPUT, 'df_proc.csv'))
df_customer = pd.read_csv(os.path.join(INPUT, 'df_customer.csv'))
df_order = pd.read_csv(os.path.join(INPUT, 'df_order.csv'))

cdc_names = df_wh[df_wh['Type']=='CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type']=='RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
customers = df_customer['Name'].tolist()
all_wh_names = cdc_names + rdc_names

cap = {}
proc_cost = {}
open_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost[row['Name']] = row['Processing_fee']
    open_cost[row['Name']] = row['Opening_fee']

dist_matrix = {}
travel_time_matrix = {}
for _, r in df_matrix.iterrows():
    dist_matrix[(r['From'], r['To'])] = r['Distance']
    dist_matrix[(r['To'], r['From'])] = r['Distance']
    travel_time_matrix[(r['From'], r['To'])] = r['Duration']
    travel_time_matrix[(r['To'], r['From'])] = r['Duration']

def calc_loss(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

loss_cost_matrix = {}
for (f, t), d in travel_time_matrix.items():
    loss_cost_matrix[(f, t)] = calc_loss(d)

T = 7
TIMELINESS_THRESHOLD = 600
TIMELINESS_RATIO = 0.95

# 构建需求
demand = {}
for day in range(T):
    date_str = f'2016-06-{24+day}'
    demand[day] = {}
    for _, row in df_order.iterrows():
        c = row['Name']
        for s in ['im', 'dm']:
            col = f'{date_str}_{s}'
            if col in df_order.columns:
                qty = row[col]
                if qty > 0:
                    demand[day][(c, s)] = qty

sku_cdc = {'im': port_cdc, 'dm': inland_cdc}

# ========== 构建简化确定性模型(类似鲁棒模型Γ=0%) ==========
print('构建简化确定性模型...')
problem = cplex.Cplex()
problem.set_log_stream(None)
problem.set_warning_stream(None)
problem.set_error_stream(None)
problem.set_results_stream(None)

problem.objective.set_sense(problem.objective.sense.minimize)

var_indices = {}
var_count = 0

def add_var(name, vtype, lb, ub, obj):
    global var_count
    var_indices[name] = var_count
    var_count += 1
    if vtype == 'B':
        problem.variables.add(obj=[obj], lb=[lb], ub=[ub],
                            types=[problem.variables.type.binary], names=[name])
    else:
        problem.variables.add(obj=[obj], lb=[lb], ub=[ub],
                            types=[problem.variables.type.continuous], names=[name])

# y变量 (仅RDC)
for t in range(T):
    for wh in rdc_names:
        add_var(f'y_{t}_{wh}', 'B', 0, 1, 0)

# open_new变量
for t in range(T):
    for wh in rdc_names:
        add_var(f'open_new_{t}_{wh}', 'B', 0, 1, 0)

# z变量 (仅RDC)
for wh in rdc_names:
    add_var(f'z_{wh}', 'B', 0, 1, 1.5)

# u变量 (无dist过滤)
obj_contributions = {}
for t in range(T):
    for (c, s), qty in demand[t].items():
        eligible = [sku_cdc[s]] + rdc_names
        for wh in eligible:
            d = dist_matrix.get((wh, c), 99999)
            if d > 5000:
                continue
            u_var = f'u_{t}_{wh}_{c}_{s}'
            if u_var in var_indices:
                continue
            add_var(u_var, 'B', 0, 1, 0)
            trans_cost = 1.45e-4 * d * qty
            loss_c = loss_cost_matrix.get((wh, c), 0.0) * qty
            proc_c = 2.0 * proc_cost.get(wh, 0.0) * qty
            obj_contributions[u_var] = obj_contributions.get(u_var, 0) + trans_cost + loss_c + proc_c

# f变量
for t in range(T):
    for cdc in cdc_names:
        s = 'im' if cdc == port_cdc else 'dm'
        for rdc in rdc_names:
            d = dist_matrix.get((cdc, rdc), 99999)
            if d > 5000:
                continue
            f_var = f'f_{t}_{cdc}_{rdc}_{s}'
            if f_var in var_indices:
                continue
            add_var(f_var, 'C', 0, 100000, 0)
            trans_c = 0.9e-4 * d
            loss_c = loss_cost_matrix.get((cdc, rdc), 0.0)
            proc_c = 2.0 * proc_cost.get(cdc, 0.0)
            obj_contributions[f_var] = obj_contributions.get(f_var, 0) + trans_c + loss_c + proc_c

# v变量
for t in range(T):
    for (c, s) in demand[t].keys():
        v_var = f'v_{t}_{c}_{s}'
        if v_var not in var_indices:
            add_var(v_var, 'B', 0, 1, 0)

# w变量 (仅RDC)
for t in range(T):
    for wh in rdc_names:
        add_var(f'w_{t}_{wh}', 'C', 0, 100000, 0)

# 设置obj系数
for var_name, coeff in obj_contributions.items():
    if var_name in var_indices:
        problem.objective.set_linear(var_indices[var_name], coeff)

# w变量的obj
for t in range(T):
    for wh in rdc_names:
        problem.objective.set_linear(var_indices[f'w_{t}_{wh}'], -0.8 * proc_cost.get(wh, 0.0))

# open_new变量的obj
for t in range(T):
    for wh in rdc_names:
        problem.objective.set_linear(var_indices[f'open_new_{t}_{wh}'], open_cost.get(wh, 0.0))

print(f'变量数: {var_count}')

# ========== 约束 ==========
constraint_count = 0

def add_constraint(indices, coeffs, sense, rhs):
    global constraint_count
    problem.linear_constraints.add(lin_expr=[[indices, coeffs]], senses=[sense], rhs=[rhs])
    constraint_count += 1

# (1) 单调性: y_t >= y_{t-1}
for t in range(1, T):
    for wh in rdc_names:
        add_constraint([var_indices[f'y_{t}_{wh}'], var_indices[f'y_{t-1}_{wh}']],
                      [1, -1], 'G', 0)

# (2) 新开仓: open_new_t = y_t - y_{t-1}
for t in range(T):
    for wh in rdc_names:
        if t == 0:
            add_constraint([var_indices[f'open_new_{t}_{wh}'], var_indices[f'y_{t}_{wh}']],
                          [1, -1], 'E', 0)
        else:
            add_constraint([var_indices[f'open_new_{t}_{wh}'], var_indices[f'y_{t}_{wh}'], var_indices[f'y_{t-1}_{wh}']],
                          [1, -1, 1], 'E', 0)

# (3) z约束: z <= sum(y_t)/T (简化: z <= 1)
for wh in rdc_names:
    add_constraint([var_indices[f'z_{wh}']], [1], 'L', 1)

# (4) 单源配送
for t in range(T):
    for (c, s) in demand[t].keys():
        indices = []
        coeffs = []
        eligible = [sku_cdc[s]] + rdc_names
        for wh in eligible:
            u_var = f'u_{t}_{wh}_{c}_{s}'
            if u_var in var_indices:
                indices.append(var_indices[u_var])
                coeffs.append(1)
        if indices:
            add_constraint(indices, coeffs, 'E', 1)

# (5) u <= y (仅RDC)
for t in range(T):
    for (c, s) in demand[t].keys():
        for wh in rdc_names:
            u_var = f'u_{t}_{wh}_{c}_{s}'
            if u_var in var_indices:
                add_constraint([var_indices[u_var], var_indices[f'y_{t}_{wh}']],
                             [1, -1], 'L', 0)

# (6) 流量平衡
for t in range(T):
    for rdc in rdc_names:
        for s in ['im', 'dm']:
            cdc_name = sku_cdc[s]
            f_var = f'f_{t}_{cdc_name}_{rdc}_{s}'
            if f_var not in var_indices:
                continue
            indices = [var_indices[f_var]]
            coeffs = [-1.0]
            for c in customers:
                u_var = f'u_{t}_{rdc}_{c}_{s}'
                if u_var in var_indices and (c, s) in demand[t]:
                    qty = demand[t][(c, s)]
                    indices.append(var_indices[u_var])
                    coeffs.append(qty)
            if len(indices) > 1:
                add_constraint(indices, coeffs, 'E', 0)

# (7) RDC容量
for t in range(T):
    for wh in rdc_names:
        indices_lhs = [var_indices[f'y_{t}_{wh}']]
        coeffs_lhs = [-cap.get(wh, 0.0)]
        for s in ['im', 'dm']:
            for c in customers:
                u_var = f'u_{t}_{wh}_{c}_{s}'
                if u_var in var_indices and (c, s) in demand[t]:
                    qty = demand[t][(c, s)]
                    indices_lhs.append(var_indices[u_var])
                    coeffs_lhs.append(qty)
        add_constraint(indices_lhs, coeffs_lhs, 'L', 0)

# (8) CDC容量
for t in range(T):
    for cdc in cdc_names:
        s = 'im' if cdc == port_cdc else 'dm'
        cap_cdc = cap.get(cdc, 100000)
        indices_cdc = []
        coeffs_cdc = []
        for c in customers:
            u_var = f'u_{t}_{cdc}_{c}_{s}'
            if u_var in var_indices and (c, s) in demand[t]:
                qty = demand[t][(c, s)]
                indices_cdc.append(var_indices[u_var])
                coeffs_cdc.append(qty)
        for rdc in rdc_names:
            f_var = f'f_{t}_{cdc}_{rdc}_{s}'
            if f_var in var_indices:
                indices_cdc.append(var_indices[f_var])
                coeffs_cdc.append(1.0)
        if indices_cdc:
            add_constraint(indices_cdc, coeffs_cdc, 'L', cap_cdc)

# (9) 时效约束 (鲁棒模型风格)
for t in range(T):
    for (c, s) in demand[t].keys():
        v_var = f'v_{t}_{c}_{s}'
        if v_var not in var_indices:
            continue
        indices_v = [var_indices[v_var]]
        coeffs_v = [1.0]
        u_found = False
        for wh in all_wh_names:
            u_var = f'u_{t}_{wh}_{c}_{s}'
            travel_time = travel_time_matrix.get((wh, c), 99999)
            if u_var in var_indices and travel_time <= TIMELINESS_THRESHOLD:
                indices_v.append(var_indices[u_var])
                coeffs_v.append(-1.0)
                u_found = True
        if u_found:
            add_constraint(indices_v, coeffs_v, 'L', 0)

# (10) 时效满足率
for t in range(T):
    total_demand = sum(demand[t].values())
    required = TIMELINESS_RATIO * total_demand
    indices_time = []
    coeffs_time = []
    for (c, s), qty in demand[t].items():
        v_var = f'v_{t}_{c}_{s}'
        if v_var in var_indices:
            indices_time.append(var_indices[v_var])
            coeffs_time.append(qty)
    if indices_time:
        add_constraint(indices_time, coeffs_time, 'G', required)

# (11) w约束
for t in range(T):
    for wh in rdc_names:
        w_var = f'w_{t}_{wh}'
        z_var = f'z_{wh}'
        y_var = f'y_{t}_{wh}'
        # w <= sum(u*qty) for this wh
        indices_w = [var_indices[w_var]]
        coeffs_w = [-1.0]
        for (c, s), qty in demand[t].items():
            u_var = f'u_{t}_{wh}_{c}_{s}'
            if u_var in var_indices:
                indices_w.append(var_indices[u_var])
                coeffs_w.append(qty)
        add_constraint(indices_w, coeffs_w, 'L', 0)
        # w <= z * cap
        add_constraint([var_indices[w_var], var_indices[z_var]],
                      [1, -cap.get(wh, 0.0)], 'L', 0)

print(f'约束数: {constraint_count}')

# ========== 求解 ==========
problem.parameters.mip.tolerances.mipgap.set(0.005)
problem.parameters.timelimit.set(300)
problem.parameters.threads.set(4)

print('开始求解(300秒时间限制)...')
problem.solve()

status = problem.solution.get_status_string()
obj_val = problem.solution.get_objective_value()
try:
    mip_gap = problem.solution.MIP.get_mip_gap()
except:
    mip_gap = -1

print(f'\n=== 求解结果 ===')
print(f'状态: {status}')
print(f'目标值: {obj_val:.2f}')
print(f'MIP gap: {mip_gap*100:.2f}%')

# 对比
with open(os.path.join(BASE, 'results/question4', 'problem4_robust', 'robust_results.json'), 'r', encoding='utf-8') as f:
    rob = json.load(f)
rob_obj = rob[0]['objective']
print(f'\n鲁棒模型Γ=0%目标值: {rob_obj:.2f}')
print(f'差异: {obj_val - rob_obj:.2f} ({(obj_val - rob_obj)/rob_obj*100:.2f}%)')

# 提取开仓信息
open_rdcs = []
for wh in rdc_names:
    y_val = problem.solution.get_values(var_indices[f'y_0_{wh}'])
    if y_val > 0.5:
        open_rdcs.append(wh)
print(f'\n开仓RDC({len(open_rdcs)}): {sorted(open_rdcs)}')
print(f'鲁棒模型开仓RDC({len(rob[0]["open_warehouses"])}): {sorted(rob[0]["open_warehouses"])}')
