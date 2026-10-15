# -*- coding: utf-8 -*-
"""
问题2结果可视化脚本（运输网络+损耗成本）

显示问题2的仓库选择变化、运输路径以及超时路径的损耗成本
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())

import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import os
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

print("="*80)
print("问题2结果可视化（运输网络+损耗成本）")
print("="*80)

# ==================== 数据加载 ====================
output_dir = str(_REPO_ROOT / 'results/question2')
input_dir = str(_REPO_ROOT / 'data/raw')

print("\n【数据加载】")
try:
    df_supply_loss = pd.read_csv(os.path.join(output_dir, '仓网供应关系文件_运输损耗_cplex.csv'))
    print("  ✓ 仓网供应关系文件（运输损耗）")
    
    df_performance_loss = pd.read_csv(os.path.join(output_dir, '仓网业务表现文件_运输损耗_cplex.csv'))
    print("  ✓ 仓网业务表现文件（运输损耗）")
    
    df_matrix = pd.read_csv(os.path.join(input_dir, 'df_matrix.csv'))
    print("  ✓ 运输矩阵文件（df_matrix.csv）")
    
    df_customer = pd.read_csv(os.path.join(input_dir, 'df_customer.csv'))
    print("  ✓ 客户文件（df_customer.csv）")
    
    df_wh = pd.read_csv(os.path.join(input_dir, 'df_wh.csv'))
    print("  ✓ 仓库文件（df_wh.csv）")
    
    df_loc = pd.read_csv(os.path.join(input_dir, 'df_loc.csv'))
    print("  ✓ 城市位置文件（df_loc.csv）")
    
    # 加载损耗明细文件
    df_wh_loss = pd.read_csv(os.path.join(output_dir, '仓→仓损耗明细文件_完整版_cplex.csv'))
    print("  ✓ 仓→仓损耗明细文件")
    
    df_cust_loss = pd.read_csv(os.path.join(output_dir, '仓→店损耗明细文件_完整版_cplex.csv'))
    print("  ✓ 仓→店损耗明细文件")
    
except Exception as e:
    print(f"  ✗ 加载失败: {e}")
    sys.exit(1)

# ==================== 从数据文件加载坐标 ====================
print("\n【坐标映射加载】")

# 创建城市坐标字典（从df_loc.csv）
city_coords = {}
for _, row in df_loc.iterrows():
    city_name = row['Location']
    longitude = row['Longitude']
    latitude = row['Latitude']
    if pd.notna(longitude) and pd.notna(latitude):
        city_coords[city_name] = [longitude, latitude]

print(f"  ✓ 加载了 {len(city_coords)} 个城市的坐标")

# 仓库坐标从df_wh的Location映射到city_coords
warehouse_coords = {}

# 加载仓库信息
print("\n  加载仓库坐标...")
for _, row in df_wh.iterrows():
    wh_name = row['Name']
    wh_location = row['Location']
    
    # 从city_coords获取坐标
    if wh_location in city_coords:
        warehouse_coords[wh_name] = {
            'coords': city_coords[wh_location],
            'type': row['Type']
        }
        print(f"    ✓ {wh_name} ({wh_location}): {city_coords[wh_location]}")
    else:
        print(f"    ⚠ 未找到 {wh_name} ({wh_location}) 的坐标")

print(f"  ✓ 加载了 {len(warehouse_coords)} 个仓库坐标")

# ==================== 数据预处理 ====================
print("\n【数据预处理】")

# 1. 创建 Duration 查找字典
duration_dict = {}
for _, row in df_matrix.iterrows():
    from_loc = row['From']
    to_loc = row['To']
    duration = row['Duration']
    
    duration_dict[(from_loc, to_loc)] = duration

# 2. 加载门店到城市的映射
store_city_map = {}
for _, row in df_customer.iterrows():
    store_city_map[row['Name']] = row['Location']

# 3. 处理问题2的供应关系 - 区分仓库间调拨和仓库到门店
print("  ✓ 处理问题2供应关系...")

# 识别CDC、RDC和Factory
cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist() if 'Type' in df_wh.columns else []
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist() if 'Type' in df_wh.columns else []
factory_names = df_wh[df_wh['Type'] == 'Factory']['Name'].tolist() if 'Type' in df_wh.columns else []

# 统计仓库订单量
wh_qty_loss = {}
for _, row in df_supply_loss.iterrows():
    from_wh = row['Name']
    to_wh = row['Customer']
    qty = row['Qty（单位：吨）']
    
    if from_wh in warehouse_coords:
        if from_wh not in wh_qty_loss:
            wh_qty_loss[from_wh] = 0
        wh_qty_loss[from_wh] += qty

print(f"  ✓ 处理 {len(wh_qty_loss)} 个仓库的订单量")

# 4. 识别运输类型
# 仓库间调拨（CDC/RDC/Factory → RDC）
warehouse_to_warehouse_links = []
# 仓库到门店（RDC → Customer）
warehouse_to_customer_links = []

# 直接从损耗明细文件加载仓库间调拨数据
print(f"\n  加载仓→仓损耗明细数据...")
for _, row in df_wh_loss.iterrows():
    from_wh = row['From_wh']
    to_wh = row['To_wh']
    qty = row['Qty（单位：吨）']
    duration = row['运输时间(分钟)']
    loss = row['总损耗成本(万元)']
    
    # 检查仓库是否在warehouse_coords中
    if from_wh not in warehouse_coords:
        print(f"    ⚠ 警告: 未找到 {from_wh} 的坐标")
    if to_wh not in warehouse_coords:
        print(f"    ⚠ 警告: 未找到 {to_wh} 的坐标")
    
    warehouse_to_warehouse_links.append({
        'from': from_wh,
        'to': to_wh,
        'qty': qty,
        'duration': duration,
        'loss': loss
    })

print(f"  ✓ 加载了 {len(warehouse_to_warehouse_links)} 条仓→仓调拨")

# 直接从损耗明细文件加载仓库到门店数据
for _, row in df_cust_loss.iterrows():
    from_wh = row['From_wh']
    to_city = row['To_city']
    to_store = row['To_store']
    qty = row['Qty（单位：吨）']
    duration = row['运输时间(分钟)']
    loss = row['总损耗成本(万元)']
    
    warehouse_to_customer_links.append({
        'from': from_wh,
        'to_city': to_city,
        'to_store': to_store,
        'qty': qty,
        'duration': duration,
        'loss': loss
    })

print(f"  ✓ 仓库间调拨: {len(warehouse_to_warehouse_links)} 条")
print(f"  ✓ 仓库到门店: {len(warehouse_to_customer_links)} 条")

# 5. 识别运输类型（按运输时间分级）
# 500分钟以下：绿色（高透明度）
# 500-600分钟：橙色（中透明度）
# 600分钟以上：红色（低透明度）
low_time_links = []      # ≤500分钟
mid_time_links = []      # 500-600分钟
high_time_links = []     # >600分钟

for link in warehouse_to_warehouse_links:
    if link['duration'] is not None:
        if link['duration'] <= 500:
            low_time_links.append(link)
        elif link['duration'] <= 600:
            mid_time_links.append(link)
        else:
            high_time_links.append(link)

print(f"  ✓ 仓库间调拨 - ≤500分钟: {len(low_time_links)} 条")
print(f"  ✓ 仓库间调拨 - 500-600分钟: {len(mid_time_links)} 条")
print(f"  ✓ 仓库间调拨 - >600分钟: {len(high_time_links)} 条")

# ==================== 可视化：问题2运输网络（标出损耗成本） ====================
print("\n【可视化】问题2运输网络（标出损耗成本）...")

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    
    fig = plt.figure(figsize=(16, 12))
    ax = plt.axes(projection=ccrs.PlateCarree())
    
    # 添加地图要素
    ax.add_feature(cfeature.COASTLINE, linewidth=0.6)
    ax.add_feature(cfeature.BORDERS, linestyle='-', linewidth=0.9)
    ax.add_feature(cfeature.LAKES, alpha=0.3)
    ax.add_feature(cfeature.RIVERS, linewidth=0.4)
    
    # 设置地图范围
    ax.set_extent([73, 136, 18, 54], crs=ccrs.PlateCarree())
    
    # 统计各类型仓库数量
    cdc_count = 0
    rdc_count = 0
    factory_count = 0
    
    # 绘制CDC（红色正方形）
    for wh, info in warehouse_coords.items():
        if info['type'] == 'CDC':
            coords = info['coords']
            ax.scatter(coords[0], coords[1], s=250, c='red', alpha=0.9, 
                      marker='s', edgecolors='darkred', linewidths=2.5, 
                      transform=ccrs.PlateCarree(), zorder=5)
            ax.text(coords[0] + 0.3, coords[1] + 0.2, wh, fontsize=10, 
                   fontproperties='SimHei', transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                            alpha=0.9, edgecolor='darkred', linewidth=1.5))
            cdc_count += 1
    
    # 绘制RDC（蓝色圆形）
    for wh, info in warehouse_coords.items():
        if info['type'] == 'RDC':
            coords = info['coords']
            ax.scatter(coords[0], coords[1], s=180, c='steelblue', alpha=0.9, 
                      marker='o', edgecolors='darkblue', linewidths=2.5, 
                      transform=ccrs.PlateCarree(), zorder=5)
            ax.text(coords[0] + 0.3, coords[1] + 0.2, wh, fontsize=9, 
                   fontproperties='SimHei', transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                            alpha=0.9, edgecolor='darkblue', linewidth=1.5))
            rdc_count += 1
    
    # 绘制Factory（绿色三角形）
    for wh, info in warehouse_coords.items():
        if info['type'] == 'Factory':
            coords = info['coords']
            ax.scatter(coords[0], coords[1], s=200, c='green', alpha=0.9, 
                      marker='^', edgecolors='darkgreen', linewidths=2.5, 
                      transform=ccrs.PlateCarree(), zorder=5)
            ax.text(coords[0] + 0.3, coords[1] + 0.2, wh, fontsize=9, 
                   fontproperties='SimHei', transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                            alpha=0.9, edgecolor='darkgreen', linewidth=1.5))
            factory_count += 1
    
    # 绘制仓库间调拨连接
    # 1. ≤500分钟：绿色，高透明度
    for link in low_time_links:
        from_coords = warehouse_coords[link['from']]['coords']
        to_coords = warehouse_coords[link['to']]['coords']
        
        linewidth = min(3, max(0.5, link['qty'] / 100))
        
        ax.plot([from_coords[0], to_coords[0]], 
               [from_coords[1], to_coords[1]], 
               color='green', linewidth=linewidth, alpha=0.6,
               linestyle='-', transform=ccrs.PlateCarree(), zorder=1)
        
        # 标注损耗成本
        if link['loss'] is not None and link['loss'] > 0:
            mid_x = (from_coords[0] + to_coords[0]) / 2
            mid_y = (from_coords[1] + to_coords[1]) / 2
            ax.text(mid_x, mid_y + 0.15, f'{link["loss"]:.1f}万', fontsize=7, 
                   fontproperties='SimHei', transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='lightgreen', 
                            alpha=0.8, edgecolor='green'))
    
    # 2. 500-600分钟：橙色，中透明度
    for link in mid_time_links:
        from_coords = warehouse_coords[link['from']]['coords']
        to_coords = warehouse_coords[link['to']]['coords']
        
        linewidth = min(3, max(0.5, link['qty'] / 100))
        
        ax.plot([from_coords[0], to_coords[0]], 
               [from_coords[1], to_coords[1]], 
               color='orange', linewidth=linewidth, alpha=0.7,
               linestyle='-', transform=ccrs.PlateCarree(), zorder=1)
        
        # 标注Duration和损耗
        mid_x = (from_coords[0] + to_coords[0]) / 2
        mid_y = (from_coords[1] + to_coords[1]) / 2
        ax.text(mid_x, mid_y + 0.15, f'{link["duration"]:.0f}min\n{link["loss"]:.1f}万', fontsize=7, 
               fontproperties='SimHei', transform=ccrs.PlateCarree(),
               bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', 
                        alpha=0.8, edgecolor='orange'))
    
    # 3. >600分钟：红色，低透明度
    for link in high_time_links:
        from_coords = warehouse_coords[link['from']]['coords']
        to_coords = warehouse_coords[link['to']]['coords']
        
        linewidth = min(4, max(1.0, link['qty'] / 80))
        
        ax.plot([from_coords[0], to_coords[0]], 
               [from_coords[1], to_coords[1]], 
               color='red', linewidth=linewidth, alpha=0.8,
               linestyle='--', transform=ccrs.PlateCarree(), zorder=2)
        
        # 标注Duration和损耗
        mid_x = (from_coords[0] + to_coords[0]) / 2
        mid_y = (from_coords[1] + to_coords[1]) / 2
        ax.text(mid_x, mid_y + 0.15, f'{link["duration"]:.0f}min\n{link["loss"]:.1f}万', fontsize=7, 
               fontproperties='SimHei', transform=ccrs.PlateCarree(),
               bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', 
                        alpha=0.9, edgecolor='red'))
    
    # 绘制仓库到门店的运输连接（只显示超时的）
    print(f"\n  绘制仓库到门店的运输连接...")
    customer_links_low = []  # ≤500分钟
    customer_links_mid = []  # 500-600分钟
    customer_links_high = [] # >600分钟
    
    for link in warehouse_to_customer_links:
        if link['duration'] is not None:
            if link['duration'] <= 500:
                customer_links_low.append(link)
            elif link['duration'] <= 600:
                customer_links_mid.append(link)
            else:
                customer_links_high.append(link)
    
    print(f"    ✓ 仓库到门店 - ≤500分钟: {len(customer_links_low)} 条")
    print(f"    ✓ 仓库到门店 - 500-600分钟: {len(customer_links_mid)} 条")
    print(f"    ✓ 仓库到门店 - >600分钟: {len(customer_links_high)} 条")
    
    # 绘制仓库到门店的连接（所有路径）
    # 1. ≤500分钟：绿色，高透明度
    for link in customer_links_low:
        from_coords = warehouse_coords[link['from']]['coords']
        to_city = link['to_city']
        to_coords = city_coords.get(to_city)
        
        if to_coords is None:
            continue
        
        linewidth = min(2, max(0.5, link['qty'] / 100))
        
        ax.plot([from_coords[0], to_coords[0]], 
               [from_coords[1], to_coords[1]], 
               color='green', linewidth=linewidth, alpha=0.6,
               linestyle='-', transform=ccrs.PlateCarree(), zorder=1)
    
    # 2. 500-600分钟：橙色，中透明度
    for link in customer_links_mid:
        from_coords = warehouse_coords[link['from']]['coords']
        to_city = link['to_city']
        to_coords = city_coords.get(to_city)
        
        if to_coords is None:
            continue
        
        linewidth = min(2, max(0.5, link['qty'] / 100))
        
        ax.plot([from_coords[0], to_coords[0]], 
               [from_coords[1], to_coords[1]], 
               color='orange', linewidth=linewidth, alpha=0.7,
               linestyle='-', transform=ccrs.PlateCarree(), zorder=1)
        
        # 标注Duration和损耗
        mid_x = (from_coords[0] + to_coords[0]) / 2
        mid_y = (from_coords[1] + to_coords[1]) / 2
        ax.text(mid_x, mid_y + 0.15, f'{link["duration"]:.0f}min\n{link["loss"]:.1f}万', fontsize=7, 
               fontproperties='SimHei', transform=ccrs.PlateCarree(),
               bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', 
                        alpha=0.8, edgecolor='orange'))
    
    # 3. >600分钟：红色，高透明度
    for link in customer_links_high:
        from_coords = warehouse_coords[link['from']]['coords']
        to_city = link['to_city']
        to_coords = city_coords.get(to_city)
        
        if to_coords is None:
            continue
        
        linewidth = min(3, max(1.0, link['qty'] / 80))
        
        ax.plot([from_coords[0], to_coords[0]], 
               [from_coords[1], to_coords[1]], 
               color='red', linewidth=linewidth, alpha=0.8,
               linestyle='--', transform=ccrs.PlateCarree(), zorder=2)
        
        # 标注Duration和损耗
        mid_x = (from_coords[0] + to_coords[0]) / 2
        mid_y = (from_coords[1] + to_coords[1]) / 2
        ax.text(mid_x, mid_y + 0.15, f'{link["duration"]:.0f}min\n{link["loss"]:.1f}万', fontsize=7, 
               fontproperties='SimHei', transform=ccrs.PlateCarree(),
               bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', 
                        alpha=0.9, edgecolor='red'))
    
    # 绘制客户位置（小圆点）
    print("\n  绘制客户位置...")
    customer_count = 0
    for _, row in df_customer.iterrows():
        customer_name = row['Name']
        customer_location = row['Location']
        
        if customer_location in city_coords:
            coords = city_coords[customer_location]
            ax.scatter(coords[0], coords[1], s=15, c='gray', alpha=0.5, 
                      marker='o', transform=ccrs.PlateCarree(), zorder=3)
            customer_count += 1
    
    print(f"  ✓ 绘制了 {customer_count} 个客户位置")
    
    ax.set_title('问题2：仓网运输网络（含运输损耗成本）', fontsize=16, fontweight='bold', fontproperties='SimHei')
    
    # 添加图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor='red', markersize=12, 
               markeredgecolor='darkred', markeredgewidth=2.5, label=f'CDC（中心仓）{cdc_count}个'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='steelblue', markersize=10, 
               markeredgecolor='darkblue', markeredgewidth=2.5, label=f'RDC（区域仓）{rdc_count}个'),
        Line2D([0], [0], marker='^', color='w', markerfacecolor='green', markersize=10, 
               markeredgecolor='darkgreen', markeredgewidth=2.5, label=f'Factory（工厂）{factory_count}个'),
        Line2D([0], [0], color='green', linewidth=2, alpha=0.6, label='≤500分钟（绿色，高透明）'),
        Line2D([0], [0], color='orange', linewidth=2, alpha=0.7, label='500-600分钟（橙色，中透明）'),
        Line2D([0], [0], color='red', linewidth=2, linestyle='--', alpha=0.8, label='>600分钟（红色，高透明）'),
        Line2D([0], [0], marker='o', color='gray', markersize=5, alpha=0.5, linestyle='None', label=f'客户位置（{customer_count}个）'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', prop={'family': 'SimHei', 'size': 11})
    
    plt.tight_layout()
    plt.savefig('问题2_运输网络_损耗成本.png', dpi=300, bbox_inches='tight')
    print("  ✓ 已保存: 问题2_运输网络_损耗成本.png")
    plt.close()
    
    # 打印统计信息
    print(f"\n【问题2统计信息】")
    print(f"  开仓数量: {df_performance_loss['开仓数量'].values[0]} 个")
    print(f"  时效满足率: {df_performance_loss['时效满足率'].values[0]:.4f}")
    print(f"  总物流成本: {df_performance_loss['总物流成本（单位：万元）'].values[0]:.2f} 万元")
    print(f"  运输损耗总成本: {df_performance_loss['运输损耗总成本（单位：万元）'].values[0]:.2f} 万元")
    
    print(f"\n【运输时间分级详情】")
    print(f"  ≤500分钟: {len(low_time_links)} 条")
    print(f"  500-600分钟: {len(mid_time_links)} 条")
    print(f"  >600分钟: {len(high_time_links)} 条")
    
    if high_time_links:
        print(f"\n  >600分钟调拨详情：")
        for link in high_time_links[:20]:
            print(f"    {link['from']} → {link['to']}: {link['qty']:.1f}吨, {link['duration']:.0f}分钟, 损耗 {link['loss']:.1f}万元")
        if len(high_time_links) > 20:
            print(f"    ... 还有 {len(high_time_links) - 20} 条")
    
    print(f"\n【损耗成本分布】")
    total_loss_cost = df_performance_loss['运输损耗总成本（单位：万元）'].values[0]
    print(f"  总损耗成本: {total_loss_cost:.2f} 万元")
    
except ImportError:
    print("  ⚠  跳过：未安装 cartopy 库")

print("\n" + "="*80)
print("可视化完成！")
print("生成的PNG图片：")
print("  - 问题2_运输网络_损耗成本.png")
print("="*80)
