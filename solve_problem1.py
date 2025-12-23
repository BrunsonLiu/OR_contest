import pandas as pd
from pulp import *
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

# 创建模型
model = LpProblem('FreshEcom_Warehouse_Network', LpMinimize)

# ========== 决策变量 ==========
y = {}  # 仓库开设
z = {}  # 智能系统采购
u = {}  # 服务关系
v = {}  # 时效满足
f = {}  # 调拨量
w = {}  # 线性化辅助变量

# 仓库开设变量 - 只包含RDC和CDC类型
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
        y[wh] = LpVariable(f'y_{wh}', cat=LpBinary)
        if wh in cdc_names:
            model += y[wh] == 1  # CDC必开

# 智能系统变量 - 只包含RDC和CDC类型
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
        z[wh] = LpVariable(f'z_{wh}', cat=LpBinary)

# 服务关系变量
for _, row in df_order.iterrows():
    store = row['Name']
    sku = row['SKU']
    # 确定可服务的仓库集合
    if sku == 'im':
        eligible_whs = [port_cdc] + rdc_names
    else:  # dm
        eligible_whs = [inland_cdc] + rdc_names
    
    for wh in eligible_whs:
        u[(wh, store, sku)] = LpVariable(f'u_{wh}_{store}_{sku}', cat=LpBinary)

# 时效满足变量
for _, row in df_order.iterrows():
    store = row['Name']
    sku = row['SKU']
    v[(store, sku)] = LpVariable(f'v_{store}_{sku}', cat=LpBinary)

# 调拨量变量
for cdc in cdc_names:
    for rdc in rdc_names:
        for sku in ['im', 'dm']:
            # 检查调拨是否允许
            if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                f[(cdc, rdc, sku)] = LpVariable(f'f_{cdc}_{rdc}_{sku}', lowBound=0, cat=LpContinuous)

# 线性化辅助变量 - 只包含RDC和CDC类型
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
        w[wh] = LpVariable(f'w_{wh}', lowBound=0, cat=LpContinuous)

# ========== 约束条件 ==========
# 1. 单源服务约束
for _, row in df_order.iterrows():
    store = row['Name']
    sku = row['SKU']
    eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
    model += lpSum(u[(wh, store, sku)] for wh in eligible_whs) == 1, f'single_source_{store}_{sku}'

# 2. 仓库开设与服务关系
for (wh, store, sku) in u.keys():
    model += u[(wh, store, sku)] <= y[wh], f'service_open_{wh}_{store}_{sku}'

# 3. RDC流量平衡
for rdc in rdc_names:
    for sku in ['im', 'dm']:
        # 计算RDC的总配送量
        total_delivery = lpSum(
            demand[(store, sku)] * u[(rdc, store, sku)] 
            for store in df_order['Name'].unique() 
            if (rdc, store, sku) in u
        )
        
        # 计算CDC到该RDC的调拨量
        if sku == 'im' and (port_cdc, rdc, sku) in f:
            total_transfer = f[(port_cdc, rdc, sku)]
        elif sku == 'dm' and (inland_cdc, rdc, sku) in f:
            total_transfer = f[(inland_cdc, rdc, sku)]
        else:
            total_transfer = 0
        
        model += total_transfer == total_delivery, f'balance_{rdc}_{sku}'

# 4. 容量约束
M = df_order['qty'].sum()  # 大M
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type not in ['RDC', 'CDC']:  # 忽略Factory类型
        continue
        
    # 计算总出库量
    if wh in cdc_names:
        # CDC的出库包括调拨和直接配送
        transfer_out = lpSum(
            f[(wh, rdc, sku)] 
            for rdc in rdc_names 
            for sku in ['im', 'dm']
            if (wh, rdc, sku) in f
        )
        direct_out = lpSum(
            demand[(store, sku)] * u[(wh, store, sku)]
            for store in df_order['Name'].unique()
            for sku in ['im', 'dm']
            if (wh, store, sku) in u
        )
        out_i = transfer_out + direct_out
    else:
        # RDC只有直接配送
        out_i = lpSum(
            demand[(store, sku)] * u[(wh, store, sku)]
            for store in df_order['Name'].unique()
            for sku in ['im', 'dm']
            if (wh, store, sku) in u
        )
    
    model += out_i <= cap[wh] * y[wh], f'capacity_{wh}'
    
    # 5. 线性化约束
    model += w[wh] <= M * z[wh], f'linear1_{wh}'
    model += w[wh] <= out_i, f'linear2_{wh}'
    model += w[wh] >= out_i - M * (1 - z[wh]), f'linear3_{wh}'

