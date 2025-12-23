import pandas as pd
import cplex
import os

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
print(f"港口CDC: {port_cdc}")
print(f"内陆CDC: {inland_cdc}")

# 3. 门店需求
demand = {}
for _, row in df_order.iterrows():
    demand[(row['Name'], row['SKU'])] = row['qty']

# 4. 门店到城市的映射
store_city_map = {}
for _, row in df_customer.iterrows():
    store_city_map[row['Name']] = row['Location']

# 4. 距离矩阵
dist = {}
time_matrix = {}
for _, row in df_matrix.iterrows():
    dist[(row['From'], row['To'])] = row['Distance']
    time_matrix[(row['From'], row['To'])] = row['Duration']

# 5. 仓库参数 - 只包含RDC和CDC类型
cap = {}; open_cost = {}; proc_cost = {}
# 先从df_proc获取所有参数
proc_dict = {}
for _, row in df_proc.iterrows():
    proc_dict[row['Name']] = {
        'Capacity': row['Capacity'],
        'Opening_fee': row['Opening_fee'],
        'Processing_fee': row['Processing_fee']
    }

# 然后只处理RDC和CDC类型的仓库
for _, row in df_wh.iterrows():
    wh_name = row['Name']
    wh_type = row['Type']
    if wh_type in ['RDC', 'CDC'] and wh_name in proc_dict:
        cap[wh_name] = proc_dict[wh_name]['Capacity']
        open_cost[wh_name] = proc_dict[wh_name]['Opening_fee']
        proc_cost[wh_name] = proc_dict[wh_name]['Processing_fee']

# 6. 获取所有门店名称
customers = df_customer['Name'].tolist()

# 7. 整理配送矩阵
valid_routes = df_matrix[(df_matrix['From'].isin(df_wh['Name'])) & \
                         ((df_matrix['To'].isin(df_wh['Name'])) | df_matrix['To'].isin(customers))]

# 创建CPLEX模型
problem = cplex.Cplex()
problem.objective.set_sense(problem.objective.sense.minimize)

# ========== 决策变量 ==========
# 变量名称到索引的映射
y_indices = {}  # 仓库开设
z_indices = {}  # 智能系统采购
u_indices = {}  # 服务关系
v_indices = {}  # 时效满足
f_indices = {}  # 调拨量
w_indices = {}  # 线性化辅助变量

# 仓库开设变量 - 只包含RDC和CDC类型
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
        var_name = f'y_{wh}'
        lb = 1.0 if wh in cdc_names else 0.0  # CDC必开
        ub = 1.0
        obj = open_cost.get(wh, 0.0)
        problem.variables.add(obj=[obj], lb=[lb], ub=[ub], types=[problem.variables.type.binary], names=[var_name])
        y_indices[wh] = len(y_indices)

