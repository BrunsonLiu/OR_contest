from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
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
        dist_val = dist.get((wh, store), 0)
        qty_val = demand.get((store, sku), 0)
        p_cost = proc_cost.get(wh, 0)

        # 核心公式：运输费 + 2.0倍处置费 (入+出)
        # 注意：这里的 p_cost 如果是元，
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
            # 检查调拨是否允许
            if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                var_name = f'f_{cdc}_{rdc}_{sku}'
                # 计算运输成本系数: 0.9/10000 * distance
                dist_val = dist.get((cdc, rdc), 0)
                p_cost_cdc = proc_cost.get(cdc, 0)

                # 运输费 + CDC的处置费(2倍:入+出) + RDC的处置费(1倍:仅入库，RDC出库由u变量承担)
                cost = (0.9e-4 * dist_val) + (2.0 * p_cost_cdc)

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
        p_cost = proc_cost.get(wh, 0)
        # 折扣额 = - (0.4折扣 * 2.0倍处置量 * 单价)
        discount_coeff = -0.8 * p_cost 

        problem.variables.add(obj=[discount_coeff], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
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

# ========== 5. 线性化约束 (修正版) ==========
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:
        # 收集该仓库的总出库量表达式 (out_i)
        out_indices = []
        out_values = []
        
        # 1. 配送量 (u 变量)
        for store in df_customer['Name']:
            for sku in ['im', 'dm']:
                if (wh, store, sku) in u_indices:
                    out_indices.append(u_indices[(wh, store, sku)])
                    out_values.append(demand.get((store, sku), 0.0))
        
        # 2. 调拨量 (f 变量, 仅CDC有)
        if wh in cdc_names:
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (wh, rdc, sku) in f_indices:
                        out_indices.append(f_indices[(wh, rdc, sku)])
                        out_values.append(1.0)
        
        if out_indices:
            # --- 约束 1: w_wh <= 实际总出库量 ---
            # 折扣不能超过实际货量
            row1 = [[w_indices[wh]] + out_indices, [1.0] + [-v for v in out_values]]
            problem.linear_constraints.add(lin_expr=[row1], senses=['L'], rhs=[0.0], 
                                         names=[f'w_max_out_{wh}'])
            
            # --- 约束 2: w_wh <= M * z_wh ---
            # 核心锁：如果不买系统(z=0)，w 强制为 0
            M_val = cap.get(wh, 100000) 
            row2 = [[w_indices[wh], z_indices[wh]], [1.0, -M_val]]
            problem.linear_constraints.add(lin_expr=[row2], senses=['L'], rhs=[0.0], 
                                         names=[f'w_limit_by_z_{wh}'])

# 6. 时效约束（对全部需求应用95%时效满足率要求；按“服务门店的仓库→门店”运输时长判断是否满足10小时）
total_demand_for_time = sum(demand.values())
satisfied_demand_indices = []
satisfied_demand_values = []

for (store, sku) in v_indices.keys():
    # 获取可服务仓库
    eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names

    for wh in eligible_whs:
        if (wh, store, sku) not in u_indices:
            continue

        travel_time = time_matrix.get((wh, store), float('inf'))
        feasible = travel_time <= 600

        if feasible:
            # v_store_sku >= u_wh_store_sku
            row = [[v_indices[(store, sku)], u_indices[(wh, store, sku)]], [-1.0, 1.0]]
            problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0], names=[f'time1_{constraint_count}'])
            constraint_count += 1
        else:
            # v_store_sku <= 1 - u_wh_store_sku
            row = [[v_indices[(store, sku)], u_indices[(wh, store, sku)]], [1.0, 1.0]]
            problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[1.0], names=[f'time2_{constraint_count}'])
            constraint_count += 1

    # 收集全部需求（im+dm）用于整体时效约束
    satisfied_demand_indices.append(v_indices[(store, sku)])
    satisfied_demand_values.append(demand.get((store, sku), 0.0))

