# -*- coding: utf-8 -*-
"""
Created on Fri Jan 16 19:39:13 2026

@author: 86173
"""

import pandas as pd
import cplex
import os
import itertools

# 设置数据文件路径
input_dir = 'c:/Users/86173/Desktop/ORcontest/2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data'

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

# 定义要遍历的参数组合
time_limits = [8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5]  # 小时
satisfaction_rates = [0.75, 0.80, 0.85, 0.90, 0.95, 0.98, 1.00]

# 将小时转换为分钟
time_limits_minutes = [t * 60 for t in time_limits]

# 存储所有结果
all_results = []

def solve_with_parameters(time_limit_minutes, satisfaction_rate):
    """求解给定参数组合的模型"""
    
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

            cost = (1.45e-4 * dist_val * qty_val) + (2.0 * p_cost * qty_val)

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
                    cost = (0.9e-4 * dist_val) + (2.0 * p_cost_cdc)
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
            discount_coeff = -0.8 * p_cost 
            problem.variables.add(obj=[discount_coeff], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
            w_indices[wh] = w_vars_start_idx + w_count
            w_count += 1

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

    # 6. 时效约束 - 使用传入的time_limit_minutes和satisfaction_rate
    total_demand = df_order['qty'].sum()
    satisfied_demand_indices = []
    satisfied_demand_values = []

    for (store, sku) in v_indices.keys():
        eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        
        for wh in eligible_whs:
            if (wh, store, sku) in u_indices:
                travel_time = time_matrix.get((wh, store), float('inf'))
                if travel_time <= time_limit_minutes:  # 使用传入的时效要求
                    row = [[v_indices[(store, sku)], u_indices[(wh, store, sku)]], [-1.0, 1.0]]
                    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'time1_{constraint_count}'])
                    constraint_count += 1
                else:
                    row = [[v_indices[(store, sku)], u_indices[(wh, store, sku)]], [1.0, 1.0]]
                    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[1.0], names=[f'time2_{constraint_count}'])
                    constraint_count += 1
        
        satisfied_demand_indices.append(v_indices[(store, sku)])
        satisfied_demand_values.append(demand.get((store, sku), 0.0))

    # 整体时效约束 - 使用传入的satisfaction_rate
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

    # ========== 求解 ==========
    problem.solve()
    
    # 检查求解状态
    status_string = problem.solution.get_status_string()
    
    if "optimal" in status_string.lower():
        # 提取业务表现指标
        valid_whs = [wh for wh in df_wh['Name'] if wh in cap]
        total_demand_val = sum(demand.values())
        
        # 1. 开仓数量
        open_wh_count = sum(1 for wh in valid_whs if problem.solution.get_values(y_indices[wh]) > 0.5)
        
        # 2. 实际时效满足率
        satisfied_demand_val = sum(demand.get((store, sku), 0.0) * problem.solution.get_values(v_indices[(store, sku)])
                                   for (store, sku) in v_indices.keys())
        actual_satisfaction_rate = satisfied_demand_val / total_demand_val
        
        # 3. 总物流成本
        total_cost = problem.solution.get_objective_value()
        
        # 4. 仓库间运输成本
        transport_wh = sum(0.9e-4 * dist.get((cdc, rdc), 0) * problem.solution.get_values(f_indices[(cdc, rdc, sku)]) 
                           for (cdc, rdc, sku) in f_indices.keys())
        
        # 5. 仓库到门店运输成本
        transport_cust = sum(1.45e-4 * dist.get((wh, store), 0) * demand.get((store, sku), 0) * problem.solution.get_values(u_indices[(wh, store, sku)])
                             for (wh, store, sku) in u_indices.keys())
        
        # 6. 开仓总成本
        opening_cost_total = sum(open_cost[wh] * problem.solution.get_values(y_indices[wh]) for wh in valid_whs)

        # 7. 智能系统采购成本
        smart_system_cost = sum(1.5 * problem.solution.get_values(z_indices[wh]) for wh in valid_whs if wh in z_indices)

        # 8. 处置总成本（扣除折扣）
        processing_total_cost = 0.0
        for wh in valid_whs:
            if problem.solution.get_values(y_indices[wh]) < 0.5:
                continue
                
            out_qty_dm = 0.0
            out_qty_im = 0.0
            
            for store in df_customer['Name']:
                if (wh, store, 'dm') in u_indices:
                    out_qty_dm += demand.get((store, 'dm'), 0) * problem.solution.get_values(u_indices[(wh, store, 'dm')])
                if (wh, store, 'im') in u_indices:
                    out_qty_im += demand.get((store, 'im'), 0) * problem.solution.get_values(u_indices[(wh, store, 'im')])
            
            if wh in cdc_names:
                for rdc in rdc_names:
                    if (wh, rdc, 'dm') in f_indices:
                        out_qty_dm += problem.solution.get_values(f_indices[(wh, rdc, 'dm')])
                    if (wh, rdc, 'im') in f_indices:
                        out_qty_im += problem.solution.get_values(f_indices[(wh, rdc, 'im')])
            
            qty_total_wh = 2.0 * (out_qty_dm + out_qty_im)
            z_val = problem.solution.get_values(z_indices[wh])
            actual_proc = proc_cost[wh] * qty_total_wh * (1 - 0.4 * z_val) 
            processing_total_cost += actual_proc
        
        # 返回结果
        return {
            '时效要求(h)': time_limit_minutes / 60,
            '时效满足率要求': satisfaction_rate,
            '实际时效满足率': actual_satisfaction_rate,
            '开仓数量': open_wh_count,
            '总物流成本(万元)': total_cost,
            '仓库间运输成本(万元)': transport_wh,
            '仓库到门店运输成本(万元)': transport_cust,
            '开仓总成本(万元)': opening_cost_total,
            '出入仓处置总成本(万元)': processing_total_cost,
            '智能系统采购总成本(万元)': smart_system_cost,
            '求解状态': status_string
        }
    else:
        # 如果无解，返回空结果
        return {
            '时效要求(h)': time_limit_minutes / 60,
            '时效满足率要求': satisfaction_rate,
            '实际时效满足率': None,
            '开仓数量': None,
            '总物流成本(万元)': None,
            '仓库间运输成本(万元)': None,
            '仓库到门店运输成本(万元)': None,
            '开仓总成本(万元)': None,
            '出入仓处置总成本(万元)': None,
            '智能系统采购总成本(万元)': None,
            '求解状态': status_string
        }