# 智能系统变量 - 只包含RDC和CDC类型
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
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
        var_name = f'u_{wh}_{store}_{sku}'
        # 计算运输成本系数: 1.45/10000 * distance * demand
        cost = 1.45/10000 * dist.get((wh, store), 0) * demand.get((store, sku), 0)
        problem.variables.add(obj=[cost], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
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
            # 检查调拨是否允许
            if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                var_name = f'f_{cdc}_{rdc}_{sku}'
                # 计算运输成本系数: 0.9/10000 * distance
                cost = 0.9/10000 * dist.get((cdc, rdc), 0)
                problem.variables.add(obj=[cost], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
                f_indices[(cdc, rdc, sku)] = f_vars_start_idx + f_count
                f_count += 1

# 线性化辅助变量 - 只包含RDC和CDC类型
w_vars_start_idx = f_vars_start_idx + f_count
w_count = 0
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
        var_name = f'w_{wh}'
        # w变量是线性化辅助变量，用于实现智能系统的折扣效果
        # 不直接在目标函数中设置系数，而是通过约束条件控制其取值
        problem.variables.add(obj=[0.0], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
        w_indices[wh] = w_vars_start_idx + w_count
        w_count += 1

print(f"总变量数: {len(y_indices) + len(z_indices) + u_count + v_count + f_count + w_count}")

# ========== 约束条件 ==========
# 1. 单源服务约束
constraint_count = 0
for _, row in df_order.iterrows():
    store = row['Name']
    sku = row['SKU']
    eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
    
    # 收集所有u变量
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
    # u_wh_store_sku <= y_wh
    row = [[u_indices[(wh, store, sku)], y_indices[wh]], [1.0, -1.0]]
    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'service_open_{constraint_count}'])
    constraint_count += 1

# 3. RDC流量平衡
M = df_order['qty'].sum()  # 大M
for rdc in rdc_names:
    for sku in ['im', 'dm']:
        # 计算RDC的总配送量
        lhs_indices = []
        lhs_values = []
        
        # 从RDC出发的配送
        for store in df_order['Name'].unique():
            if (rdc, store, sku) in u_indices:
                lhs_indices.append(u_indices[(rdc, store, sku)])
                lhs_values.append(demand.get((store, sku), 0.0))
        
        # CDC到该RDC的调拨量
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
    if wh_type not in ['RDC', 'CDC']:  # 忽略Factory类型
        continue
    
    lhs_indices = []
    lhs_values = []
    
    if wh in cdc_names:
        # CDC的出库包括调拨和直接配送
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
        # RDC只有直接配送
        for store in df_order['Name'].unique():
            for sku in ['im', 'dm']:
                if (wh, store, sku) in u_indices:
                    lhs_indices.append(u_indices[(wh, store, sku)])
                    lhs_values.append(demand.get((store, sku), 0.0))
    
    # 容量约束: 出库量 <= 容量 * y_wh
    lhs_indices.append(y_indices[wh])
    lhs_values.append(-cap[wh])
    
    if lhs_indices:
        problem.linear_constraints.add(lin_expr=[[lhs_indices, lhs_values]], senses=['L'], rhs=[0.0], names=[f'capacity_{constraint_count}'])
        constraint_count += 1

# 5. 线性化约束
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
        # w_wh <= M * z_wh
        indices = [w_indices[wh], z_indices[wh]]
        values = [1.0, -M]
        problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['L'], rhs=[0.0], names=[f'linear1_{constraint_count}'])
        constraint_count += 1
        
        # 计算出库量用于 w_wh <= out_i
        out_indices = []
        out_values = []
        
        if wh in cdc_names:
            # CDC的出库包括调拨和直接配送
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (wh, rdc, sku) in f_indices:
                        out_indices.append(f_indices[(wh, rdc, sku)])
                        out_values.append(1.0)
            
            for store in df_order['Name'].unique():
                for sku in ['im', 'dm']:
                    if (wh, store, sku) in u_indices:
                        out_indices.append(u_indices[(wh, store, sku)])
                        out_values.append(demand.get((store, sku), 0.0))
        else:
            # RDC只有直接配送
            for store in df_order['Name'].unique():
                for sku in ['im', 'dm']:
                    if (wh, store, sku) in u_indices:
                        out_indices.append(u_indices[(wh, store, sku)])
                        out_values.append(demand.get((store, sku), 0.0))
        
        if out_indices:
            # w_wh <= out_i
            row = [[w_indices[wh]] + out_indices, [-1.0] + out_values]
            problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'linear2_{constraint_count}'])
            constraint_count += 1
            
            # w_wh >= out_i - M*(1 - z_wh)
            # 重写为: w_wh + M*z_wh >= out_i - M
            row = [[w_indices[wh], z_indices[wh]] + out_indices, [1.0, M] + [-v for v in out_values]]
            problem.linear_constraints.add(lin_expr=[row], senses=['G'], rhs=[-M], names=[f'linear3_{constraint_count}'])
            constraint_count += 1

# 6. 时效约束
total_demand = df_order['qty'].sum()
satisfied_demand_indices = []
satisfied_demand_values = []

