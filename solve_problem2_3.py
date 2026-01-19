# -*- coding: utf-8 -*-
"""
Created on Fri Jan 16 21:44:57 2026

@author: 86173
"""

import pandas as pd
import cplex
import os
import numpy as np

# 设置数据文件路径
input_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data'

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

# 9. 计算每条路径的损耗成本系数（万元/吨）
def calculate_loss_cost(t):
    """根据运输时间计算损耗成本（万元/吨）"""
    if t <= 500:
        return 0.0
    else:
        # 0.2*(t-500)^2，转换为万元（乘以1e-4）
        return 0.2 * (t - 500) ** 2 * 1e-4

loss_cost_matrix = {}
for (from_point, to_point), t in time_matrix.items():
    loss_cost_matrix[(from_point, to_point)] = calculate_loss_cost(t)

def solve_with_transportation_loss():
    """求解考虑运输损耗成本的模型"""
    
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
            travel_time = time_matrix.get((wh, store), 0)
            
            # 基本运输成本：运输费 + 2.0倍处置费
            base_cost = (1.45e-4 * dist_val * qty_val) + (2.0 * p_cost * qty_val)
            
            # 运输损耗成本
            loss_cost_per_ton = loss_cost_matrix.get((wh, store), 0.0)
            loss_cost = loss_cost_per_ton * qty_val
            
            # 总成本 = 基本运输成本 + 运输损耗成本
            total_cost = base_cost + loss_cost

            problem.variables.add(
                obj=[total_cost], 
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
                    travel_time = time_matrix.get((cdc, rdc), 0)
                    
                    # 基本运输成本：运输费 + CDC的处置费(2倍)
                    base_cost = (0.9e-4 * dist_val) + (2.0 * p_cost_cdc)
                    
                    # 运输损耗成本（每吨）
                    loss_cost_per_ton = loss_cost_matrix.get((cdc, rdc), 0.0)
                    
                    # 总成本 = 基本运输成本 + 运输损耗成本
                    total_cost = base_cost + loss_cost_per_ton
                    
                    problem.variables.add(obj=[total_cost], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
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

    print(f"总变量数: {len(y_indices) + len(z_indices) + u_count + v_count + f_count + w_count}")

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

    print(f"总约束数: {constraint_count}")

    # ========== 求解 ==========
    print("求解模型...")
    problem.solve()

    # 输出求解状态
    status_string = problem.solution.get_status_string()
    print(f"求解状态: {status_string}")

    # 检查求解状态
    if "optimal" in status_string.lower():
        print(f'最优总成本: {problem.solution.get_objective_value():.2f} 万元')
        
        # ========== 结果提取与附件生成 ==========
        output_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/output_result'
        os.makedirs(output_dir, exist_ok=True)
        
        # 基础数据准备
        valid_whs = [wh for wh in df_wh['Name'] if wh in cap]
        total_demand_val = sum(demand.values())

        # 1. 统计开仓数量
        open_wh_count = sum(1 for wh in valid_whs if problem.solution.get_values(y_indices[wh]) > 0.5)
        
        # 2. 计算时效满足率
        satisfied_demand_val = sum(demand.get((store, sku), 0.0) * problem.solution.get_values(v_indices[(store, sku)])
                                   for (store, sku) in v_indices.keys())
        satisfied_rate = satisfied_demand_val / total_demand_val
        
        # 3. 运输成本分解：仓库间调拨
        transport_wh_basic = 0.0  # 基本运输费
        transport_wh_loss = 0.0   # 运输损耗成本
        transport_wh_total = 0.0  # 总成本
        
        for (cdc, rdc, sku), idx in f_indices.items():
            qty = problem.solution.get_values(idx)
            if qty > 0:
                dist_val = dist.get((cdc, rdc), 0)
                # 基本运输费
                basic_cost = 0.9e-4 * dist_val * qty
                # 运输损耗成本
                loss_cost_per_ton = loss_cost_matrix.get((cdc, rdc), 0.0)
                loss_cost = loss_cost_per_ton * qty
                
                transport_wh_basic += basic_cost
                transport_wh_loss += loss_cost
                transport_wh_total += basic_cost + loss_cost
        
        # 4. 运输成本分解：仓库到门店
        transport_cust_basic = 0.0  # 基本运输费
        transport_cust_loss = 0.0   # 运输损耗成本
        transport_cust_total = 0.0  # 总成本
        
        for (wh, store, sku), idx in u_indices.items():
            u_val = problem.solution.get_values(idx)
            if u_val > 0.5:
                qty_val = demand.get((store, sku), 0)
                dist_val = dist.get((wh, store), 0)
                # 基本运输费
                basic_cost = 1.45e-4 * dist_val * qty_val
                # 运输损耗成本
                loss_cost_per_ton = loss_cost_matrix.get((wh, store), 0.0)
                loss_cost = loss_cost_per_ton * qty_val
                
                transport_cust_basic += basic_cost
                transport_cust_loss += loss_cost
                transport_cust_total += basic_cost + loss_cost
        
        # 5. 开仓总成本
        opening_cost_total = sum(open_cost[wh] * problem.solution.get_values(y_indices[wh]) for wh in valid_whs)

        # 6. 智能系统采购成本
        smart_system_cost = sum(1.5 * problem.solution.get_values(z_indices[wh]) for wh in valid_whs if wh in z_indices)

        # 7. 处置总成本（扣除折扣）
        processing_total_cost = 0.0
        warehouse_stats = []  # 用于附件10

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
            qty_total_wh = 2.0 * (out_qty_dm + out_qty_im)
            if out_qty_dm > 0: 
                warehouse_stats.append({'Name': wh, 'SKU': 'dm', 'Qty（单位：吨）': 2.0 * out_qty_dm})
            if out_qty_im > 0: 
                warehouse_stats.append({'Name': wh, 'SKU': 'im', 'Qty（单位：吨）': 2.0 * out_qty_im})
            
            # 计算该仓处置费（扣除系统折扣）
            z_val = problem.solution.get_values(z_indices[wh])
            actual_proc = proc_cost[wh] * qty_total_wh * (1 - 0.4 * z_val) 
            processing_total_cost += actual_proc

        # 8. 总物流成本
        total_logistics_cost = (transport_wh_total + transport_cust_total + opening_cost_total + 
                               processing_total_cost + smart_system_cost)
        
        # 9. 总运输损耗成本
        total_loss_cost = transport_wh_loss + transport_cust_loss
        
        # --- 写入附件9（考虑运输损耗成本）---
        business_performance = pd.DataFrame({
            '开仓数量': [open_wh_count],
            '时效满足率': [satisfied_rate],
            '总物流成本（单位：万元）': [total_logistics_cost],
            '仓库之间的运输总成本（单位：万元）': [transport_wh_total],
            '仓库到门店的运输总成本（单位：万元）': [transport_cust_total],
            '开仓总成本（单位：万元）': [opening_cost_total],
            '出入仓处置总成本（单位：万元）': [processing_total_cost],
            '智能调度系统采购总成本（单位：万元）': [smart_system_cost],
            '运输损耗总成本（单位：万元）': [total_loss_cost]  # 新增列，用于记录运输损耗成本
        })
        business_performance.to_csv(os.path.join(output_dir, '仓网业务表现文件_运输损耗_cplex.csv'), index=False, encoding='utf-8-sig')

        # --- 写入附件10（考虑运输损耗成本）---
        pd.DataFrame(warehouse_stats).to_csv(os.path.join(output_dir, '仓库处置订单量文件_运输损耗_cplex.csv'), index=False, encoding='utf-8-sig')

        # --- 写入附件11（考虑运输损耗成本）---
        supply_relationships = []
        # 调拨关系
        for (cdc, rdc, sku), idx in f_indices.items():
            qty = problem.solution.get_values(idx)
            if qty > 0.01:
                supply_relationships.append({'Name': cdc, 'Customer': rdc, 'SKU': sku, 'Qty（单位：吨）': qty})
        # 配送关系
        for (wh, store, sku), idx in u_indices.items():
            if problem.solution.get_values(idx) > 0.5:
                supply_relationships.append({'Name': wh, 'Customer': store_city_map[store], 'SKU': sku, 'Qty（单位：吨）': demand.get((store, sku), 0)})
        
        pd.DataFrame(supply_relationships).to_csv(os.path.join(output_dir, '仓网供应关系文件_运输损耗_cplex.csv'), index=False, encoding='utf-8-sig')

        print("所有附件结果已成功保存至 output_result 文件夹！")
        
        # 返回结果用于对比分析
        result = {
            '方案类型': '考虑运输损耗',
            '开仓数量': open_wh_count,
            '时效满足率': satisfied_rate,
            '总物流成本（单位：万元）': total_logistics_cost,
            '仓库之间的运输总成本（单位：万元）': transport_wh_total,
            '仓库到门店的运输总成本（单位：万元）': transport_cust_total,
            '开仓总成本（单位：万元）': opening_cost_total,
            '出入仓处置总成本（单位：万元）': processing_total_cost,
            '智能调度系统采购总成本（单位：万元）': smart_system_cost,
            '运输损耗总成本（单位：万元）': total_loss_cost,
            '求解状态': status_string
        }
        
        attachment_data = {
            'warehouse_stats': warehouse_stats,
            'u_indices': u_indices,
            'f_indices': f_indices,
            'problem': problem,
            'demand': demand,
            'store_city_map': store_city_map
        }
        
        return result, attachment_data
    else:
        print(f'求解状态: {problem.solution.get_status_string()}')
        print('未找到最优解')
        return None, None

# ========== 主程序 ==========
print("="*60)
print("求解问题2第三小问（考虑运输损耗成本）...")
print("="*60)

result_loss, attachment_data_loss = solve_with_transportation_loss()

if result_loss:
    print("\n问题2第三小问求解完成！")
    print("\n考虑运输损耗成本的仓网业务表现:")
    print("="*120)
    for key, value in result_loss.items():
        if key != '方案类型' and key != '求解状态':
            print(f"{key}: {value}")
    print("="*120)
    
    # 输出文件位置
    output_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/output_result'
    print(f"\n结果文件已保存到 {output_dir} 目录:")
    print("1. 仓网业务表现文件_运输损耗_cplex.csv")
    print("2. 仓库处置订单量文件_运输损耗_cplex.csv")
    print("3. 仓网供应关系文件_运输损耗_cplex.csv")
else:
    print("模型求解失败，请检查代码和输入数据。") 