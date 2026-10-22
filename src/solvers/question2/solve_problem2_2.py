# -*- coding: utf-8 -*-
"""
对应论文文档: 问题2.md （文件: 问题2.md）
子问 2.2 (补贴) 公式对照与要点
    - 补贴变量 s_j（或 s_{area}）在目标中影响企业净成本: 企业成本 - \sum_j s_j
    - 预算约束示例: \sum_j s_j ≤ B
    - 代码中相关变量: `subsidy_vars`, 补贴约束与 `apply_subsidy` 分支

实现提示:
    - 输出对比表 `results/question2/开仓补贴政策对比_cplex.csv` 包含企业/社会成本与补贴额，适合在论文中呈现政策效果。
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _runtime_sys
_runtime_sys.path.insert(0, str(_REPO_ROOT))
from src.runtime import results_root as _results_root, read_forecast as _read_forecast, configure_solver as _configure_solver, record_solver as _record_solver
_RESULTS_ROOT = _results_root()
from src.subsidy_support import subsidy_rows

import pandas as pd
import cplex
import os

# 设置数据文件路径
input_dir = str(_REPO_ROOT / 'data/raw')

# 读取数据
df_customer = pd.read_csv(os.path.join(input_dir, 'df_customer.csv'))
df_wh = pd.read_csv(os.path.join(input_dir, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(input_dir, 'df_matrix.csv'))
df_order = pd.read_csv(os.path.join(input_dir, 'df_order.csv'))
df_proc = pd.read_csv(os.path.join(input_dir, 'df_proc.csv'))

# 数据预处理
# 1. 识别CDC和RDC
cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()

# 2. 识别港口CDC和内陆CDC（根据名称判断）
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

# 3. 门店需求
demand = {}
for _, row in df_order.iterrows():
    demand[(row['Name'], row['SKU'])] = row['qty']

# 4. 门店到城市的映射
store_city_map = {}
for _, row in df_customer.iterrows():
    store_city_map[row['Name']] = row['Location']

# 5. 距离矩阵
dist = {}
time_matrix = {}
for _, row in df_matrix.iterrows():
    dist[(row['From'], row['To'])] = row['Distance']
    time_matrix[(row['From'], row['To'])] = row['Duration']

# 6. 仓库参数
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

# 7. 获取所有门店名称
customers = df_customer['Name'].tolist()

# 8. 整理配送矩阵
valid_routes = df_matrix[(df_matrix['From'].isin(df_wh['Name'])) & \
                         ((df_matrix['To'].isin(df_wh['Name'])) | df_matrix['To'].isin(customers))]

def solve_model_with_subsidy(apply_subsidy=False):
    """求解模型，可以选择是否应用补贴政策"""
    
    # 创建CPLEX模型
    problem = cplex.Cplex()
    problem.objective.set_sense(problem.objective.sense.minimize)

    # ========== 决策变量 ==========
    y_indices = {}  # 仓库开设
    z_indices = {}  # 智能系统采购
    u_indices = {}  # 服务关系
    v_indices = {}  # 时效满足
    f_indices = {}  # 调拨量
    w_indices = {}  # 线性化辅助变量
    
    # 新增变量用于补贴
    subsidy_vars = {}  # 补贴相关变量

    # 仓库开设变量
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            var_name = f'y_{wh}'
            lb = 1.0 if wh in cdc_names else 0.0  # CDC必开
            ub = 1.0
            obj = open_cost.get(wh, 0.0)
            problem.variables.add(obj=[obj], lb=[lb], ub=[ub], types=[problem.variables.type.binary], names=[var_name])
            y_indices[wh] = len(y_indices)

    # 智能系统变量
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            var_name = f'z_{wh}'
            obj = 1.5  # 智能系统成本
            problem.variables.add(obj=[obj], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
            z_indices[wh] = len(z_indices) + len(y_indices)

    # 服务关系变量
    u_vars_start_idx = len(y_indices) + len(z_indices)
    u_count = 0
    for _, row in df_order.iterrows():
        store = row['Name']
        sku = row['SKU']
        # 确定可服务的仓库集合
        if sku == 'im':
            eligible_whs = [port_cdc] + rdc_names
        else:  # dm
            eligible_whs = [inland_cdc] + rdc_names
        
        for wh in eligible_whs:
            dist_val = dist.get((wh, store), 0)
            qty_val = demand.get((store, sku), 0)
            p_cost = proc_cost.get(wh, 0)

            cost = (1.45e-4 * dist_val * qty_val) + (p_cost * qty_val)

            problem.variables.add(
                obj=[cost], 
                lb=[0.0], 
                ub=[1.0], 
                types=[problem.variables.type.binary], 
                names=[f'u_{wh}_{store}_{sku}']
            )
            u_indices[(wh, store, sku)] = u_vars_start_idx + u_count
            u_count += 1

    # 时效满足变量
    v_vars_start_idx = u_vars_start_idx + u_count
    v_count = 0
    for _, row in df_order.iterrows():
        store = row['Name']
        sku = row['SKU']
        var_name = f'v_{store}_{sku}'
        problem.variables.add(obj=[0.0], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
        v_indices[(store, sku)] = v_vars_start_idx + v_count
        v_count += 1

    # 调拨量变量
    f_vars_start_idx = v_vars_start_idx + v_count
    f_count = 0
    for cdc in cdc_names:
        for rdc in rdc_names:
            for sku in ['im', 'dm']:
                if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                    var_name = f'f_{cdc}_{rdc}_{sku}'
                    dist_val = dist.get((cdc, rdc), 0)
                    p_cost_cdc = proc_cost.get(cdc, 0)
                    cost = (0.9e-4 * dist_val) + (p_cost_cdc)
                    problem.variables.add(obj=[cost], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
                    f_indices[(cdc, rdc, sku)] = f_vars_start_idx + f_count
                    f_count += 1

    # 线性化辅助变量
    w_vars_start_idx = f_vars_start_idx + f_count
    w_count = 0
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            var_name = f'w_{wh}'
            p_cost = proc_cost.get(wh, 0)
            discount_coeff = -0.4 * p_cost
            problem.variables.add(obj=[discount_coeff], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
            w_indices[wh] = w_vars_start_idx + w_count
            w_count += 1

    # ========== 补贴相关变量 ==========
    if apply_subsidy:
        subsidy_start_idx = w_vars_start_idx + w_count
        
        # 变量：开仓总数
        problem.variables.add(obj=[0.0], lb=[0.0], ub=[cplex.infinity], 
                             types=[problem.variables.type.continuous], 
                             names=['total_open'])
        total_open_idx = subsidy_start_idx
        subsidy_vars['total_open'] = total_open_idx
        
        # 变量：是否达到补贴门槛（二进制变量）
        problem.variables.add(obj=[0.0], lb=[0.0], ub=[1.0], 
                             types=[problem.variables.type.binary], 
                             names=['subsidy_indicator'])
        subsidy_indicator_idx = subsidy_start_idx + 1
        subsidy_vars['subsidy_indicator'] = subsidy_indicator_idx
        
        # 变量：超过门槛的仓库数
        problem.variables.add(obj=[-7.0], lb=[0.0], ub=[cplex.infinity],  # 目标函数系数为-7，表示补贴减少成本
                             types=[problem.variables.type.continuous], 
                             names=['excess_warehouses'])
        excess_warehouses_idx = subsidy_start_idx + 2
        subsidy_vars['excess_warehouses'] = excess_warehouses_idx

    # ========== 约束条件 ==========
    constraint_count = 0
    
    # 1. 单源服务约束
    for _, row in df_order.iterrows():
        store = row['Name']
        sku = row['SKU']
        eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        
        indices = []
        values = []
        for wh in eligible_whs:
            if (wh, store, sku) in u_indices:
                indices.append(u_indices[(wh, store, sku)])
                values.append(1.0)
        
        if indices:
            problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['E'], rhs=[1.0], names=[f'single_source_{constraint_count}'])
            constraint_count += 1

    # 2. 仓库开设与服务关系
    for (wh, store, sku) in u_indices.keys():
        row = [[u_indices[(wh, store, sku)], y_indices[wh]], [1.0, -1.0]]
        problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'service_open_{constraint_count}'])
        constraint_count += 1

    # 3. RDC流量平衡
    M = df_order['qty'].sum()
    for rdc in rdc_names:
        for sku in ['im', 'dm']:
            lhs_indices = []
            lhs_values = []
            
            for store in df_order['Name'].unique():
                if (rdc, store, sku) in u_indices:
                    lhs_indices.append(u_indices[(rdc, store, sku)])
                    lhs_values.append(demand.get((store, sku), 0.0))
            
            if sku == 'im':
                cdc = port_cdc
            else:
                cdc = inland_cdc
                
            if (cdc, rdc, sku) in f_indices:
                lhs_indices.append(f_indices[(cdc, rdc, sku)])
                lhs_values.append(-1.0)
            
            if lhs_indices:
                problem.linear_constraints.add(lin_expr=[[lhs_indices, lhs_values]], senses=['E'], rhs=[0.0], names=[f'balance_{constraint_count}'])
                constraint_count += 1

    # 4. 容量约束
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type not in ['RDC', 'CDC']:
            continue
        
        lhs_indices = []
        lhs_values = []
        
        if wh in cdc_names:
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (wh, rdc, sku) in f_indices:
                        lhs_indices.append(f_indices[(wh, rdc, sku)])
                        lhs_values.append(1.0)
            
            for store in df_order['Name'].unique():
                for sku in ['im', 'dm']:
                    if (wh, store, sku) in u_indices:
                        lhs_indices.append(u_indices[(wh, store, sku)])
                        lhs_values.append(demand.get((store, sku), 0.0))
        else:
            for store in df_order['Name'].unique():
                for sku in ['im', 'dm']:
                    if (wh, store, sku) in u_indices:
                        lhs_indices.append(u_indices[(wh, store, sku)])
                        lhs_values.append(demand.get((store, sku), 0.0))
        
        lhs_indices.append(y_indices[wh])
        lhs_values.append(-cap[wh])
        
        if lhs_indices:
            problem.linear_constraints.add(lin_expr=[[lhs_indices, lhs_values]], senses=['L'], rhs=[0.0], names=[f'capacity_{constraint_count}'])
            constraint_count += 1

    # 5. 线性化约束
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            out_indices = []
            out_values = []
            
            for store in df_customer['Name']:
                for sku in ['im', 'dm']:
                    if (wh, store, sku) in u_indices:
                        out_indices.append(u_indices[(wh, store, sku)])
                        out_values.append(demand.get((store, sku), 0.0))
            
            if wh in cdc_names:
                for rdc in rdc_names:
                    for sku in ['im', 'dm']:
                        if (wh, rdc, sku) in f_indices:
                            out_indices.append(f_indices[(wh, rdc, sku)])
                            out_values.append(1.0)
            
            if out_indices:
                row1 = [[w_indices[wh]] + out_indices, [1.0] + [-v for v in out_values]]
                problem.linear_constraints.add(lin_expr=[row1], senses=['L'], rhs=[0.0], 
                                             names=[f'w_max_out_{wh}'])
                
                M_val = cap.get(wh, 100000) 
                row2 = [[w_indices[wh], z_indices[wh]], [1.0, -M_val]]
                problem.linear_constraints.add(lin_expr=[row2], senses=['L'], rhs=[0.0], 
                                             names=[f'w_limit_by_z_{wh}'])

    # 6. 时效约束
    time_limit_minutes = 600  # 10小时 = 600分钟
    satisfaction_rate = 0.95  # 95%
    total_demand = df_order['qty'].sum()
    satisfied_demand_indices = []
    satisfied_demand_values = []

    for (store, sku) in v_indices.keys():
        eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        
        for wh in eligible_whs:
            if (wh, store, sku) in u_indices:
                travel_time = time_matrix.get((wh, store), float('inf'))
                if travel_time <= time_limit_minutes:
                    row = [[v_indices[(store, sku)], u_indices[(wh, store, sku)]], [-1.0, 1.0]]
                    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'time1_{constraint_count}'])
                    constraint_count += 1
                else:
                    row = [[v_indices[(store, sku)], u_indices[(wh, store, sku)]], [1.0, 1.0]]
                    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[1.0], names=[f'time2_{constraint_count}'])
                    constraint_count += 1
        
        satisfied_demand_indices.append(v_indices[(store, sku)])
        satisfied_demand_values.append(demand.get((store, sku), 0.0))

    # 整体时效约束
    satisfied_demand = [[satisfied_demand_indices, satisfied_demand_values]]
    problem.linear_constraints.add(lin_expr=satisfied_demand, senses=['G'], rhs=[satisfaction_rate * total_demand], names=[f'overall_time_window_{constraint_count}'])
    constraint_count += 1

    # 7. 智能系统采购约束
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            row = [[z_indices[wh], y_indices[wh]], [1.0, -1.0]]
            problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'system_{constraint_count}'])
            constraint_count += 1

    # 8. 补贴相关约束
    if apply_subsidy:
        # 8.1 开仓总数 = 所有y_i的和
        y_indices_list = list(y_indices.values())
        # 这里使用线性表达式来建立约束
        problem.linear_constraints.add(
            lin_expr=[[[subsidy_vars['total_open']] + y_indices_list, [-1.0] + [1.0]*len(y_indices_list)]],
            senses=['E'],
            rhs=[0.0],
            names=['total_open_constraint']
        )
        constraint_count += 1
        
        # count includes both CDCs. Preserve the current excess=max(count-10, 0) policy.
        for indices, coefficients, sense, rhs in subsidy_rows(
                subsidy_vars['total_open'], subsidy_vars['subsidy_indicator'],
                subsidy_vars['excess_warehouses'], len(y_indices)):
            problem.linear_constraints.add(lin_expr=[[indices, coefficients]], senses=[sense], rhs=[rhs])
            constraint_count += 1

    print(f"总变量数: {problem.variables.get_num()}")
    print(f"总约束数: {constraint_count}")

    # ========== 求解 ==========
    print("求解模型...")
    _configure_solver(problem)
    problem.solve()
    _record_solver(problem)
    # 输出求解状态
    status_string = problem.solution.get_status_string()
    print(f"求解状态: {status_string}")

    # 检查求解状态
    if problem.solution.is_primal_feasible():
        print(f'当前可行解目标: {problem.solution.get_objective_value():.2f} 万元')
        
        # ========== 结果提取 ==========
        valid_whs = [wh for wh in df_wh['Name'] if wh in cap]
        total_demand_val = sum(demand.values())

        # 1. 统计开仓数量
        open_wh_count = sum(1 for wh in valid_whs if problem.solution.get_values(y_indices[wh]) > 0.5)
        
        # 2. 计算时效满足率
        satisfied_demand_val = sum(demand.get((store, sku), 0.0) * problem.solution.get_values(v_indices[(store, sku)])
                                   for (store, sku) in v_indices.keys())
        satisfied_rate = satisfied_demand_val / total_demand_val
        
        # 3. 运输成本：仓库间调拨
        transport_wh = sum(0.9e-4 * dist.get((cdc, rdc), 0) * problem.solution.get_values(f_indices[(cdc, rdc, sku)]) 
                           for (cdc, rdc, sku) in f_indices.keys())
        
        # 4. 运输成本：仓库到门店
        transport_cust = sum(1.45e-4 * dist.get((wh, store), 0) * demand.get((store, sku), 0) * problem.solution.get_values(u_indices[(wh, store, sku)])
                             for (wh, store, sku) in u_indices.keys())
        
        # 5. 开仓总成本
        opening_cost_total = sum(open_cost[wh] * problem.solution.get_values(y_indices[wh]) for wh in valid_whs)

        # 6. 智能系统采购成本
        smart_system_cost = sum(1.5 * problem.solution.get_values(z_indices[wh]) for wh in valid_whs if wh in z_indices)

        # 7. 处置总成本（扣除折扣）
        processing_total_cost = 0.0
        warehouse_stats = [] # 用于附件10

        for wh in valid_whs:
            if problem.solution.get_values(y_indices[wh]) < 0.5:
                continue
                
            # 计算该仓的出库量
            out_qty_dm = 0.0
            out_qty_im = 0.0
            
            # 配送量
            for store in df_customer['Name']:
                if (wh, store, 'dm') in u_indices:
                    out_qty_dm += demand.get((store, 'dm'), 0) * problem.solution.get_values(u_indices[(wh, store, 'dm')])
                if (wh, store, 'im') in u_indices:
                    out_qty_im += demand.get((store, 'im'), 0) * problem.solution.get_values(u_indices[(wh, store, 'im')])
            
            # 调拨发出量（如果是CDC）
            if wh in cdc_names:
                for rdc in rdc_names:
                    if (wh, rdc, 'dm') in f_indices:
                        out_qty_dm += problem.solution.get_values(f_indices[(wh, rdc, 'dm')])
                    if (wh, rdc, 'im') in f_indices:
                        out_qty_im += problem.solution.get_values(f_indices[(wh, rdc, 'im')])
            
            # 记录附件10数据
            qty_total_wh = (out_qty_dm + out_qty_im)
            if out_qty_dm > 0: 
                warehouse_stats.append({'Name': wh, 'SKU': 'dm', 'Qty（单位：吨）': out_qty_dm})
            if out_qty_im > 0: 
                warehouse_stats.append({'Name': wh, 'SKU': 'im', 'Qty（单位：吨）': out_qty_im})
            
            # 计算该仓处置费（扣除系统折扣）
            z_val = problem.solution.get_values(z_indices[wh])
            actual_proc = proc_cost[wh] * qty_total_wh * (1 - 0.4 * z_val) 
            processing_total_cost += actual_proc

        # 8. 计算补贴金额和企业总成本
        if apply_subsidy:
            excess_warehouses_val = problem.solution.get_values(subsidy_vars['excess_warehouses'])
            subsidy_amount = 7.0 * excess_warehouses_val
            
            # 原总成本（不含补贴）
            original_total_cost = (transport_wh + transport_cust + opening_cost_total + 
                                 processing_total_cost + smart_system_cost)
            
            # 企业总成本 = 原总成本 - 补贴
            enterprise_total_cost = original_total_cost - subsidy_amount
            
            # 社会总成本 = 原总成本
            social_total_cost = original_total_cost
            
            print(f"开仓数量: {open_wh_count}")
            print(f"超过门槛仓库数: {excess_warehouses_val:.2f}")
            print(f"补贴金额: {subsidy_amount:.2f} 万元")
            print(f"企业总成本: {enterprise_total_cost:.2f} 万元")
            print(f"社会总成本: {social_total_cost:.2f} 万元")
        else:
            # 无补贴时，企业总成本 = 社会总成本 = 原总成本
            enterprise_total_cost = (transport_wh + transport_cust + opening_cost_total + 
                                   processing_total_cost + smart_system_cost)
            social_total_cost = enterprise_total_cost
            subsidy_amount = 0.0
        
        # 返回结果
        result = {
            '方案类型': '有补贴' if apply_subsidy else '无补贴',
            '开仓数量': open_wh_count,
            '时效满足率': satisfied_rate,
            '企业总物流成本（单位：万元）': enterprise_total_cost,
            '社会总成本（单位：万元）': social_total_cost,
            '补贴金额（单位：万元）': subsidy_amount,
            '仓库之间的运输总成本（单位：万元）': transport_wh,
            '仓库到门店的运输总成本（单位：万元）': transport_cust,
            '开仓总成本（单位：万元）': opening_cost_total,
            '出入仓处置总成本（单位：万元）': processing_total_cost,
            '智能调度系统采购总成本（单位：万元）': smart_system_cost,
            '求解状态': status_string
        }
        
        # 返回用于生成附件的中间数据
        attachment_data = {
            'warehouse_stats': warehouse_stats,
            'u_indices': u_indices,
            'f_indices': f_indices,
            'problem': problem,
            'y_indices': y_indices,
            'demand': demand,
            'store_city_map': store_city_map,
            'dist': dist,
            'proc_cost': proc_cost,
            'z_indices': z_indices
        }
        
        scenario = _RESULTS_ROOT / 'question2/subsidy_scenarios' / ('with_subsidy' if apply_subsidy else 'without_subsidy')
        scenario.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([result]).to_csv(scenario/'business.csv', index=False, encoding='utf-8-sig')
        pd.DataFrame(warehouse_stats).to_csv(scenario/'warehouse_quantities.csv', index=False, encoding='utf-8-sig')
        pd.DataFrame([{'Name': wh, 'open': int(problem.solution.get_values(y_indices[wh]) > 0.5),
                       'smart': int(problem.solution.get_values(z_indices[wh]) > 0.5)}
                      for wh in valid_whs]).to_csv(scenario/'decisions.csv', index=False, encoding='utf-8-sig')
        flows = [{'source': cdc, 'target': rdc, 'sku': sku, 'qty': problem.solution.get_values(index)}
                 for (cdc, rdc, sku), index in f_indices.items() if problem.solution.get_values(index) > 0.01]
        flows += [{'source': wh, 'target': store, 'sku': sku, 'qty': demand[store, sku]}
                  for (wh, store, sku), index in u_indices.items() if problem.solution.get_values(index) > 0.5]
        pd.DataFrame(flows).to_csv(scenario/'flows.csv', index=False, encoding='utf-8-sig')
        return result, attachment_data
    else:
        print(f'求解状态: {problem.solution.get_status_string()}')
        print('未找到最优解')
        return None, None

# ========== 主程序 ==========
print("="*60)
print("求解问题1（无补贴）...")
print("="*60)
result_no_subsidy, attachment_data_no_subsidy = solve_model_with_subsidy(apply_subsidy=False)

print("\n" + "="*60)
print("求解问题2第二小问（有补贴）...")
print("="*60)
result_with_subsidy, attachment_data_with_subsidy = solve_model_with_subsidy(apply_subsidy=True)

# ========== 输出结果表格 ==========
output_dir = str(_RESULTS_ROOT / 'question2')
os.makedirs(output_dir, exist_ok=True)

# 创建包含两个方案结果的DataFrame
if result_no_subsidy and result_with_subsidy:
    # 创建结果表格
    business_performance = pd.DataFrame([result_no_subsidy, result_with_subsidy])
    
    # 重新排列列顺序
    column_order = ['方案类型', '开仓数量', '时效满足率', '企业总物流成本（单位：万元）', 
                    '社会总成本（单位：万元）', '补贴金额（单位：万元）',
                    '仓库之间的运输总成本（单位：万元）', '仓库到门店的运输总成本（单位：万元）',
                    '开仓总成本（单位：万元）', '出入仓处置总成本（单位：万元）',
                    '智能调度系统采购总成本（单位：万元）', '求解状态']
    business_performance = business_performance[column_order]
    
    # 保存到文件
    business_performance.to_csv(os.path.join(output_dir, '开仓补贴政策对比_cplex.csv'), index=False, encoding='utf-8-sig')
    
    print("\n开仓补贴政策对比结果:")
    print("="*120)
    print(business_performance.to_string(index=False))
    print("="*120)
    print(f"结果已保存到: {os.path.join(output_dir, '开仓补贴政策对比_cplex.csv')}")
    
    # ========== 输出问题2第二小问的附件文件 ==========
    if attachment_data_with_subsidy:
        # --- 写入附件10（有补贴方案）---
        warehouse_stats_df = pd.DataFrame(attachment_data_with_subsidy['warehouse_stats'])
        warehouse_stats_df.to_csv(os.path.join(output_dir, '仓库处置订单量文件_有补贴_cplex.csv'), index=False, encoding='utf-8-sig')
        print(f"附件10（有补贴方案）已保存到: {os.path.join(output_dir, '仓库处置订单量文件_有补贴_cplex.csv')}")
        
        # --- 写入附件11（有补贴方案）---
        supply_relationships = []
        
        # 调拨关系
        for (cdc, rdc, sku), idx in attachment_data_with_subsidy['f_indices'].items():
            qty = attachment_data_with_subsidy['problem'].solution.get_values(idx)
            if qty > 0.01:
                supply_relationships.append({'Name': cdc, 'Customer': rdc, 'SKU': sku, 'Qty（单位：吨）': qty})
        
        # 配送关系
        u_indices_with_subsidy = attachment_data_with_subsidy['u_indices']
        for (wh, store, sku), idx in u_indices_with_subsidy.items():
            if attachment_data_with_subsidy['problem'].solution.get_values(idx) > 0.5:
                supply_relationships.append({'Name': wh, 'Customer': store_city_map[store], 'SKU': sku, 'Qty（单位：吨）': demand.get((store, sku), 0)})
        
        pd.DataFrame(supply_relationships).to_csv(os.path.join(output_dir, '仓网供应关系文件_有补贴_cplex.csv'), index=False, encoding='utf-8-sig')
        print(f"附件11（有补贴方案）已保存到: {os.path.join(output_dir, '仓网供应关系文件_有补贴_cplex.csv')}")
        
        print("\n问题2第二小问求解完成！")
    else:
        print("警告：有补贴方案的附件数据无法生成！")
else:
    print("警告：至少一个模型未能成功求解！")
    
# ========== 成本分析 ==========
if result_no_subsidy and result_with_subsidy:
    print("\n" + "="*60)
    print("成本分析:")
    print("="*60)
    
    # 计算成本变化
    cost_reduction = result_no_subsidy['企业总物流成本（单位：万元）'] - result_with_subsidy['企业总物流成本（单位：万元）']
    subsidy_effectiveness = cost_reduction / result_with_subsidy['补贴金额（单位：万元）'] if result_with_subsidy['补贴金额（单位：万元）'] > 0 else 0
    
    print(f"无补贴方案企业成本: {result_no_subsidy['企业总物流成本（单位：万元）']:.2f} 万元")
    print(f"有补贴方案企业成本: {result_with_subsidy['企业总物流成本（单位：万元）']:.2f} 万元")
    print(f"企业成本减少: {cost_reduction:.2f} 万元")
    print(f"补贴金额: {result_with_subsidy['补贴金额（单位：万元）']:.2f} 万元")
    print(f"补贴效率（每万元补贴减少的企业成本）: {subsidy_effectiveness:.2f}")
    print(f"社会总成本变化: {result_with_subsidy['社会总成本（单位：万元）'] - result_no_subsidy['社会总成本（单位：万元）']:.2f} 万元")
    
    # 开仓数量分析
    print(f"\n开仓数量变化: {result_with_subsidy['开仓数量'] - result_no_subsidy['开仓数量']} 个")
    print(f"无补贴方案开仓数: {result_no_subsidy['开仓数量']} 个")
    print(f"有补贴方案开仓数: {result_with_subsidy['开仓数量']} 个")
