from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _runtime_sys
_runtime_sys.path.insert(0, str(_REPO_ROOT))
from src.runtime import results_root as _results_root, read_forecast as _read_forecast, configure_solver as _configure_solver, record_solver as _record_solver
_RESULTS_ROOT = _results_root()
import pandas as pd
import cplex
import os
import numpy as np
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 基础数据读取（同前序题目，CDC/RDC识别、距离/时效矩阵、仓库参数等）
input_dir = str(_REPO_ROOT / 'data/raw')
output_dir = str(_RESULTS_ROOT / 'question4/problem4_noloss/output_result')
os.makedirs(output_dir, exist_ok=True)

df_customer = pd.read_csv(os.path.join(input_dir, 'df_customer.csv'))
df_wh = pd.read_csv(os.path.join(input_dir, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(input_dir, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(input_dir, 'df_proc.csv'))
df_demand_multi = _read_forecast()  # 第三题预测结果

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

def solve_multi_period_no_loss():
    # 创建CPLEX模型
    problem = cplex.Cplex()
    problem.objective.set_sense(problem.objective.sense.minimize)
    
    # ===================== CPLEX参数设置（减少gap） =====================
    # 设置MIP gap阈值（相对gap）
    problem.parameters.mip.tolerances.mipgap.set(0.0)
    
    # 设置绝对MIP gap阈值
    problem.parameters.mip.tolerances.absmipgap.set(0.0)
    
    # 设置求解器强调（强调找到最优解）
    problem.parameters.emphasis.mip.set(1)
    
    # 设置节点选择策略
    problem.parameters.mip.strategy.variableselect.set(3)
    
    # 设置最大求解时间（秒）
    problem.parameters.timelimit.set(60)
    
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
    
    # 3. 服务关系变量 u_t^(w,c,s)（不考虑损耗成本）
    for t in range(T):
        for (store, sku), qty in demand_multi[t].items():
            eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
            for wh in eligible_whs:
                var_name = f'u_{t}_{wh}_{store}_{sku}'
                # 目标函数系数：运输成本 + 处置成本（不含损耗成本）
                dist_val = dist.get((wh, store), 0)
                trans_cost = 1.45e-4 * dist_val * qty  # 仓库→门店运输成本（元→万元）
                proc_cost_val = proc_cost.get(wh, 0.0) * qty  # 处置成本（入库+出库）
                obj = trans_cost + proc_cost_val  # 不含损耗成本
                problem.variables.add(obj=[obj], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
                var_indices[var_name] = var_count
                var_count += 1
    
    # 4. 调拨量变量 f_t^(cdc,rdc,s)（不考虑损耗成本）
    for t in range(T):
        for cdc in cdc_names:
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                        var_name = f'f_{t}_{cdc}_{rdc}_{sku}'
                        # 目标函数系数：调拨运输成本 + CDC处置成本（不含损耗成本）
                        dist_val = dist.get((cdc, rdc), 0)
                        trans_cost = 0.9e-4 * dist_val  # 元→万元（每吨成本，后续乘以调拨量）
                        proc_cost_cdc = proc_cost.get(cdc, 0.0)  # CDC处置成本（每吨）
                        obj = trans_cost + proc_cost_cdc  # 不含损耗成本
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
    
    # 2. 智能系统采购约束：z^w ≤ sum(y_t^w)（仅开设过的仓库可采购）
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            var_z = f'z_{wh}'
            indices = [var_indices[var_z]] + [var_indices[f'y_{t}_{wh}'] for t in range(T)]
            # 只要存在任一周期 y_t^w=1 即允许采购：z^w <= sum_t y_t^w
            values = [1.0] + [-1.0 for t in range(T)]
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
    print("求解多周期模型（不考虑损耗成本）...")
    _configure_solver(problem)
    problem.solve()
    _record_solver(problem)
    # 输出求解状态
    status_string = problem.solution.get_status_string()
    print(f"求解状态: {status_string}")
    
    if "optimal" in status_string.lower():
        print(f'多周期总最优成本（不含损耗）: {problem.solution.get_objective_value():.2f} 万元')

        # ==================== 计算每天各项成本（参考solve_problem1格式） ====================
        # 开仓总成本（一次性）
        total_open_cost = 0.0
        for wh in rdc_names:
            for t_idx in range(T):
                var_open_new = f'open_new_{t_idx}_{wh}'
                if var_open_new in var_indices:
                    total_open_cost += open_cost.get(wh, 0.0) * problem.solution.get_values(var_indices[var_open_new])

        # 智能系统总成本（一次性）
        total_smart_cost = sum(1.5 * problem.solution.get_values(var_indices[f'z_{wh}']) for wh in df_wh['Name'] if f'z_{wh}' in var_indices)

        # ==================== 每天输出三个文件 ====================
        for t in range(T):
            period = periods[t].replace('/', '-')  # 日期格式处理

            # ---- 1. 仓网业务表现文件 ----
            # 开仓数量（含CDC）
            open_wh_count = 2
            open_wh_list = []
            for wh in rdc_names:
                var_y = f'y_{t}_{wh}'
                if var_y in var_indices and problem.solution.get_values(var_indices[var_y]) > 0.5:
                    open_wh_count += 1
                    open_wh_list.append(wh)

            # 时效满足率
            total_seafood_demand_t = sum(qty for (store, sku), qty in demand_multi[t].items() if sku in ['im', 'dm'])
            satisfied_seafood_demand_t = 0.0
            for (store, sku), qty in demand_multi[t].items():
                if sku in ['im', 'dm']:
                    var_v = f'v_{t}_{store}_{sku}'
                    if var_v in var_indices:
                        satisfied_seafood_demand_t += qty * problem.solution.get_values(var_indices[var_v])
            satisfied_rate_t = satisfied_seafood_demand_t / total_seafood_demand_t

            # 当天各项成本
            transport_wh_t = 0.0  # 仓库间运输
            transport_cust_t = 0.0  # 仓库到门店
            proc_cost_t = 0.0  # 处置成本
            discount_t = 0.0  # 智能系统折扣

            # 仓库到门店配送成本
            for (store, sku), qty in demand_multi[t].items():
                eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
                for wh in eligible_whs:
                    var_u = f'u_{t}_{wh}_{store}_{sku}'
                    if var_u in var_indices and problem.solution.get_values(var_indices[var_u]) > 0.5:
                        dist_val = dist.get((wh, store), 0)
                        transport_cust_t += 1.45e-4 * dist_val * qty
                        proc_cost_t += proc_cost.get(wh, 0.0) * qty

            # CDC到RDC调拨成本
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
                                    proc_cost_t += proc_cost.get(cdc, 0.0) * qty

            # 智能系统折扣（w变量）
            for wh in df_wh['Name']:
                wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
                if wh_type in ['RDC', 'CDC']:
                    var_w = f'w_{t}_{wh}'
                    if var_w in var_indices:
                        w_val = problem.solution.get_values(var_indices[var_w])
                        if w_val > 0.01:
                            discount_t += 0.4 * proc_cost.get(wh, 0.0) * w_val

            # 处置成本（扣折扣后）
            actual_proc_t = proc_cost_t - discount_t
            daily_total_cost = transport_wh_t + transport_cust_t + actual_proc_t

            open_cost_display = round(total_open_cost, 2) if t == 0 else '-'
            smart_cost_display = round(total_smart_cost, 2) if t == 0 else '-'
            daily_total_with_one_time = round(daily_total_cost + total_open_cost + total_smart_cost, 2) if t == 0 else round(daily_total_cost, 2)

            business_perf = pd.DataFrame([{
                '周期（日期）': periods[t],
                '开仓数量': open_wh_count,
                '时效满足率': round(satisfied_rate_t, 4),
                '仓库之间的运输总成本（万元）': round(transport_wh_t, 2),
                '仓库到门店的运输总成本（万元）': round(transport_cust_t, 2),
                '处置总成本（万元）': round(actual_proc_t, 2),
                '开仓总成本（万元）': open_cost_display,
                '智能系统采购总成本（万元）': smart_cost_display,
                '当天总成本（万元）': daily_total_with_one_time
            }])
            business_perf.to_csv(os.path.join(output_dir, f'仓网业务表现文件_{period}.csv'), index=False, encoding='utf-8-sig')

            # ---- 2. 仓网供应关系文件 ----
            supply_relationships = []
            # 调拨关系（CDC→RDC）
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
            # 配送关系（仓库→门店）
            for (store, sku), qty in demand_multi[t].items():
                eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
                for wh in eligible_whs:
                    var_u = f'u_{t}_{wh}_{store}_{sku}'
                    if var_u in var_indices and problem.solution.get_values(var_indices[var_u]) > 0.5:
                        supply_relationships.append({
                            '仓库名称': wh,
                            '服务对象': store_city_map.get(store, store),
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
                    # 配送量
                    for (store, s), qty in demand_multi[t].items():
                        if s != sku:
                            continue
                        var_u = f'u_{t}_{wh}_{store}_{sku}'
                        if var_u in var_indices:
                            out_qty += qty * problem.solution.get_values(var_indices[var_u])
                    # 调拨量（仅CDC）
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
                            'Qty（单位：吨）': round(out_qty, 2)  # 入库+出库
                        })
            pd.DataFrame(warehouse_stats).to_csv(os.path.join(output_dir, f'仓库处置订单量文件_{period}.csv'), index=False, encoding='utf-8-sig')

        # ==================== 汇总文件 ====================
        total_trans_wh = 0.0
        total_trans_cust = 0.0
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
                                    total_proc += proc_cost.get(cdc, 0.0) * qty
            for wh in df_wh['Name']:
                wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
                if wh_type in ['RDC', 'CDC']:
                    var_w = f'w_{t}_{wh}'
                    if var_w in var_indices:
                        w_val = problem.solution.get_values(var_indices[var_w])
                        if w_val > 0.01:
                            total_discount += 0.4 * proc_cost.get(wh, 0.0) * w_val

        # 开仓不关闭：周期末已开设的仓库数即整个计划期开设的仓库数，含两个 CDC
        final_open_wh_count = 2 + sum(
            1 for wh in rdc_names if f'y_{T-1}_{wh}' in var_indices
            and problem.solution.get_values(var_indices[f'y_{T-1}_{wh}']) > 0.5)

        summary_perf = pd.DataFrame([{
            '指标': '汇总（7天）',
            '开仓数量': final_open_wh_count,
            '时效满足率': '-',
            '仓库之间的运输总成本（万元）': round(total_trans_wh, 2),
            '仓库到门店的运输总成本（万元）': round(total_trans_cust, 2),
            '处置总成本（万元）': round(total_proc - total_discount, 2),
            '开仓总成本（万元）': round(total_open_cost, 2),
            '智能系统采购总成本（万元）': round(total_smart_cost, 2),
            '7天总物流成本（万元）': round(problem.solution.get_objective_value(), 2)
        }])
        summary_perf.to_csv(os.path.join(output_dir, '仓网业务表现文件_汇总.csv'), index=False, encoding='utf-8-sig')

        print("多周期模型求解完成！结果文件已保存至 output_result_question4_no_loss 目录。")
        return problem.solution.get_objective_value(), None
    else:
        print("求解失败，状态：", status_string)
        return None, None

# ===================== 主程序执行 =====================
if __name__ == "__main__":
    print("="*60)
    print("求解问题4：多周期动态仓网布局优化（不考虑损耗成本）")
    print("="*60)
    total_cost, _ = solve_multi_period_no_loss()
    if total_cost:
        print(f"\n多周期总最优成本（不含损耗）：{total_cost:.2f} 万元")
