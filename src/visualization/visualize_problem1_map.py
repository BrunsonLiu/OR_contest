# -*- coding: utf-8 -*-
"""
问题1结果可视化脚本（带中国地图背景）

使用 cartopy 绘制真实的中国地图背景，展示仓库分布
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
print("问题1结果可视化（带中国地图背景）")
print("="*80)

# ==================== 数据加载 ====================
output_dir = str(_RESULTS_ROOT / 'question1')

print("\n【数据加载】")
try:
    df_business = pd.read_csv(os.path.join(output_dir, '仓网业务表现文件_cplex.csv'))
    print("  ✓ 仓网业务表现文件")
    
    df_supply = pd.read_csv(os.path.join(output_dir, '仓网供应关系文件_cplex.csv'))
    print("  ✓ 仓网供应关系文件")
    
    df_wh = pd.read_csv(os.path.join(output_dir, '仓库处置订单量文件_cplex.csv'))
    print("  ✓ 仓库处置订单量文件")
except Exception as e:
    print(f"  ✗ 加载失败: {e}")
    sys.exit(1)

# ==================== 仓库地理坐标映射 ====================
from src.geography import warehouse_coordinates
warehouse_coords = warehouse_coordinates()

# ==================== 数据预处理 ====================
print("\n【数据预处理】")

T = len(df_business)

# 1. 仓库处置订单量
wh_qty = {}
for _, row in df_wh.iterrows():
    wh = row['Name']
    qty = row['Qty（单位：吨）']
    if wh in warehouse_coords:
        if wh not in wh_qty:
            wh_qty[wh] = 0
        wh_qty[wh] += qty

print(f"  ✓ 处理 {len(wh_qty)} 个仓库的订单量")

# 2. 供应关系
supply_links = []
for _, row in df_supply.iterrows():
    from_wh = row['Name']
    to_wh = row['Customer']
    qty = row['Qty（单位：吨）']
    
    if from_wh in warehouse_coords and to_wh in warehouse_coords:
        supply_links.append({
            'from': from_wh,
            'to': to_wh,
            'qty': qty
        })

print(f"  ✓ 处理 {len(supply_links)} 条运输关系")

# ==================== 可视化1：带中国地图的仓库分布 ====================
print("\n【可视化1】带中国地图的仓库分布...")

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    
    fig = plt.figure(figsize=(14, 10))
    ax = plt.axes(projection=ccrs.PlateCarree())
    
    # 添加地图要素
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
    ax.add_feature(cfeature.BORDERS, linestyle='-', linewidth=0.8)
    ax.add_feature(cfeature.LAKES, alpha=0.5)
    ax.add_feature(cfeature.RIVERS, linewidth=0.5)
    
    # 设置地图范围（中国）
    ax.set_extent([73, 136, 18, 54], crs=ccrs.PlateCarree())
    
    # 绘制仓库
    for wh, coords in warehouse_coords.items():
        qty = wh_qty.get(wh, 0)
        size = 80 + 400 * qty / max(max(wh_qty.values(), default=0), 1)  # 根据数量调整大小
        is_cdc = wh.endswith('-CDC')
        color = 'red' if qty > 0 else 'blue'
        marker = 's' if is_cdc else 'o'  # CDC用正方形，RDC用圆形
        
        ax.scatter(coords[0], coords[1], s=size, c=color, alpha=0.8,
                   edgecolors='darkred' if qty > 0 else 'darkblue', 
                   linewidths=2, marker=marker, transform=ccrs.PlateCarree())
        
        # 添加标签
        ax.text(coords[0] + 0.5, coords[1] + 0.3, wh, fontsize=9, 
                fontproperties='SimHei', transform=ccrs.PlateCarree(),
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                         alpha=0.8, edgecolor='gray'))
    
    ax.set_title('问题1：仓网仓库分布（带中国地图）', fontsize=14, fontweight='bold', fontproperties='SimHei')
    
    # 添加图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor='red', markersize=10, 
               markeredgecolor='darkred', markeredgewidth=2, label='CDC（有订单）'),
        Line2D([0], [0], marker='s', color='w', markerfacecolor='blue', markersize=10, 
               markeredgecolor='darkblue', markeredgewidth=2, label='CDC（无订单）'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=10, 
               markeredgecolor='darkred', markeredgewidth=2, label='RDC（有订单）'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', markersize=10, 
               markeredgecolor='darkblue', markeredgewidth=2, label='RDC（无订单）'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', prop={'family': 'SimHei'})
    
    plt.tight_layout()
    plt.savefig(str(_PLOT_DIR / '问题1_仓库分布_地图.png'), dpi=300, bbox_inches='tight')
    print("  ✓ 已保存: 问题1_仓库分布_地图.png")
    plt.close()
    
except ImportError:
    print("  ⚠  跳过：未安装 cartopy 库")
    print("  提示：pip install cartopy")

# ==================== 可视化2：带中国地图的运输网络 ====================
print("\n【可视化2】带中国地图的运输网络...")

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    
    fig = plt.figure(figsize=(14, 10))
    ax = plt.axes(projection=ccrs.PlateCarree())
    
    # 添加地图要素
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
    ax.add_feature(cfeature.BORDERS, linestyle='-', linewidth=0.8)
    ax.add_feature(cfeature.LAKES, alpha=0.3)
    ax.add_feature(cfeature.RIVERS, linewidth=0.3)
    
    # 设置地图范围
    ax.set_extent([73, 136, 18, 54], crs=ccrs.PlateCarree())
    
    # 绘制仓库
    for wh, coords in warehouse_coords.items():
        qty = wh_qty.get(wh, 0)
        size = 80 + 400 * qty / max(max(wh_qty.values(), default=0), 1)
        color = 'steelblue' if qty > 0 else 'lightblue'
        
        ax.scatter(coords[0], coords[1], s=size, c=color, alpha=0.9, 
                   edgecolors='darkblue', linewidths=2, transform=ccrs.PlateCarree())
        
        ax.text(coords[0] + 0.3, coords[1] + 0.2, wh, fontsize=8, 
                fontproperties='SimHei', transform=ccrs.PlateCarree(),
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', 
                         alpha=0.7, edgecolor='gray'))
    
    # 绘制运输连接
    for link in supply_links[:80]:  # 显示前80条
        from_wh = link['from']
        to_wh = link['to']
        qty = link['qty']
        
        if from_wh in warehouse_coords and to_wh in warehouse_coords:
            from_coords = warehouse_coords[from_wh]
            to_coords = warehouse_coords[to_wh]
            
            linewidth = min(3, max(0.5, qty / 150))
            color = 'orange' if qty > 500 else 'green' if qty > 200 else 'blue'
            
            ax.plot([from_coords[0], to_coords[0]], 
                   [from_coords[1], to_coords[1]], 
                   color=color, linewidth=linewidth, alpha=0.7,
                   linestyle='-', transform=ccrs.PlateCarree())
    
    ax.set_title('问题1：仓网运输网络（带中国地图）', fontsize=14, fontweight='bold', fontproperties='SimHei')
    
    # 添加图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='steelblue', markersize=10, 
               markeredgecolor='darkblue', markeredgewidth=2, label='仓库'),
        Line2D([0], [0], color='orange', linewidth=3, label='运量 > 500吨'),
        Line2D([0], [0], color='green', linewidth=2, label='200-500吨'),
        Line2D([0], [0], color='blue', linewidth=1, label='运量 < 200吨'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', prop={'family': 'SimHei'})
    
    plt.tight_layout()
    plt.savefig(str(_PLOT_DIR / '问题1_运输网络_地图.png'), dpi=300, bbox_inches='tight')
    print("  ✓ 已保存: 问题1_运输网络_地图.png")
    plt.close()
    
except ImportError:
    print("  ⚠  跳过：未安装 cartopy 库")

# ==================== 可视化3：综合报告（地图+成本构成） ====================
print("\n【可视化3】综合报告（地图+成本构成）...")

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    
    fig = plt.figure(figsize=(12, 8))
    fig.suptitle('问题1：仓网配送优化结果', fontsize=14, fontweight='bold', fontproperties='SimHei')
    
    # 子图1：地图上的仓库分布（左侧55%宽度）
    ax1 = plt.axes([0.02, 0.08, 0.55, 0.88], projection=ccrs.PlateCarree())
    ax1.add_feature(cfeature.COASTLINE, linewidth=0.5)
    ax1.add_feature(cfeature.BORDERS, linestyle='-', linewidth=0.8)
    ax1.set_extent([73, 136, 18, 54], crs=ccrs.PlateCarree())
    
    for wh, coords in warehouse_coords.items():
        qty = wh_qty.get(wh, 0)
        size = 80 + 400 * qty / max(max(wh_qty.values(), default=0), 1)
        color = 'red' if qty > 0 else 'blue'
        ax1.scatter(coords[0], coords[1], s=size, c=color, alpha=0.8,
                   edgecolors='darkred' if qty > 0 else 'darkblue', 
                   linewidths=1.5, transform=ccrs.PlateCarree())
        ax1.text(coords[0] + 0.3, coords[1] + 0.2, wh, fontsize=8, 
                fontproperties='SimHei', transform=ccrs.PlateCarree(),
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', 
                         alpha=0.7, edgecolor='gray'))
    ax1.set_title('仓库分布', fontproperties='SimHei', fontsize=12, fontweight='bold')
    
    # 添加图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=8, 
               markeredgecolor='darkred', markeredgewidth=1.5, label='有订单量'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', markersize=6, 
               markeredgecolor='darkblue', markeredgewidth=1.5, label='无订单量'),
    ]
    ax1.legend(handles=legend_elements, loc='upper right', prop={'family': 'SimHei'}, fontsize=9)
    
    # 子图2：成本构成（右侧40%宽度）
    ax2 = fig.add_axes([0.62, 0.10, 0.35, 0.85])
    total_cost = df_business['总物流成本（单位：万元）'].sum()
    transport_cost = df_business['仓库之间的运输总成本（单位：万元）'].sum()
    to_customer_cost = df_business['仓库到门店的运输总成本（单位：万元）'].sum()
    open_cost = df_business['开仓总成本（单位：万元）'].sum()
    process_cost = df_business['出入仓处置总成本（单位：万元）'].sum()
    smart_cost = df_business['智能调度系统采购总成本（单位：万元）'].sum()
    
    labels = ['仓库间运输', '到门店运输', '开仓成本', '处置成本', '智能系统']
    sizes = [transport_cost, to_customer_cost, open_cost, process_cost, smart_cost]
    colors = ['#4A90E2', '#50E3C2', '#F5A623', '#9013FE', '#BD10E0']
    wedges, texts, autotexts = ax2.pie(sizes, labels=labels, autopct='%1.0f%%', startangle=120, 
           textprops={'fontproperties': 'SimHei', 'fontsize': 10}, colors=colors, pctdistance=0.8,
           wedgeprops=dict(width=0.5, edgecolor='white'))
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    ax2.set_title('成本构成', fontproperties='SimHei', fontsize=12, fontweight='bold')
    
    # 添加统计信息框
    time_rates = (df_business['时效满足率'] * 100).tolist()
    stats_text = f"""总物流成本：{total_cost:.2f} 万元
开仓数量：{len(wh_qty)} 个
时效满足率：{sum(time_rates)/len(time_rates):.2f}%"""
    
    ax2.text(1.4, 0.5, stats_text, fontsize=10, verticalalignment='center',
            fontproperties='SimHei', bbox=dict(boxstyle='round,pad=0.5', facecolor='#E8F4FD', 
                                              alpha=0.9, edgecolor='#4A90E2', linewidth=1.5))
    
    plt.savefig(str(_PLOT_DIR / '问题1_综合报告_地图.png'), dpi=300, bbox_inches='tight')
    print("  ✓ 已保存: 问题1_综合报告_地图.png")
    plt.close()
    
except ImportError:
    print("  ⚠  跳过：未安装 cartopy 库")

print("\n" + "="*80)
print("可视化完成！")
print("生成的PNG图片（带中国地图）：")
print("  - 问题1_仓库分布_地图.png")
print("  - 问题1_运输网络_地图.png")
print("  - 问题1_综合报告_地图.png")
print("="*80)