for (store, sku) in v_indices.keys():
    # 获取可服务仓库
    eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
    
    for wh in eligible_whs:
        if (wh, store, sku) in u_indices:
            travel_time = time_matrix.get((wh, store), float('inf'))
            if travel_time <= 600:
                # v_store_sku >= u_wh_store_sku
                row = [[v_indices[(store, sku)], u_indices[(wh, store, sku)]], [-1.0, 1.0]]
                problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'time1_{constraint_count}'])
                constraint_count += 1
            else:
                # v_store_sku <= 1 - u_wh_store_sku
                row = [[v_indices[(store, sku)], u_indices[(wh, store, sku)]], [1.0, 1.0]]
                problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[1.0], names=[f'time2_{constraint_count}'])
                constraint_count += 1
    
    # 收集满意需求用于整体时效约束
    satisfied_demand_indices.append(v_indices[(store, sku)])
    satisfied_demand_values.append(demand.get((store, sku), 0.0))

# 整体时效约束
satisfied_demand = [[satisfied_demand_indices, satisfied_demand_values]]
problem.linear_constraints.add(lin_expr=satisfied_demand, senses=['G'], rhs=[0.95 * total_demand], names=[f'overall_time_window_{constraint_count}'])
constraint_count += 1

# 7. 智能系统采购约束 - 只包含RDC和CDC类型
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
        # z_wh <= y_wh
        row = [[z_indices[wh], y_indices[wh]], [1.0, -1.0]]
        problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'system_{constraint_count}'])
        constraint_count += 1

# ========== 处理成本添加到目标函数 ==========
# 处理成本的结构比较复杂，需要单独处理
# CDC的处置量为出库量的2倍，RDC的处置量为调拨入+直配
# 处理成本 = proc_cost * (总处置量 - 0.4 * w_wh)
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC'] and wh in proc_cost:
        cost = proc_cost[wh]
        out_indices = []
        out_values = []
        
        if wh in cdc_names:
            # CDC的处置量为出库量的2倍
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (wh, rdc, sku) in f_indices:
                        out_indices.append(f_indices[(wh, rdc, sku)])
                        out_values.append(2.0 * cost)
            
            for store in df_order['Name'].unique():
                for sku in ['im', 'dm']:
                    if (wh, store, sku) in u_indices:
                        out_indices.append(u_indices[(wh, store, sku)])
                        out_values.append(1.0 * cost)
        else:
            # RDC的处置量为调拨入+直配
            # 调拨入量
            # 按SKU分别匹配对应的CDC，避免漏算
            for sku in ['im', 'dm']:
                # im对应port_cdc，dm对应inland_cdc
                cdc = port_cdc if sku == 'im' else inland_cdc
                if (cdc, wh, sku) in f_indices:
                    out_indices.append(f_indices[(cdc, wh, sku)])
                    out_values.append(cost)
            
            # 直配量
            for store in df_order['Name'].unique():
                for sku in ['im', 'dm']:
                    if (wh, store, sku) in u_indices:
                        out_indices.append(u_indices[(wh, store, sku)])
                        out_values.append(1.0 * cost)
        
        # 添加处理成本到目标函数
        if out_indices:
            # 创建一个列表的元组，包含变量索引和对应的系数值
            coeff_list = []
            for idx, value in zip(out_indices, out_values):
                # 获取当前变量的目标函数系数
                current_coeff = problem.objective.get_linear(idx)
                # 累加上处理成本系数
                coeff_list.append((idx, current_coeff + value))
            # 使用set_linear方法更新目标函数系数
            problem.objective.set_linear(coeff_list)

print(f"总约束数: {constraint_count}")

# ========== 求解 ==========
print("求解模型...")
problem.solve()

# 输出求解状态
status_string = problem.solution.get_status_string()
print(f"求解状态: {status_string}")

