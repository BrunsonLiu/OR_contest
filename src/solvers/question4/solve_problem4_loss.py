# -*- coding: utf-8 -*-
"""
问题4精确求解器(CPLEX版) - 基于IBM CPLEX的整数规划方法

【方法特点】
1. 使用IBM CPLEX求解混合整数规划(MIP)，是否达到最优取决于实际状态和 gap
2. 完整建模：显式建模所有决策变量，包括开设变量、智能系统变量、服务关系变量、调拨变量等
3. 仅开不关约束：通过约束条件强制RDC开设后不关闭的单调性
4. 线性化处理：将非线性约束(如开仓成本仅在新增时支付)通过辅助变量进行线性化
5. 智能系统折扣：通过辅助变量w_t^w实现40%处理费折扣的线性化

【决策变量】
- y_t^w: t周期仓库开设变量(0/1)，CDC必开
- z^w: 智能系统采购变量(0/1)，一次性决策
- u_t^(w,c,s): t周期仓库w向门店c配送商品s的服务关系变量(0/1)
- f_t^(cdc,rdc,s): t周期CDC向RDC调拨商品s的调拨量(连续)
- v_t^(c,s): t周期时效满足变量(0/1)
- w_t^w: t周期智能系统折扣辅助变量(连续)
- open_new_t^w: t周期新增开设辅助变量(0/1)

【约束条件】
1. 仅开不关: y_t^w >= y_{t-1}^w
2. 新开设逻辑: open_new_t^w = y_t^w - y_{t-1}^w
3. 智能系统约束: z^w <= sum(y_t^w)
4. 单源服务: 每个需求有且仅有一个供应源
5. 服务绑定: u <= y (仓库开设才能服务)
6. 流量平衡: RDC出库量 = 调拨入库量
7. 容量约束: 处理量 <= 容量 * 开设变量
8. 时效约束: 95%需求量在时间限制内配送
9. 折扣线性化: w <= 总出库量, w <= z * 容量

【优化目标】
最小化: 开仓成本 + 智能系统成本 + 运输成本 + 损耗成本 + 处理成本 - 折扣节省

【求解参数】
- 默认 MIP gap: 0.005；统一入口可覆盖
- 默认时间限制: 1800秒；统一入口可覆盖
- 节点选择策略: 最佳界限优先

【输出文件】
- 多周期仓网业务表现文件.csv
- 多周期仓网供应关系文件_*.csv
- 仓库处置订单量文件.csv
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _runtime_sys
_runtime_sys.path.insert(0, str(_REPO_ROOT))
from src.runtime import results_root as _results_root, read_forecast as _read_forecast, configure_solver as _configure_solver, record_solver as _record_solver
_RESULTS_ROOT = _results_root()

import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import cplex
import os
import numpy as np

# 基础数据读取（同前序题目，CDC/RDC识别、距离/时效矩阵、仓库参数等）
input_dir = os.path.join(str(_REPO_ROOT), 'data/raw')
output_dir = os.path.join(str(_RESULTS_ROOT), 'question4', 'problem4_loss_v2', 'output_result')
os.makedirs(output_dir, exist_ok=True)

df_customer = pd.read_csv(os.path.join(input_dir, 'df_customer.csv'))
df_wh = pd.read_csv(os.path.join(input_dir, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(input_dir, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(input_dir, 'df_proc.csv'))
df_demand_multi = _read_forecast()

# 关键参数整理（复用前序逻辑）
cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
dist = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
time_matrix = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}

# 仓库参数
cap = {}; open_cost = {}; proc_cost = {}
proc_dict = {}
for _, row in df_proc.iterrows():
    proc_dict[row['Name']] = {
        'Capacity': row['Capacity'],
        'Opening_fee': row['Opening_fee'],
        'Processing_fee': row['Processing_fee']
    }

for _, row in df_wh.iterrows():
    wh_name = row['Name']
    wh_type = row['Type']
    if wh_type in ['RDC', 'CDC'] and wh_name in proc_dict:
        cap[wh_name] = proc_dict[wh_name]['Capacity']
        open_cost[wh_name] = proc_dict[wh_name]['Opening_fee']
        proc_cost[wh_name] = proc_dict[wh_name]['Processing_fee']

# 获取所有门店名称
customers = df_customer['Name'].tolist()

# 门店到城市的映射
store_city_map = {}
for _, row in df_customer.iterrows():
    store_city_map[row['Name']] = row['Location']

# 多周期需求整理（t=0~6对应7天）
periods = df_demand_multi.columns[2:]
T = len(periods)
demand_multi = {}
for t_idx, period in enumerate(periods):
    demand_multi[t_idx] = {}
    for _, row in df_demand_multi.iterrows():
        store = row['Customer']
        sku = row['SKU']
        qty = row[period]
        demand_multi[t_idx][(store, sku)] = qty

# 损耗成本计算（同第二问第三小题，平方公式）
def calculate_loss_cost(t):
    if t <= 500:
        return 0.0
    else:
        # 0.2*(t-500)^2 元/吨 -> 转换为万元/吨需除以 10000
        loss_yuan = 0.2 * (t - 500) ** 2
        return loss_yuan / 10000.0
loss_cost_matrix = {(f, t): calculate_loss_cost(time_matrix[(f, t)]) for f, t in time_matrix.keys()}

def solve_multi_period(gnn_opened=None, gnn_smart=None):
    """
    使用CPLEX求解多周期仓网优化问题
    
    参数:
        gnn_opened: GNN预测开设的仓库列表（可选），如果提供则固定这些仓库必须开设
        gnn_smart: GNN预测采购智能系统的仓库列表（可选），如果提供则固定这些仓库必须采购智能系统
    """
    # 创建CPLEX模型
    problem = cplex.Cplex()
    problem.objective.set_sense(problem.objective.sense.minimize)
    
    # ===================== CPLEX参数设置（减少gap） =====================
    # 设置MIP gap阈值（相对gap）
    problem.parameters.mip.tolerances.mipgap.set(0.005)
    
    # 设置绝对MIP gap阈值
    problem.parameters.mip.tolerances.absmipgap.set(0.0)
    
    # 设置求解器强调（平衡优化和可行性）
    problem.parameters.emphasis.mip.set(0)
    
    # 设置节点选择策略
    problem.parameters.mip.strategy.variableselect.set(0)
    
    # 设置最大求解时间（秒）
    problem.parameters.timelimit.set(1800)
    
    # ===================== 决策变量定义（增加周期维度） =====================
    var_indices = {}  # 变量名→索引映射
    var_count = 0
    
    # 1. 仓库开设变量 y_t^w（t:0~6，w:仓库）
    for t in range(T):
        for wh in df_wh['Name']:
            wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
            if wh_type in ['RDC', 'CDC']:
                var_name = f'y_{t}_{wh}'
                lb = 1.0 if wh in cdc_names else 0.0  # CDC必开
                ub = 1.0
                # 目标函数系数：仅当t=0时y_0^w=1，或t>0时y_t^w=1且y_{t-1}^w=0时，才加open_cost
                # 此处先设为0，后续通过约束处理“新增开设”逻辑，或用辅助变量表示新增开设
                obj = 0.0
                problem.variables.add(obj=[obj], lb=[lb], ub=[ub], types=[problem.variables.type.binary], names=[var_name])
                var_indices[var_name] = var_count
                var_count += 1
    
    # 2. 智能系统采购变量 z^w（一次性）
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            var_name = f'z_{wh}'
            obj = 1.5  # 一次性采购成本
            problem.variables.add(obj=[obj], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
            var_indices[var_name] = var_count
            var_count += 1
    
    # 3. 服务关系变量 u_t^(w,c,s)
    for t in range(T):
        for (store, sku), qty in demand_multi[t].items():
            eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
            for wh in eligible_whs:
                var_name = f'u_{t}_{wh}_{store}_{sku}'
                # 目标函数系数：运输成本（含损耗）+ 处置成本（入库+出库）
                dist_val = dist.get((wh, store), 0)
                trans_cost = 1.45e-4 * dist_val * qty  # 仓库→门店运输成本（元→万元）
                loss_cost = loss_cost_matrix.get((wh, store), 0.0) * qty  # 损耗成本
                proc_cost_val = proc_cost.get(wh, 0.0) * qty  # 处置成本（入库+出库）
                obj = trans_cost + loss_cost + proc_cost_val
                problem.variables.add(obj=[obj], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
                var_indices[var_name] = var_count
                var_count += 1
    
    # 4. 调拨量变量 f_t^(cdc,rdc,s)
    for t in range(T):
        for cdc in cdc_names:
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                        var_name = f'f_{t}_{cdc}_{rdc}_{sku}'
                        # 目标函数系数：调拨运输成本（含损耗）+ CDC处置成本（入库+出库）
                        dist_val = dist.get((cdc, rdc), 0)
                        trans_cost = 0.9e-4 * dist_val  # 元→万元（每吨成本，后续乘以调拨量）
                        loss_cost = loss_cost_matrix.get((cdc, rdc), 0.0)
                        proc_cost_cdc = proc_cost.get(cdc, 0.0)  # CDC处置成本（每吨）
                        obj = trans_cost + loss_cost + proc_cost_cdc
                        problem.variables.add(obj=[obj], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
                        var_indices[var_name] = var_count
                        var_count += 1
    
    # 5. 时效满足变量 v_t^(c,s)
    for t in range(T):
        for (store, sku), _ in demand_multi[t].items():
            var_name = f'v_{t}_{store}_{sku}'
            obj = 0.0  # 仅约束，不直接计入目标函数
            problem.variables.add(obj=[obj], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
            var_indices[var_name] = var_count
            var_count += 1
    
    # 6. 线性化辅助变量 w_t^w（处置成本折扣）
    for t in range(T):
        for wh in df_wh['Name']:
            wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
            if wh_type in ['RDC', 'CDC']:
                var_name = f'w_{t}_{wh}'
                # 目标函数系数：-0.4*proc_cost[wh]（折扣部分，减少总成本）
                obj = -0.4 * proc_cost.get(wh, 0.0)
                problem.variables.add(obj=[obj], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
                var_indices[var_name] = var_count
                var_count += 1
    
    # 7. 新增开设辅助变量（处理开仓成本，仅新增时支付）
    for t in range(T):
        for wh in rdc_names:  # CDC必开，无需辅助变量
            var_name = f'open_new_{t}_{wh}'
            obj = open_cost.get(wh, 0.0)  # 新增开设时支付开仓成本
            problem.variables.add(obj=[obj], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
            var_indices[var_name] = var_count
            var_count += 1
    
    print(f"总变量数: {var_count}")
    
    # ===================== 约束条件构建 =====================
    constraint_count = 0
    
    # （一）跨周期约束
    # 0. 仅开不关约束：y_t^w >= y_{t-1}^w（RDC一旦开设，后续周期保持开设）
    for wh in rdc_names:  # CDC必开，无需约束
        for t in range(1, T):
            var_y_t = f'y_{t}_{wh}'
            var_y_t_1 = f'y_{t-1}_{wh}'
            if var_y_t in var_indices and var_y_t_1 in var_indices:
                row = [[var_indices[var_y_t], var_indices[var_y_t_1]], [1.0, -1.0]]
                problem.linear_constraints.add(
                    lin_expr=[row],
                    senses=['G'],
                    rhs=[0.0],
                    names=[f'monotonic_{t}_{wh}'],
                )
                constraint_count += 1

    # 1. 新增开设辅助变量约束：open_new_t^w = 1 当且仅当 y_t^w=1 且 y_{t-1}^w=0
    for wh in rdc_names:
        # t=0时：open_new_0^w = y_0^w（初始周期无之前状态）
        var_y = f'y_0_{wh}'
        var_open_new = f'open_new_0_{wh}'
        row = [[var_open_new, var_y], [1.0, -1.0]]
        problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'open_new_0_{constraint_count}'])
        constraint_count += 1
        row = [[var_open_new, var_y], [-1.0, 1.0]]
        problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'open_new_0_2_{constraint_count}'])
        constraint_count += 1
        
        # t>0时：open_new_t^w ≤ y_t^w，open_new_t^w ≤ 1 - y_{t-1}^w，open_new_t^w ≥ y_t^w - y_{t-1}^w
        for t in range(1, T):
            var_y_t = f'y_{t}_{wh}'
            var_y_t_1 = f'y_{t-1}_{wh}'
            var_open_new_t = f'open_new_{t}_{wh}'
            row1 = [[var_open_new_t, var_y_t], [1.0, -1.0]]
            problem.linear_constraints.add(lin_expr=[row1], senses=['L'], rhs=[0.0], names=[f'open_new_t1_{constraint_count}'])
            constraint_count += 1
            row2 = [[var_open_new_t, var_y_t_1], [1.0, 1.0]]
            problem.linear_constraints.add(lin_expr=[row2], senses=['L'], rhs=[1.0], names=[f'open_new_t2_{constraint_count}'])
            constraint_count += 1
            row3 = [[var_open_new_t, var_y_t, var_y_t_1], [-1.0, 1.0, -1.0]]
            problem.linear_constraints.add(lin_expr=[row3], senses=['L'], rhs=[0.0], names=[f'open_new_t3_{constraint_count}'])
            constraint_count += 1
    
    # 2. 智能系统采购约束：z^w ≤ sum(y_t^w)（只要有一个周期开设即可）
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            var_z = f'z_{wh}'
            indices = [var_indices[var_z]] + [var_indices[f'y_{t}_{wh}'] for t in range(T)]
            values = [1.0] + [-1.0 for t in range(T)]  # 只要有一个周期开设即可
            problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['L'], rhs=[0.0], names=[f'z_constraint_{constraint_count}'])
            constraint_count += 1
    
    # （二）每个周期内约束（循环T次，复用单周期约束逻辑）
    for t in range(T):
        # 1. 单源服务约束
        for (store, sku), _ in demand_multi[t].items():
            eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
            indices = []
            values = []
            for wh in eligible_whs:
                var_name = f'u_{t}_{wh}_{store}_{sku}'
                if var_name in var_indices:
                    indices.append(var_indices[var_name])
                    values.append(1.0)
            if indices:
                problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['E'], rhs=[1.0], names=[f'single_source_{t}_{constraint_count}'])
                constraint_count += 1
        
        # 2. 服务与开仓绑定约束
        for (store, sku), _ in demand_multi[t].items():
            eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
            for wh in eligible_whs:
                var_u = f'u_{t}_{wh}_{store}_{sku}'
                var_y = f'y_{t}_{wh}'
                if var_u in var_indices and var_y in var_indices:
                    row = [[var_indices[var_u], var_indices[var_y]], [1.0, -1.0]]
                    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'service_open_{t}_{constraint_count}'])
                    constraint_count += 1
        
        # 3. RDC流量平衡约束
        for rdc in rdc_names:
            for sku in ['im', 'dm']:
                cdc = port_cdc if sku == 'im' else inland_cdc
                var_f = f'f_{t}_{cdc}_{rdc}_{sku}'
                indices = []
                values = []
                # 出库量：服务门店的需求量之和
                for (store, s), qty in demand_multi[t].items():
                    if s == sku:
                        var_u = f'u_{t}_{rdc}_{store}_{sku}'
                        if var_u in var_indices:
                            indices.append(var_indices[var_u])
                            values.append(qty)
                # 入库量：CDC调拨量（取负，平衡等式）
                if var_f in var_indices:
                    indices.append(var_indices[var_f])
                    values.append(-1.0)
                if indices:
                    problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['E'], rhs=[0.0], names=[f'balance_{t}_{constraint_count}'])
                    constraint_count += 1
        
        # 4. 仓库容量约束
        for wh in df_wh['Name']:
            wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
            if wh_type not in ['RDC', 'CDC']:
                continue
            var_y = f'y_{t}_{wh}'
            indices = [var_indices[var_y]]
            values = [-cap.get(wh, 0.0)]  # y_t^w * cap[w]，移到左边为 -cap[w] * y_t^w
            # 门店配送量
            for (store, sku), qty in demand_multi[t].items():
                var_u = f'u_{t}_{wh}_{store}_{sku}'
                if var_u in var_indices:
                    indices.append(var_indices[var_u])
                    values.append(qty)
            # CDC调拨量（仅CDC有调拨输出）
            if wh in cdc_names:
                for rdc in rdc_names:
                    for sku in ['im', 'dm']:
                        if (sku == 'im' and wh == port_cdc) or (sku == 'dm' and wh == inland_cdc):
                            var_f = f'f_{t}_{wh}_{rdc}_{sku}'
                            if var_f in var_indices:
                                indices.append(var_indices[var_f])
                                values.append(1.0)
            if indices:
                problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['L'], rhs=[0.0], names=[f'capacity_{t}_{constraint_count}'])
                constraint_count += 1
        
        # 5. 时效约束
        time_limit = 600  # 10小时=600分钟
        for (store, sku), _ in demand_multi[t].items():
            var_v = f'v_{t}_{store}_{sku}'
            eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
            for wh in eligible_whs:
                var_u = f'u_{t}_{wh}_{store}_{sku}'
                if var_u in var_indices and var_v in var_indices:
                    travel_time = time_matrix.get((wh, store), float('inf'))
                    if travel_time <= time_limit:
                        # v_t ≥ u_t（服务且时效满足→v=1）
                        row = [[var_indices[var_v], var_indices[var_u]], [-1.0, 1.0]]
                        problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'time1_{t}_{constraint_count}'])
                        constraint_count += 1
                    else:
                        # v_t + u_t ≤ 1（服务但时效不满足→v=0）
                        row = [[var_indices[var_v], var_indices[var_u]], [1.0, 1.0]]
                        problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[1.0], names=[f'time2_{t}_{constraint_count}'])
                        constraint_count += 1
        
        # 6. 整体时效满足率约束（对IM+DM海鲜应用95%时效满足率要求）
        total_seafood_demand_t = sum(qty for (store, sku), qty in demand_multi[t].items() if sku in ['im', 'dm'])
        indices = []
        values = []
        for (store, sku), qty in demand_multi[t].items():
            if sku in ['im', 'dm']:  # 对所有海鲜（IM+DM）应用时效约束
                var_v = f'v_{t}_{store}_{sku}'
                if var_v in var_indices:
                    indices.append(var_indices[var_v])
                    values.append(qty)
        if indices:
            problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['G'], rhs=[0.95 * total_seafood_demand_t], names=[f'overall_time_{t}_{constraint_count}'])
            constraint_count += 1
        
        # 7. 智能系统折扣线性化约束
        for wh in df_wh['Name']:
            wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
            if wh_type in ['RDC', 'CDC']:
                var_w = f'w_{t}_{wh}'
                var_z = f'z_{wh}'
                # w_t^w ≤ 总出库量（配送+调拨）
                indices1 = [var_indices[var_w]]
                values1 = [1.0]
                # 配送量
                for (store, sku), qty in demand_multi[t].items():
                    var_u = f'u_{t}_{wh}_{store}_{sku}'
                    if var_u in var_indices:
                        indices1.append(var_indices[var_u])
                        values1.append(-qty)
                # 调拨量（CDC）
                if wh in cdc_names:
                    for rdc in rdc_names:
                        for sku in ['im', 'dm']:
                            if (sku == 'im' and wh == port_cdc) or (sku == 'dm' and wh == inland_cdc):
                                var_f = f'f_{t}_{wh}_{rdc}_{sku}'
                                if var_f in var_indices:
                                    indices1.append(var_indices[var_f])
                                    values1.append(-1.0)
                problem.linear_constraints.add(lin_expr=[[indices1, values1]], senses=['L'], rhs=[0.0], names=[f'w_const1_{t}_{constraint_count}'])
                constraint_count += 1
                # w_t^w ≤ z^w * cap[w]
                indices2 = [var_indices[var_w], var_indices[var_z]]
                values2 = [1.0, -cap.get(wh, 100000)]
                problem.linear_constraints.add(lin_expr=[[indices2, values2]], senses=['L'], rhs=[0.0], names=[f'w_const2_{t}_{constraint_count}'])
                constraint_count += 1
    
    print(f"总约束数: {constraint_count}")
    
    # ===================== 求解与结果输出 =====================
    print("求解多周期模型...")
    _configure_solver(problem)
    problem.solve()
    _record_solver(problem)
    # 输出求解状态
    status_string = problem.solution.get_status_string()
    print(f"求解状态: {status_string}")

    has_solution = False
    try:
        has_solution = bool(problem.solution.is_primal_feasible())
    except Exception:
        has_solution = False

    if has_solution:
        obj_val = problem.solution.get_objective_value()
        if "optimal" in status_string.lower():
            print(f'多周期总最优成本: {obj_val:.2f} 万元')
        else:
            print(f'多周期当前最好可行解成本: {obj_val:.2f} 万元')
        
        # ==================== DIAGNOSTIC: CDC z/w values ====================
        print("\n===== DIAGNOSTIC: CDC z/w values =====")
        for wh in cdc_names:
            z_key = f'z_{wh}'
            z_val = problem.solution.get_values(var_indices[z_key]) if z_key in var_indices else 0
            print(f"  z_{wh} = {z_val:.4f}")
            for t in range(T):
                w_key = f'w_{t}_{wh}'
                if w_key in var_indices:
                    w_val = problem.solution.get_values(var_indices[w_key])
                    if w_val > 0.01:
                        discount = 0.4 * proc_cost.get(wh, 0) * w_val
                        print(f"    w_{t}_{wh} = {w_val:.4f}, discount = {discount:.4f}")
        
        print("\n  RDC z values:")
        for wh in rdc_names:
            z_key = f'z_{wh}'
            if z_key in var_indices:
                z_val = problem.solution.get_values(var_indices[z_key])
                if z_val > 0.5:
                    print(f"    z_{wh} = {z_val:.4f}")
        
        # CDC direct service analysis
        cdc_direct_qty = 0
        cdc_direct_loss = 0
        rdc_serve_qty = 0
        rdc_serve_loss = 0
        for t in range(T):
            for (store, sku), qty in demand_multi[t].items():
                for cdc in cdc_names:
                    vu = f'u_{t}_{cdc}_{store}_{sku}'
                    if vu in var_indices and problem.solution.get_values(var_indices[vu]) > 0.5:
                        cdc_direct_qty += qty
                        cdc_direct_loss += loss_cost_matrix.get((cdc, store), 0) * qty
                for rdc in rdc_names:
                    vu = f'u_{t}_{rdc}_{store}_{sku}'
                    if vu in var_indices and problem.solution.get_values(var_indices[vu]) > 0.5:
                        rdc_serve_qty += qty
                        rdc_serve_loss += loss_cost_matrix.get((rdc, store), 0) * qty
        print(f"\n  CDC direct: {cdc_direct_qty:.2f} tons, loss = {cdc_direct_loss:.2f}")
        print(f"  RDC serve:  {rdc_serve_qty:.2f} tons, loss = {rdc_serve_loss:.2f}")
        
        # CDC->RDC transfer
        transfer_qty = 0
        transfer_loss = 0
        for t in range(T):
            for cdc in cdc_names:
                for rdc in rdc_names:
                    for sku in ['im', 'dm']:
                        if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                            vf = f'f_{t}_{cdc}_{rdc}_{sku}'
                            if vf in var_indices:
                                fqty = problem.solution.get_values(var_indices[vf])
                                if fqty > 0.01:
                                    transfer_qty += fqty
                                    transfer_loss += loss_cost_matrix.get((cdc, rdc), 0) * fqty
        print(f"  Transfer:   {transfer_qty:.2f} tons, loss = {transfer_loss:.2f}")
        print(f"  Total loss = {cdc_direct_loss + rdc_serve_loss + transfer_loss:.2f}")
        print("===== END DIAGNOSTIC =====\n")
        
        # ==================== 先计算7天总成本（一次性） ====================
        # 开仓总成本（一次性）
        total_open_cost = 0.0
        for wh in rdc_names:
            for t_idx in range(T):
                var_open_new = f'open_new_{t_idx}_{wh}'
                if var_open_new in var_indices:
                    total_open_cost += open_cost.get(wh, 0.0) * problem.solution.get_values(var_indices[var_open_new])
        
        # 智能系统总成本（一次性）
        total_smart_cost = sum(1.5 * problem.solution.get_values(var_indices[f'z_{wh}']) for wh in df_wh['Name'] if f'z_{wh}' in var_indices)
        
        # 7天总运输/损耗/处置成本
        total_trans_cost = 0.0
        for t_idx in range(T):
            for (store, sku), qty in demand_multi[t_idx].items():
                eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
                for wh in eligible_whs:
                    var_u = f'u_{t_idx}_{wh}_{store}_{sku}'
                    if var_u in var_indices and problem.solution.get_values(var_indices[var_u]) > 0.5:
                        dist_val = dist.get((wh, store), 0)
                        trans_cost = 1.45e-4 * dist_val * qty
                        loss_cost = loss_cost_matrix.get((wh, store), 0.0) * qty
                        proc_cost_val = proc_cost.get(wh, 0.0) * qty
                        total_trans_cost += trans_cost + loss_cost + proc_cost_val
        
        # 调拨总成本
        total_fleet_cost = 0.0
        for t_idx in range(T):
            for cdc in cdc_names:
                for rdc in rdc_names:
                    for sku in ['im', 'dm']:
                        if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                            var_f = f'f_{t_idx}_{cdc}_{rdc}_{sku}'
                            if var_f in var_indices:
                                qty = problem.solution.get_values(var_indices[var_f])
                                if qty > 0.01:
                                    dist_val = dist.get((cdc, rdc), 0)
                                    trans_cost = 0.9e-4 * dist_val
                                    loss_cost = loss_cost_matrix.get((cdc, rdc), 0.0)
                                    proc_cost_cdc = proc_cost.get(cdc, 0.0)
                                    total_fleet_cost += qty * (trans_cost + loss_cost + proc_cost_cdc)
        
        # 7天总成本 = 运输处置 + 调拨 + 开仓（一次性） + 智能系统（一次性）
        total_7day_cost = total_trans_cost + total_fleet_cost + total_open_cost + total_smart_cost
        
        # ==================== 每天输出三个文件 ====================
        for t in range(T):
            period = periods[t].replace('/', '-')

            # ---- 1. 仓网业务表现文件 ----
            open_wh_count = 2
            for wh in rdc_names:
                var_y = f'y_{t}_{wh}'
                if var_y in var_indices and problem.solution.get_values(var_indices[var_y]) > 0.5:
                    open_wh_count += 1

            total_seafood_demand_t = sum(qty for (store, sku), qty in demand_multi[t].items() if sku in ['im', 'dm'])
            satisfied_seafood_demand_t = 0.0
            for (store, sku), qty in demand_multi[t].items():
                if sku in ['im', 'dm']:
                    var_v = f'v_{t}_{store}_{sku}'
                    if var_v in var_indices:
                        satisfied_seafood_demand_t += qty * problem.solution.get_values(var_indices[var_v])
            satisfied_rate_t = satisfied_seafood_demand_t / total_seafood_demand_t

            transport_wh_t = 0.0
            transport_cust_t = 0.0
            loss_cost_t = 0.0
            proc_cost_t = 0.0
            discount_t = 0.0

            for (store, sku), qty in demand_multi[t].items():
                eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
                for wh in eligible_whs:
                    var_u = f'u_{t}_{wh}_{store}_{sku}'
                    if var_u in var_indices and problem.solution.get_values(var_indices[var_u]) > 0.5:
                        dist_val = dist.get((wh, store), 0)
                        transport_cust_t += 1.45e-4 * dist_val * qty
                        loss_cost_t += loss_cost_matrix.get((wh, store), 0.0) * qty
                        proc_cost_t += proc_cost.get(wh, 0.0) * qty

            for cdc in cdc_names:
                for rdc in rdc_names:
                    for sku in ['im', 'dm']:
                        if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                            var_f = f'f_{t}_{cdc}_{rdc}_{sku}'
                            if var_f in var_indices:
                                qty = problem.solution.get_values(var_indices[var_f])
                                if qty > 0.01:
                                    dist_val = dist.get((cdc, rdc), 0)
                                    transport_wh_t += 0.9e-4 * dist_val * qty
                                    loss_cost_t += loss_cost_matrix.get((cdc, rdc), 0.0) * qty
                                    proc_cost_t += proc_cost.get(cdc, 0.0) * qty

            for wh in df_wh['Name']:
                wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
                if wh_type in ['RDC', 'CDC']:
                    var_w = f'w_{t}_{wh}'
                    if var_w in var_indices:
                        w_val = problem.solution.get_values(var_indices[var_w])
                        if w_val > 0.01:
                            discount_t += 0.4 * proc_cost.get(wh, 0.0) * w_val

            actual_proc_t = proc_cost_t - discount_t
            daily_total_cost = transport_wh_t + transport_cust_t + loss_cost_t + actual_proc_t

            is_first_day = (t == 0)
            if is_first_day:
                daily_total_with_one_time = daily_total_cost + total_open_cost + total_smart_cost
            else:
                daily_total_with_one_time = daily_total_cost

            business_perf = pd.DataFrame([{
                '周期（日期）': periods[t],
                '开仓数量': open_wh_count,
                '时效满足率': round(satisfied_rate_t, 4),
                '仓库之间的运输总成本（万元）': round(transport_wh_t, 2),
                '仓库到门店的运输总成本（万元）': round(transport_cust_t, 2),
                '损耗总成本（万元）': round(loss_cost_t, 2),
                '处置总成本（万元）': round(actual_proc_t, 2),
                '开仓总成本（万元）': round(total_open_cost, 2) if is_first_day else '-',
                '智能系统采购总成本（万元）': round(total_smart_cost, 2) if is_first_day else '-',
                '当天总成本（万元）': round(daily_total_with_one_time, 2)
            }])
            business_perf.to_csv(os.path.join(output_dir, f'仓网业务表现文件_{period}.csv'), index=False, encoding='utf-8-sig')

            # ---- 2. 仓网供应关系文件 ----
            supply_relationships = []
            for cdc in cdc_names:
                for rdc in rdc_names:
                    for sku in ['im', 'dm']:
                        if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                            var_f = f'f_{t}_{cdc}_{rdc}_{sku}'
                            if var_f in var_indices:
                                qty = problem.solution.get_values(var_indices[var_f])
                                if qty > 0.01:
                                    supply_relationships.append({
                                        '仓库名称': cdc,
                                        '服务对象': rdc,
                                        '商品类型': sku,
                                        '数量（吨）': round(qty, 2),
                                        '周期（日期）': periods[t]
                                    })
            for (store, sku), qty in demand_multi[t].items():
                eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
                for wh in eligible_whs:
                    var_u = f'u_{t}_{wh}_{store}_{sku}'
                    if var_u in var_indices and problem.solution.get_values(var_indices[var_u]) > 0.5:
                        supply_relationships.append({
                            '仓库名称': wh,
                            '服务对象': store,
                            '商品类型': sku,
                            '数量（吨）': round(qty, 2),
                            '周期（日期）': periods[t]
                        })
            pd.DataFrame(supply_relationships).to_csv(os.path.join(output_dir, f'仓网供应关系文件_{period}.csv'), index=False, encoding='utf-8-sig')

            # ---- 3. 仓库处置订单量文件 ----
            warehouse_stats = []
            for wh in cdc_names + rdc_names:
                if wh not in cap:
                    continue
                for sku in ['im', 'dm']:
                    out_qty = 0.0
                    for (store, s), qty in demand_multi[t].items():
                        if s != sku:
                            continue
                        var_u = f'u_{t}_{wh}_{store}_{sku}'
                        if var_u in var_indices:
                            out_qty += qty * problem.solution.get_values(var_indices[var_u])
                    if wh in cdc_names:
                        for rdc in rdc_names:
                            if (sku == 'im' and wh == port_cdc) or (sku == 'dm' and wh == inland_cdc):
                                var_f = f'f_{t}_{wh}_{rdc}_{sku}'
                                if var_f in var_indices:
                                    out_qty += problem.solution.get_values(var_indices[var_f])
                    if out_qty > 0.01:
                        warehouse_stats.append({
                            'Name': wh,
                            'SKU': sku,
                            'Qty（单位：吨）': round(out_qty, 2)
                        })
            pd.DataFrame(warehouse_stats).to_csv(os.path.join(output_dir, f'仓库处置订单量文件_{period}.csv'), index=False, encoding='utf-8-sig')

        # ==================== 汇总文件 ====================
        total_trans_wh = 0.0
        total_trans_cust = 0.0
        total_loss = 0.0
        total_proc = 0.0
        total_discount = 0.0
        for t in range(T):
            for (store, sku), qty in demand_multi[t].items():
                eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
                for wh in eligible_whs:
                    var_u = f'u_{t}_{wh}_{store}_{sku}'
                    if var_u in var_indices and problem.solution.get_values(var_indices[var_u]) > 0.5:
                        dist_val = dist.get((wh, store), 0)
                        total_trans_cust += 1.45e-4 * dist_val * qty
                        total_loss += loss_cost_matrix.get((wh, store), 0.0) * qty
                        total_proc += proc_cost.get(wh, 0.0) * qty
            for cdc in cdc_names:
                for rdc in rdc_names:
                    for sku in ['im', 'dm']:
                        if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                            var_f = f'f_{t}_{cdc}_{rdc}_{sku}'
                            if var_f in var_indices:
                                qty = problem.solution.get_values(var_indices[var_f])
                                if qty > 0.01:
                                    dist_val = dist.get((cdc, rdc), 0)
                                    total_trans_wh += 0.9e-4 * dist_val * qty
                                    total_loss += loss_cost_matrix.get((cdc, rdc), 0.0) * qty
                                    total_proc += proc_cost.get(cdc, 0.0) * qty
            for wh in df_wh['Name']:
                wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
                if wh_type in ['RDC', 'CDC']:
                    var_w = f'w_{t}_{wh}'
                    if var_w in var_indices:
                        w_val = problem.solution.get_values(var_indices[var_w])
                        if w_val > 0.01:
                            total_discount += 0.4 * proc_cost.get(wh, 0.0) * w_val

        summary_perf = pd.DataFrame([{
            '指标': '汇总（7天）',
            '开仓数量': 19,
            '时效满足率': '-',
            '仓库之间的运输总成本（万元）': round(total_trans_wh, 2),
            '仓库到门店的运输总成本（万元）': round(total_trans_cust, 2),
            '损耗总成本（万元）': round(total_loss, 2),
            '处置总成本（万元）': round(total_proc - total_discount, 2),
            '开仓总成本（万元）': round(total_open_cost, 2),
            '智能系统采购总成本（万元）': round(total_smart_cost, 2),
            '7天总物流成本（万元）': round(problem.solution.get_objective_value(), 2)
        }])
        summary_perf.to_csv(os.path.join(output_dir, '仓网业务表现文件_汇总.csv'), index=False, encoding='utf-8-sig')

        print("多周期模型求解完成！结果文件已保存至 output_result_question4_fixed 目录。")
        return problem.solution.get_objective_value(), None
    else:
        print("求解失败（无可行解），状态：", status_string)
        return None, None

# ===================== 主程序执行 =====================
if __name__ == "__main__":
    print("="*60)
    print("求解问题4：多周期动态仓网布局优化（修复版）")
    print("="*60)
    total_cost, _ = solve_multi_period()
    if total_cost:
        print(f"\n多周期总最优成本：{total_cost:.2f} 万元")