# 6. 时效约束
for (store, sku) in v.keys():
    # 获取可服务仓库
    eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
    
    for wh in eligible_whs:
        if (wh, store, sku) in u:
            travel_time = time_matrix.get((wh, store), float('inf'))
            if travel_time <= 600:
                model += v[(store, sku)] >= u[(wh, store, sku)], f'time1_{wh}_{store}_{sku}'
            else:
                model += v[(store, sku)] <= 1 - u[(wh, store, sku)], f'time2_{wh}_{store}_{sku}'

# 整体时效约束
total_demand = df_order['qty'].sum()
satisfied_demand = lpSum(
    demand[(store, sku)] * v[(store, sku)]
    for (store, sku) in v.keys()
)
model += satisfied_demand >= 0.95 * total_demand, 'overall_time_window'

# 7. 智能系统采购约束 - 只包含RDC和CDC类型
for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:  # 忽略Factory类型
        model += z[wh] <= y[wh], f'system_{wh}'

# ========== 目标函数 ==========
# 运输成本 - CDC到RDC
transport_cost_wh = lpSum(
    0.9/10000 * dist.get((cdc, rdc), 0) * f[(cdc, rdc, sku)]
    for cdc in cdc_names
    for rdc in rdc_names
    for sku in ['im', 'dm']
    if (cdc, rdc, sku) in f
)

# 运输成本 - 仓库到门店
transport_cost_cust = lpSum(
    1.45/10000 * dist.get((wh, store), 0) * demand[(store, sku)] * u[(wh, store, sku)]
    for wh in df_wh['Name']
    for store in df_order['Name'].unique()
    for sku in ['im', 'dm']
    if (wh, store, sku) in u
)

# 开仓成本 - 只包含RDC和CDC类型
opening_cost = lpSum(open_cost[wh] * y[wh] for wh in df_wh['Name'] if wh in cap)

# 处置成本（已线性化） - 只包含RDC和CDC类型
# 注意：这里需要根据仓库类型区分处理：CDC的处置量为出库量的2倍，RDC的处置量为调拨入+直配
processing_cost_terms = []
for wh in df_wh['Name']:
    if wh in cap:
        if df_wh[df_wh['Name'] == wh]['Type'].values[0] == 'CDC':
            # CDC的处置量为出库量的2倍
            outbound_cdc = lpSum(
                f[(wh, rdc, sku)] 
                for rdc in rdc_names 
                for sku in ['im', 'dm']
                if (wh, rdc, sku) in f
            ) + lpSum(
                demand[(store, sku)] * u[(wh, store, sku)]
                for store in df_order['Name'].unique()
                for sku in ['im', 'dm']
                if (wh, store, sku) in u
            )
            total_processing = 2 * outbound_cdc - 0.4 * proc_cost[wh] * w[wh]
        else:
            # RDC的处置量为调拨入+直配
            inbound_rdc = lpSum(
                f[(inland_cdc, wh, sku)]
                for inland_cdc in cdc_names
                for sku in ['im', 'dm']
                if (inland_cdc, wh, sku) in f
            )
            outbound_rdc = lpSum(
                demand[(store, sku)] * u[(wh, store, sku)]
                for store in df_order['Name'].unique()
                for sku in ['im', 'dm']
                if (wh, store, sku) in u
            )
            total_processing = (inbound_rdc + outbound_rdc) - 0.4 * proc_cost[wh] * w[wh]
        processing_cost_terms.append(proc_cost[wh] * total_processing)