# 使用更简单的方式检查求解状态 - 通过状态字符串判断
if "optimal" in status_string.lower():
    print(f'最优总成本: {problem.solution.get_objective_value():.2f} 万元')
    
    # 提取结果用于生成附件9、10、11
    output_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/output_result'
    os.makedirs(output_dir, exist_ok=True)
    
    # 附件9: 仓网业务表现文件
    # 计算各指标
    # 只处理RDC和CDC类型的仓库
    valid_whs = [wh for wh in df_wh['Name'] if wh in cap]
    
    open_wh_count = sum(1 for wh in valid_whs if problem.solution.get_values(y_indices[wh]) > 0.5)
    
    # 计算满意需求
    satisfied_demand_val = 0.0
    for (store, sku) in v_indices.keys():
        satisfied_demand_val += demand.get((store, sku), 0.0) * problem.solution.get_values(v_indices[(store, sku)])
    
    satisfied_rate = satisfied_demand_val / total_demand
    
    # 运输成本 - CDC到RDC
    transport_wh = 0.9/10000 * sum(dist.get((cdc, rdc), 0) * problem.solution.get_values(f_indices[(cdc, rdc, sku)]) 
                                  for cdc in cdc_names
                                  for rdc in rdc_names
                                  for sku in ['im', 'dm']
                                  if (cdc, rdc, sku) in f_indices)
    
    # 运输成本 - 仓库到门店
    transport_cust = 1.45/10000 * sum(dist.get((wh, store), 0) * demand.get((store, sku), 0) * problem.solution.get_values(u_indices[(wh, store, sku)])
                                     for wh in valid_whs
                                     for store in df_order['Name'].unique()
                                     for sku in ['im', 'dm']
                                     if (wh, store, sku) in u_indices)
    
    # 开仓成本
    opening = sum(open_cost[wh] * problem.solution.get_values(y_indices[wh]) for wh in valid_whs)
    
    # 处置成本
    processing_total_cost = 0.0
    for wh in valid_whs:
        if wh in cdc_names:
            # CDC的处置量为出库量的2倍
            qty = 2 * (sum(problem.solution.get_values(f_indices[(wh, rdc, sku)])
                           for rdc in rdc_names
                           for sku in ['im', 'dm']
                           if (wh, rdc, sku) in f_indices) +
                      sum(demand.get((store, sku), 0) * problem.solution.get_values(u_indices[(wh, store, sku)])
                          for store in df_order['Name'].unique()
                          for sku in ['im', 'dm']
                          if (wh, store, sku) in u_indices))
        else:
            # RDC的处置量为调拨入+直配
            # 按SKU分别匹配对应的CDC，避免漏算
            qty = 0
            for sku in ['im', 'dm']:
                # im对应port_cdc，dm对应inland_cdc
                cdc = port_cdc if sku == 'im' else inland_cdc
                if (cdc, wh, sku) in f_indices:
                    qty += problem.solution.get_values(f_indices[(cdc, wh, sku)])
            # 加上直配量
            qty += sum(demand.get((store, sku), 0) * problem.solution.get_values(u_indices[(wh, store, sku)])
                      for store in df_order['Name'].unique()
                      for sku in ['im', 'dm']
                      if (wh, store, sku) in u_indices)
        
        # 应用智能系统折扣，确保处理成本始终为正值
        processing_total_cost += proc_cost[wh] * max(qty * 0.6, 0.0)
    
    # 智能调度系统成本
    smart_system = sum(1.5 * problem.solution.get_values(z_indices[wh]) for wh in valid_whs if wh in z_indices)
    
    # 创建仓网业务表现文件
    business_performance = pd.DataFrame({
        '开仓数量': [open_wh_count],
        '时效满足率': [satisfied_rate],
        '总物流成本（单位：万元）': [problem.solution.get_objective_value()],
        '仓库之间的运输总成本（单位：万元）': [transport_wh],
        '仓库到门店的运输总成本（单位：万元）': [transport_cust],
        '开仓总成本（单位：万元）': [opening],
        '出入仓处置总成本（单位：万元）': [processing_total_cost],
        '智能调度系统采购总成本（单位：万元）': [smart_system]
    })
    
    business_performance.to_csv(os.path.join(output_dir, '仓网业务表现文件_cplex.csv'), index=False)
    print(f"仓网业务表现文件_cplex.csv已保存")
    
    # 附件10: 仓库处置订单量文件
    warehouse_processing = []
    # 只处理RDC和CDC类型的仓库
    for wh in valid_whs:
        if problem.solution.get_values(y_indices[wh]) > 0.5:  # 只统计已开仓库
            for sku in ['dm', 'im']:
                if sku == 'dm':
                    # 内陆CDC处理国产海鲜，RDC可以处理国产海鲜
                    if wh == inland_cdc or wh in rdc_names:
                        qty = sum(demand.get((store, sku), 0) * problem.solution.get_values(u_indices[(wh, store, sku)]) 
                                 for store in df_order['Name'].unique() 
                                 if (wh, store, sku) in u_indices)
                        # 计算调拨出量（仅CDC有）
                        if wh == inland_cdc:
                            qty += sum(problem.solution.get_values(f_indices[(wh, rdc, sku)]) 
                                     for rdc in rdc_names 
                                     if (wh, rdc, sku) in f_indices)
                            # CDC的处置量为出库量的2倍（入库量+出库量）
                            qty *= 2
                        elif wh in rdc_names and (inland_cdc, wh, sku) in f_indices:
                            # RDC的货来自内陆CDC
                            qty += problem.solution.get_values(f_indices[(inland_cdc, wh, sku)])
                        warehouse_processing.append({'Name': wh, 'SKU': sku, 'Qty（单位：吨）': qty})
                else:  # im
                    # 港口CDC处理进口海鲜，RDC可以处理进口海鲜
                    if wh == port_cdc or wh in rdc_names:
                        qty = sum(demand.get((store, sku), 0) * problem.solution.get_values(u_indices[(wh, store, sku)]) 
                                 for store in df_order['Name'].unique() 
                                 if (wh, store, sku) in u_indices)
                        # 计算调拨出量（仅CDC有）
                        if wh == port_cdc:
                            qty += sum(problem.solution.get_values(f_indices[(wh, rdc, sku)]) 
                                     for rdc in rdc_names 
                                     if (wh, rdc, sku) in f_indices)
                            # CDC的处置量为出库量的2倍（入库量+出库量）
                            qty *= 2
                        elif wh in rdc_names and (port_cdc, wh, sku) in f_indices:
                            # RDC的货来自港口CDC
                            qty += problem.solution.get_values(f_indices[(port_cdc, wh, sku)])
                        warehouse_processing.append({'Name': wh, 'SKU': sku, 'Qty（单位：吨）': qty})
    
    warehouse_processing_df = pd.DataFrame(warehouse_processing)
    warehouse_processing_df.to_csv(os.path.join(output_dir, '仓库处置订单量文件_cplex.csv'), index=False)
    print(f"仓库处置订单量文件_cplex.csv已保存")
    
    # 附件11: 仓网供应关系文件
    supply_relationships = []
    
    # CDC到RDC的调拨
    for cdc in cdc_names:
        for rdc in rdc_names:
            for sku in ['dm', 'im']:
                if (cdc, rdc, sku) in f_indices:
                    qty = problem.solution.get_values(f_indices[(cdc, rdc, sku)])
                    if qty > 0.01:  # 只记录有调拨量的关系
                        supply_relationships.append({'Name': cdc, 'Customer': rdc, 'SKU': sku, 'Qty（单位：吨）': qty})
    
    # 仓库到门店的配送
    for wh in df_wh['Name']:
        for store in df_order['Name'].unique():
            for sku in ['dm', 'im']:
                if (wh, store, sku) in u_indices and problem.solution.get_values(u_indices[(wh, store, sku)]) > 0.5:
                    qty = demand.get((store, sku), 0)
                    city = store_city_map[store]
                    supply_relationships.append({'Name': wh, 'Customer': city, 'SKU': sku, 'Qty（单位：吨）': qty})
    
    supply_relationships_df = pd.DataFrame(supply_relationships)
    supply_relationships_df.to_csv(os.path.join(output_dir, '仓网供应关系文件_cplex.csv'), index=False)
    print(f"仓网供应关系文件_cplex.csv已保存")
    
    print("问题1求解完成！")
else:
    print(f'求解状态: {problem.solution.get_status_string()}')
    print('未找到最优解')