# 整体时效约束：95%的总需求满足时效
satisfied_demand = [[satisfied_demand_indices, satisfied_demand_values]]
problem.linear_constraints.add(
    lin_expr=satisfied_demand,
    senses=['G'],
    rhs=[0.95 * total_demand_for_time],
    names=[f'overall_time_window_{constraint_count}'],
)
constraint_count += 1

# 7. 智能系统采购约束 - 只包含RDC和CDC类型
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
        # z_wh <= y_wh
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

# 使用更简单的方式检查求解状态 - 通过状态字符串判断
if "optimal" in status_string.lower():
    print(f'最优总成本: {problem.solution.get_objective_value():.2f} 万元')
    
   # ========== 结果提取与附件生成 ==========
    output_dir = str(_REPO_ROOT / 'results/question1')
    os.makedirs(output_dir, exist_ok=True)
    
    # 基础数据准备
    valid_whs = [wh for wh in df_wh['Name'] if wh in cap]
    total_demand = sum(demand.values())

    # 1. 统计开仓数量
    open_wh_count = sum(1 for wh in valid_whs if problem.solution.get_values(y_indices[wh]) > 0.5)
    
    # 2. 计算时效满足率（按全部需求im+dm）
    satisfied_demand_val = sum(
        demand.get((store, sku), 0.0) * problem.solution.get_values(v_indices[(store, sku)])
        for (store, sku) in v_indices.keys()
    )
    satisfied_rate = (satisfied_demand_val / total_demand) if total_demand > 0 else 1.0
    
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

    # 7. 处置总成本（核心修正：必须扣除w变量代表的折扣）
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
        
        # 记录附件10数据：处置量 = 2.0 * 出库量 (对于CDC和RDC通用逻辑)
        # 注意：RDC的入库量在流平衡下等于出库量，所以 2*出库量 等于 入+出
        qty_total_wh = 2.0 * (out_qty_dm + out_qty_im)
        if out_qty_dm > 0: warehouse_stats.append({'Name': wh, 'SKU': 'dm', 'Qty（单位：吨）': 2.0 * out_qty_dm})
        if out_qty_im > 0: warehouse_stats.append({'Name': wh, 'SKU': 'im', 'Qty（单位：吨）': 2.0 * out_qty_im})
        
        # 计算该仓处置费（扣除系统折扣）
        z_val = problem.solution.get_values(z_indices[wh])
        # 折扣额 w = z_val * qty_total_wh * 0.4
        actual_proc = proc_cost[wh] * qty_total_wh * (1 - 0.4 * z_val) 
        processing_total_cost += actual_proc

    # --- 写入附件9 ---
    business_performance = pd.DataFrame({
        '开仓数量': [open_wh_count],
        '时效满足率': [satisfied_rate],
        '总物流成本（单位：万元）': [problem.solution.get_objective_value()],
        '仓库之间的运输总成本（单位：万元）': [transport_wh],
        '仓库到门店的运输总成本（单位：万元）': [transport_cust],
        '开仓总成本（单位：万元）': [opening_cost_total],
        '出入仓处置总成本（单位：万元）': [processing_total_cost],
        '智能调度系统采购总成本（单位：万元）': [smart_system_cost]
    })
    business_performance.to_csv(os.path.join(output_dir, '仓网业务表现文件_cplex.csv'), index=False)

    # --- 写入附件10 ---
    pd.DataFrame(warehouse_stats).to_csv(os.path.join(output_dir, '仓库处置订单量文件_cplex.csv'), index=False)

    # --- 写入附件11 ---
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
    
    pd.DataFrame(supply_relationships).to_csv(os.path.join(output_dir, '仓网供应关系文件_cplex.csv'), index=False)

    print("所有附件结果已成功保存至 output_result 文件夹！")
    
    print("问题1求解完成！")
else:
    print(f'求解状态: {problem.solution.get_status_string()}')
    print('未找到最优解')
