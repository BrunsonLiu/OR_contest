# -*- coding: utf-8 -*-
"""
验证问题一CPLEX结果加上运输损耗成本后的总成本
"""

import pandas as pd
import os

# 设置数据文件路径
input_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data'
output_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/output_result'

# 读取数据
df_customer = pd.read_csv(os.path.join(input_dir, 'df_customer.csv'))
df_wh = pd.read_csv(os.path.join(input_dir, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(input_dir, 'df_matrix.csv'))
df_order = pd.read_csv(os.path.join(input_dir, 'df_order.csv'))
df_proc = pd.read_csv(os.path.join(input_dir, 'df_proc.csv'))

# 读取问题一的结果
problem1_business = pd.read_csv(os.path.join(output_dir, '仓网业务表现文件_cplex.csv'))
supply_relationships = pd.read_csv(os.path.join(output_dir, '仓网供应关系文件_cplex.csv'))

# 数据预处理
# 1. 识别CDC和RDC
cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()

# 2. 识别港口CDC和内陆CDC
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

# 5. 距离和时效矩阵
dist = {}
time_matrix = {}
for _, row in df_matrix.iterrows():
    dist[(row['From'], row['To'])] = row['Distance']
    time_matrix[(row['From'], row['To'])] = row['Duration']

# 6. 仓库参数
cap = {}
open_cost = {}
proc_cost = {}
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

# 定义损耗成本计算函数
def calculate_loss_cost(duration_min):
    """根据运输时间计算损耗成本（万元/吨）"""
    if duration_min <= 500:
        return 0.0
    else:
        # 公式：0.2 * (t-500)^2 元/吨 -> 转换为万元/吨需除以 10000
        loss_yuan = 0.2 * (duration_min - 500)**2
        return loss_yuan / 10000.0

print("="*80)
print("验证问题一CPLEX结果加上运输损耗成本后的总成本")
print("="*80)

# 读取问题一的基础成本
base_total_cost = problem1_business['总物流成本（单位：万元）'].values[0]
transport_wh_cost = problem1_business['仓库之间的运输总成本（单位：万元）'].values[0]
transport_store_cost = problem1_business['仓库到门店的运输总成本（单位：万元）'].values[0]
opening_cost = problem1_business['开仓总成本（单位：万元）'].values[0]
processing_cost = problem1_business['出入仓处置总成本（单位：万元）'].values[0]
smart_system_cost = problem1_business['智能调度系统采购总成本（单位：万元）'].values[0]

print("\n问题一的基础成本：")
print("-"*80)
print(f"总物流成本: {base_total_cost:.2f} 万元")
print(f"  - 仓库之间的运输总成本: {transport_wh_cost:.2f} 万元")
print(f"  - 仓库到门店的运输总成本: {transport_store_cost:.2f} 万元")
print(f"  - 开仓总成本: {opening_cost:.2f} 万元")
print(f"  - 出入仓处置总成本: {processing_cost:.2f} 万元")
print(f"  - 智能调度系统采购总成本: {smart_system_cost:.2f} 万元")

# 计算运输损耗成本
print("\n计算运输损耗成本：")
print("-"*80)

total_loss_cost = 0.0
high_loss_paths = []

for _, row in supply_relationships.iterrows():
    from_wh = row['Name']
    to_customer = row['Customer']
    sku = row['SKU']
    qty = row['Qty（单位：吨）']
    
    # 获取运输时间
    travel_time = time_matrix.get((from_wh, to_customer), float('inf'))
    
    if travel_time != float('inf'):
        # 计算损耗成本
        loss_per_ton = calculate_loss_cost(travel_time)
        loss_cost = loss_per_ton * qty
        
        total_loss_cost += loss_cost
        
        if loss_cost > 0:
            high_loss_paths.append({
                'from_wh': from_wh,
                'to_customer': to_customer,
                'sku': sku,
                'qty': qty,
                'travel_time': travel_time,
                'loss_per_ton': loss_per_ton,
                'loss_cost': loss_cost
            })

print(f"总运输损耗成本: {total_loss_cost:.2f} 万元")
print(f"有损耗的路径数量: {len(high_loss_paths)} 条")

# 显示损耗最大的路径
if high_loss_paths:
    high_loss_paths_sorted = sorted(high_loss_paths, key=lambda x: x['loss_cost'], reverse=True)
    print("\n损耗成本最高的10条路径：")
    print("-"*80)
    for i, path in enumerate(high_loss_paths_sorted[:10], 1):
        print(f"{i}. {path['from_wh']} -> {path['to_customer']} ({path['sku']})")
        print(f"   运输时间: {path['travel_time']:.0f} 分钟")
        print(f"   数量: {path['qty']:.2f} 吨")
        print(f"   损耗成本: {path['loss_per_ton']:.4f} 万元/吨")
        print(f"   总损耗: {path['loss_cost']:.2f} 万元")

# 计算加上损耗成本后的总成本
new_total_cost = base_total_cost + total_loss_cost

print("\n" + "="*80)
print("加上运输损耗成本后的结果：")
print("="*80)
print(f"基础总成本: {base_total_cost:.2f} 万元")
print(f"运输损耗成本: {total_loss_cost:.2f} 万元")
print(f"新总成本: {new_total_cost:.2f} 万元")
print(f"成本增加: {(total_loss_cost/base_total_cost*100):.1f}%")
print("="*80)

# 生成增强的供应关系文件（包含损耗成本）
enhanced_relationships = []
for _, row in supply_relationships.iterrows():
    from_wh = row['Name']
    to_customer = row['Customer']
    sku = row['SKU']
    qty = row['Qty（单位：吨）']
    
    travel_time = time_matrix.get((from_wh, to_customer), float('inf'))
    loss_per_ton = calculate_loss_cost(travel_time) if travel_time != float('inf') else 0.0
    total_loss = loss_per_ton * qty
    
    enhanced_relationships.append({
        'Name': from_wh,
        'Customer': to_customer,
        'SKU': sku,
        'Qty（单位：吨）': qty,
        '运输时间(分钟)': travel_time if travel_time != float('inf') else 0,
        '损耗成本(万元/吨)': loss_per_ton,
        '总损耗成本(万元)': total_loss
    })

enhanced_df = pd.DataFrame(enhanced_relationships)
enhanced_df.to_csv(os.path.join(output_dir, '仓网供应关系文件_带损耗成本_cplex.csv'), 
                  index=False, encoding='utf-8-sig')

print(f"\n增强的供应关系文件已保存到: {os.path.join(output_dir, '仓网供应关系文件_带损耗成本_cplex.csv')}")

# 生成业务表现文件（包含损耗成本）
business_performance = pd.DataFrame({
    '开仓数量': [problem1_business['开仓数量'].values[0]],
    '时效满足率': [problem1_business['时效满足率'].values[0]],
    '基础总物流成本（单位：万元）': [base_total_cost],
    '仓库之间的运输总成本（单位：万元）': [transport_wh_cost],
    '仓库到门店的运输总成本（单位：万元）': [transport_store_cost],
    '开仓总成本（单位：万元）': [opening_cost],
    '出入仓处置总成本（单位：万元）': [processing_cost],
    '智能调度系统采购总成本（单位：万元）': [smart_system_cost],
    '运输损耗总成本（单位：万元）': [total_loss_cost],
    '加上损耗后的总成本（单位：万元）': [new_total_cost]
})

business_performance.to_csv(os.path.join(output_dir, '仓网业务表现文件_带损耗成本_cplex.csv'), 
                        index=False, encoding='utf-8-sig')

print(f"业务表现文件已保存到: {os.path.join(output_dir, '仓网业务表现文件_带损耗成本_cplex.csv')}")
