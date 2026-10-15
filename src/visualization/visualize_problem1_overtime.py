# -*- coding: utf-8 -*-
"""
问题1结果可视化脚本（运输网络+超时路径）

显示仓库到门店的运输网络，并标出超时的路径
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _runtime_sys
_runtime_sys.path.insert(0, str(_REPO_ROOT))
from src.runtime import results_root as _results_root, read_forecast as _read_forecast, configure_solver as _configure_solver, record_solver as _record_solver
_RESULTS_ROOT = _results_root()
_PLOT_DIR = _RESULTS_ROOT / 'question1'
_PLOT_DIR.mkdir(parents=True, exist_ok=True)

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
print("问题1结果可视化（仓库到门店的运输网络+超时路径）")
print("="*80)

# ==================== 数据加载 ====================
output_dir = str(_RESULTS_ROOT / 'question1')
input_dir = str(_REPO_ROOT / 'data/raw')

print("\n【数据加载】")
try:
    df_supply = pd.read_csv(os.path.join(output_dir, '仓网供应关系文件_cplex.csv'))
    print("  ✓ 仓网供应关系文件")
    
    df_matrix = pd.read_csv(os.path.join(input_dir, 'df_matrix.csv'))
    print("  ✓ 运输矩阵文件（df_matrix.csv）")
    
    df_customer = pd.read_csv(os.path.join(input_dir, 'df_customer.csv'))
    print("  ✓ 客户文件（df_customer.csv）")
    
    df_order = pd.read_csv(os.path.join(input_dir, 'df_order.csv'))
    print("  ✓ 订单文件（df_order.csv）")
    
    df_wh = pd.read_csv(os.path.join(input_dir, 'df_wh.csv'))
    print("  ✓ 仓库文件（df_wh.csv）")
    
    df_loc = pd.read_csv(os.path.join(input_dir, 'df_loc.csv'))
    print("  ✓ 城市位置文件（df_loc.csv）")
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
for _, row in df_wh.iterrows():
    wh_name = row['Name']
    wh_location = row['Location']
    
    # 从city_coords获取坐标
    if wh_location in city_coords:
        warehouse_coords[wh_name] = city_coords[wh_location]
        print(f"  ✓ {wh_name} -> {wh_location}: {city_coords[wh_location]}")
    else:
        print(f"  ⚠ 未找到 {wh_name} ({wh_location}) 的坐标")

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

# 创建城市到门店的反向映射（用于查找门店坐标）
city_to_stores = {}
for store_name, city_name in store_city_map.items():
    if city_name not in city_to_stores:
        city_to_stores[city_name] = []
    city_to_stores[city_name].append(store_name)

# 3. 加载订单数据
demand = {}
for _, row in df_order.iterrows():
    demand[(row['Name'], row['SKU'])] = row['qty']

# 4. 处理供应关系 - 只处理仓库到门店的配送
print("  ✓ 处理供应关系...")

# 识别CDC和RDC
cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist() if 'Type' in df_wh.columns else []
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist() if 'Type' in df_wh.columns else []

# 识别港口CDC和内陆CDC
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0] if cdc_names else 'gang-kou-CDC'
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0] if cdc_names else 'nei-lu-CDC'

# 统计仓库订单量
wh_qty = {}
for _, row in df_supply.iterrows():
    from_wh = row['Name']
    to_wh = row['Customer']
    qty = row['Qty（单位：吨）']
    
    # 只统计仓库到门店的配送（Customer是城市/门店，不是仓库）
    if from_wh in warehouse_coords and to_wh not in warehouse_coords:
        if from_wh not in wh_qty:
            wh_qty[from_wh] = 0
        wh_qty[from_wh] += qty

print(f"  ✓ 处理 {len(wh_qty)} 个仓库的订单量")

# 5. 识别超时路径（Duration > 600分钟算超时）
overtime_links = []
normal_links = []

for _, row in df_supply.iterrows():
    from_wh = row['Name']
    to_wh = row['Customer']
    qty = row['Qty（单位：吨）']
    
    # 只处理仓库到门店的配送
    if from_wh in warehouse_coords and to_wh not in warehouse_coords:
        # 获取从仓库到门店的Duration（通过城市映射）
        duration = None
        
        # 尝试直接查找仓库到城市
        if (from_wh, to_wh) in duration_dict:
            duration = duration_dict[(from_wh, to_wh)]
        else:
            # 尝试查找仓库到门店（如果to_wh是门店名）
            for store_name in store_city_map.keys():
                if store_city_map[store_name] == to_wh:
                    if (from_wh, store_name) in duration_dict:
                        duration = duration_dict[(from_wh, store_name)]
                        break
        
        # Duration > 600分钟算超时
        is_overtime = duration is not None and duration > 600
        
        link_info = {
            'from': from_wh,
            'to': to_wh,
            'qty': qty,
            'duration': duration,
            'is_overtime': is_overtime
        }
        
        if is_overtime:
            overtime_links.append(link_info)
        else:
            normal_links.append(link_info)

print(f"  ✓ 识别超时路径: {len(overtime_links)} 条")
print(f"  ✓ 正常路径: {len(normal_links)} 条")

# 显示实际使用的仓库
print(f"\n【实际使用的仓库】")
print(f"  CDC（中心仓）: {[w for w in warehouse_coords.keys() if w.endswith('-CDC')]}")
print(f"  RDC（区域仓）: {[w for w in warehouse_coords.keys() if not w.endswith('-CDC')]}")
print(f"  总计: {len(warehouse_coords)} 个仓库")

# ==================== 可视化：运输网络（标出超时路径） ====================
print("\n【可视化】仓库到门店的运输网络（标出超时路径）...")

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import cartopy.io.img_tiles as cimgt
    
    fig = plt.figure(figsize=(16, 10))
    ax = plt.axes(projection=ccrs.PlateCarree())
    
    # 添加地图要素
    ax.add_feature(cfeature.COASTLINE, linewidth=0.6)
    ax.add_feature(cfeature.BORDERS, linestyle='-', linewidth=0.9)
    ax.add_feature(cfeature.LAKES, alpha=0.3)
    ax.add_feature(cfeature.RIVERS, linewidth=0.4)
    
    # 设置地图范围
    ax.set_extent([73, 136, 18, 54], crs=ccrs.PlateCarree())
    
    # 绘制CDC（红色正方形）
    for wh, coords in warehouse_coords.items():
        if wh.endswith('-CDC'):
            ax.scatter(coords[0], coords[1], s=200, c='red', alpha=0.9, 
                      marker='s', edgecolors='darkred', linewidths=2, 
                      transform=ccrs.PlateCarree(), zorder=5)
            ax.text(coords[0] + 0.3, coords[1] + 0.2, wh, fontsize=9, 
                   fontproperties='SimHei', transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', 
                            alpha=0.8, edgecolor='darkred'))
    
    # 绘制RDC（蓝色圆形）
    for wh, coords in warehouse_coords.items():
        if not wh.endswith('-CDC'):
            ax.scatter(coords[0], coords[1], s=120, c='steelblue', alpha=0.9, 
                      marker='o', edgecolors='darkblue', linewidths=2, 
                      transform=ccrs.PlateCarree(), zorder=5)
            ax.text(coords[0] + 0.3, coords[1] + 0.2, wh, fontsize=8, 
                   fontproperties='SimHei', transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', 
                            alpha=0.7, edgecolor='darkblue'))
    
    # 识别所有客户城市（从供应关系中提取）
    customer_cities = set()
    for _, row in df_supply.iterrows():
        to_wh = row['Customer']
        if to_wh not in warehouse_coords:
            customer_cities.add(to_wh)
    
    print(f"  ✓ 识别 {len(customer_cities)} 个客户城市")
    
    # 绘制客户城市（灰色小圆点，不标注名称避免混乱）
    customer_coords_used = set()
    for city in customer_cities:
        if city in city_coords and city not in warehouse_coords:
            coords = city_coords[city]
            # 避免重复绘制相同坐标
            coord_tuple = (coords[0], coords[1])
            if coord_tuple not in customer_coords_used:
                ax.scatter(coords[0], coords[1], s=30, c='gray', alpha=0.6, 
                          marker='o', transform=ccrs.PlateCarree(), zorder=3)
                customer_coords_used.add(coord_tuple)
    
    # 绘制正常运输连接（绿色，低透明度避免混乱）
    for link in normal_links:
        from_coords = warehouse_coords[link['from']]
        
        # 使用城市坐标
        to_coords = city_coords.get(link['to'], [from_coords[0] + 0.5, from_coords[1] + 0.5])
        
        linewidth = min(3, max(0.5, link['qty'] / 150))
        
        ax.plot([from_coords[0], to_coords[0]], 
               [from_coords[1], to_coords[1]], 
               color='green', linewidth=linewidth, alpha=0.4,
               linestyle='-', transform=ccrs.PlateCarree(), zorder=1)
    
    # 绘制超时运输连接（红色虚线，高透明度）
    for link in overtime_links:
        from_coords = warehouse_coords[link['from']]
        
        # 使用城市坐标
        to_coords = city_coords.get(link['to'], [from_coords[0] + 0.5, from_coords[1] + 0.5])
        
        linewidth = min(4, max(1.0, link['qty'] / 100))
        
        ax.plot([from_coords[0], to_coords[0]], 
               [from_coords[1], to_coords[1]], 
               color='red', linewidth=linewidth, alpha=0.9,
               linestyle='--', transform=ccrs.PlateCarree(), zorder=2)
        
        # 标注Duration（分钟）
        mid_x = (from_coords[0] + to_coords[0]) / 2
        mid_y = (from_coords[1] + to_coords[1]) / 2
        ax.text(mid_x, mid_y + 0.3, f'{link["duration"]:.0f}min', fontsize=7, 
               fontproperties='SimHei', transform=ccrs.PlateCarree(),
               bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', 
                        alpha=0.8, edgecolor='red'))
    
    ax.set_title('问题1：仓网运输网络（仓库→门店，标出超时路径）', fontsize=14, fontweight='bold', fontproperties='SimHei')
    
    # 添加图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor='red', markersize=10, 
               markeredgecolor='darkred', markeredgewidth=2, label='CDC（中心仓）'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='steelblue', markersize=8, 
               markeredgecolor='darkblue', markeredgewidth=2, label='RDC（区域仓）'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='gray', markersize=5, 
               markeredgecolor='gray', alpha=0.6, label='客户城市'),
        Line2D([0], [0], color='green', linewidth=2, label='正常运输（≤600分钟）'),
        Line2D([0], [0], color='red', linewidth=2, linestyle='--', label='超时路径（>600分钟）'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', prop={'family': 'SimHei'})
    
    plt.tight_layout()
    plt.savefig(str(_PLOT_DIR / '问题1_运输网络_超时路径.png'), dpi=300, bbox_inches='tight')
    print("  ✓ 已保存: 问题1_运输网络_超时路径.png")
    plt.close()
    
    # 打印超时路径详情
    if overtime_links:
        print("\n【超时路径详情】")
        for link in overtime_links[:20]:  # 只显示前20条
            print(f"  {link['from']} → {link['to']}: {link['qty']}吨, {link['duration']:.0f}分钟")
        if len(overtime_links) > 20:
            print(f"  ... 还有 {len(overtime_links) - 20} 条超时路径")
    
except ImportError:
    print("  ⚠  跳过：未安装 cartopy 库")

print("\n" + "="*80)
print("可视化完成！")
print("生成的PNG图片：")
print("  - 问题1_运输网络_超时路径.png")
print("="*80)