# 遍历所有参数组合
print("开始求解不同参数组合下的模型...")
total_combinations = len(time_limits_minutes) * len(satisfaction_rates)
current = 0

for time_limit_minutes in time_limits_minutes:
    for satisfaction_rate in satisfaction_rates:
        current += 1
        print(f"正在求解: 时效要求={time_limit_minutes/60}h, 时效满足率要求={satisfaction_rate*100}% ({current}/{total_combinations})")
        
        result = solve_with_parameters(time_limit_minutes, satisfaction_rate)
        all_results.append(result)

# 将结果转换为DataFrame
results_df = pd.DataFrame(all_results)

# 重新排列列顺序，使其更易读
column_order = ['时效要求(h)', '时效满足率要求', '实际时效满足率', '开仓数量', '总物流成本(万元)', 
                '仓库间运输成本(万元)', '仓库到门店运输成本(万元)', '开仓总成本(万元)', 
                '出入仓处置总成本(万元)', '智能系统采购总成本(万元)', '求解状态']
results_df = results_df[column_order]

# 保存结果到CSV文件
output_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/output_result'
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, '时效与成本关系分析.csv')
results_df.to_csv(output_file, index=False, encoding='utf-8-sig')

print(f"\n所有参数组合求解完成！")
print(f"结果已保存到: {output_file}")

# 打印结果摘要
print("\n结果摘要:")
print("=" * 120)
print(results_df.to_string(index=False))
print("=" * 120)

# 保存一个简化的版本，只包含关键指标
summary_df = results_df[['时效要求(h)', '时效满足率要求', '开仓数量', '总物流成本(万元)', '实际时效满足率']]
summary_file = os.path.join(output_dir, '时效与成本关系分析_摘要.csv')
summary_df.to_csv(summary_file, index=False, encoding='utf-8-sig')
print(f"结果摘要已保存到: {summary_file}")