processing_cost = lpSum(processing_cost_terms)

# 智能系统成本 - 只包含RDC和CDC类型
system_cost = lpSum(1.5 * z[wh] for wh in df_wh['Name'] if wh in cap)

# 总成本
model += transport_cost_wh + transport_cost_cust + opening_cost + processing_cost + system_cost

# ========== 求解 ==========
print("求解模型...")
model.solve()

# 输出结果
if model.status == LpStatusOptimal:
    print(f'最优总成本: {value(model.objective):.2f} 万元')
    
    # 提取结果用于生成附件9、10、11
    output_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/output_result'
    os.makedirs(output_dir, exist_ok=True)
    
    # 附件9: 仓网业务表现文件
    # 计算各指标
    # 只处理RDC和CDC类型的仓库
    valid_whs = [wh for wh in df_wh['Name'] if wh in cap]
    
    open_wh_count = sum(1 for wh in valid_whs if value(y[wh]) > 0.5)
    satisfied_rate = value(satisfied_demand) / total_demand
    
    # 运输成本 - CDC到RDC
    transport_wh = 0.9/10000 * sum(dist.get((cdc, rdc), 0) * value(f[(cdc, rdc, sku)]) 
                                  for cdc in cdc_names
                                  for rdc in rdc_names
                                  for sku in ['im', 'dm']
                                  if (cdc, rdc, sku) in f)
    
    # 运输成本 - 仓库到门店
    transport_cust = 1.45/10000 * sum(dist.get((wh, store), 0) * demand[(store, sku)] * value(u[(wh, store, sku)])
                                     for wh in valid_whs
                                     for store in df_order['Name'].unique()
                                     for sku in ['im', 'dm']
                                     if (wh, store, sku) in u)
    
    # 开仓成本
    opening = sum(open_cost[wh] * value(y[wh]) for wh in valid_whs)
    
    # 处置成本
    processing_total_cost = sum(proc_cost[wh] * (
                                                   2 * (
                                                       sum(value(f[(wh, rdc, sku)])
                                                           for rdc in rdc_names
                                                           for sku in ['im', 'dm']
                                                           if (wh, rdc, sku) in f) +
                                                       sum(demand[(store, sku)] * value(u[(wh, store, sku)])
                                                           for store in df_order['Name'].unique()
                                                           for sku in ['im', 'dm']
                                                           if (wh, store, sku) in u)
                                                   ) if df_wh[df_wh['Name'] == wh]['Type'].values[0] == 'CDC' else
                                                   (
                                                       sum(value(f[(inland_cdc, wh, sku)])
                                                           for inland_cdc in cdc_names
                                                           for sku in ['im', 'dm']
                                                           if (inland_cdc, wh, sku) in f) +
                                                       sum(demand[(store, sku)] * value(u[(wh, store, sku)])
                                                           for store in df_order['Name'].unique()
                                                           for sku in ['im', 'dm']
                                                           if (wh, store, sku) in u)
                                                   )
                                               ) - 0.4 * proc_cost[wh] * value(w[wh])
                               for wh in valid_whs)
    
    # 智能调度系统成本
    smart_system = sum(1.5 * value(z[wh]) for wh in valid_whs)
    
    # 创建仓网业务表现文件
    business_performance = pd.DataFrame({
        '开仓数量': [open_wh_count],
        '时效满足率': [satisfied_rate],
        '总物流成本（单位：万元）': [value(model.objective)],
        '仓库之间的运输总成本（单位：万元）': [transport_wh],
        '仓库到门店的运输总成本（单位：万元）': [transport_cust],
        '开仓总成本（单位：万元）': [opening],
        '出入仓处置总成本（单位：万元）': [processing_total_cost],
        '智能调度系统采购总成本（单位：万元）': [smart_system]
    })
    
    business_performance.to_csv(os.path.join(output_dir, '仓网业务表现文件.csv'), index=False)
    print(f"仓网业务表现文件已保存")
    
    # 附件10: 仓库处置订单量文件
    warehouse_processing = []
    # 只处理RDC和CDC类型的仓库
    for wh in valid_whs:
        if value(y[wh]) > 0.5:  # 只统计已开仓库
            for sku in ['dm', 'im']:
                if sku == 'dm':
                    # 内陆CDC处理国产海鲜，RDC可以处理国产海鲜
                    if wh == inland_cdc or wh in rdc_names:
                        qty = sum(demand[(store, sku)] * value(u[(wh, store, sku)]) 
                                 for store in df_order['Name'].unique() 
                                 if (store, sku) in demand and (wh, store, sku) in u)
                        # 计算调拨出量（仅CDC有）
                        if wh == inland_cdc:
                            qty += sum(value(f[(wh, rdc, sku)]) 
                                     for rdc in rdc_names 
                                     if (wh, rdc, sku) in f)
                            # CDC的处置量为出库量的2倍（入库量+出库量）
                            qty *= 2
                        elif wh in rdc_names and (inland_cdc, wh, sku) in f:
                            # RDC的货来自内陆CDC
                            qty += value(f[(inland_cdc, wh, sku)])
                        warehouse_processing.append({'Name': wh, 'SKU': sku, 'Qty（单位：吨）': qty})
                else:  # im
                    # 港口CDC处理进口海鲜，RDC可以处理进口海鲜
                    if wh == port_cdc or wh in rdc_names:
                        qty = sum(demand[(store, sku)] * value(u[(wh, store, sku)]) 
                                 for store in df_order['Name'].unique() 
                                 if (store, sku) in demand and (wh, store, sku) in u)
                        # 计算调拨出量（仅CDC有）
                        if wh == port_cdc:
                            qty += sum(value(f[(wh, rdc, sku)]) 
                                     for rdc in rdc_names 
                                     if (wh, rdc, sku) in f)
                            # CDC的处置量为出库量的2倍（入库量+出库量）
                            qty *= 2
                        elif wh in rdc_names and (port_cdc, wh, sku) in f:
                            # RDC的货来自港口CDC
                            qty += value(f[(port_cdc, wh, sku)])
                        warehouse_processing.append({'Name': wh, 'SKU': sku, 'Qty（单位：吨）': qty})
    
    warehouse_processing_df = pd.DataFrame(warehouse_processing)
    warehouse_processing_df.to_csv(os.path.join(output_dir, '仓库处置订单量文件.csv'), index=False)
    print(f"仓库处置订单量文件已保存")
    
    # 附件11: 仓网供应关系文件
    supply_relationships = []
    
    # CDC到RDC的调拨
    for cdc in cdc_names:
        for rdc in rdc_names:
            for sku in ['dm', 'im']:
                if (cdc, rdc, sku) in f:
                    qty = value(f[(cdc, rdc, sku)])
                    if qty > 0.01:  # 只记录有调拨量的关系
                        supply_relationships.append({'Name': cdc, 'Customer': rdc, 'SKU': sku, 'Qty（单位：吨）': qty})
    
    # 仓库到门店的配送
    for wh in df_wh['Name']:
        for store in df_order['Name'].unique():
            for sku in ['dm', 'im']:
                if (wh, store, sku) in u and value(u[(wh, store, sku)]) > 0.5:
                    qty = demand[(store, sku)]
                    city = store_city_map[store]
                    supply_relationships.append({'Name': wh, 'Customer': city, 'SKU': sku, 'Qty（单位：吨）': qty})
    
    supply_relationships_df = pd.DataFrame(supply_relationships)
    supply_relationships_df.to_csv(os.path.join(output_dir, '仓网供应关系文件.csv'), index=False)
    print(f"仓网供应关系文件已保存")
    
    print("问题1求解完成！")
else:
    print(f'求解状态: {LpStatus[model.status]}')
    print('未找到最优解')