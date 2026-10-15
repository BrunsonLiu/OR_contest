# -*- coding: utf-8 -*-
"""
问题2结果可视化脚本（最高的15条损失路径）

显示损耗成本最高的15条运输路径
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
print("问题2结果可视化（最高的15条损失路径）")
print("="*80)

# ==================== 数据加载 ====================
output_dir = str(_REPO_ROOT / 'results/question2')
input_dir = str(_REPO_ROOT / 'data/raw')

print("\n【数据加载】")
try:
    df_performance_loss = pd.read_csv(os.path.join(output_dir, '仓网业务表现文件_运输损耗_cplex.csv'))
    print("  ✓ 仓网业务表现文件（运输损耗）")
    
    df_wh_loss = pd.read_csv(os.path.join(output_dir, '仓→仓损耗明细文件_完整版_cplex.csv'))
    print("  ✓ 仓→仓损耗明细文件")
    
    df_cust_loss = pd.read_csv(os.path.join(output_dir, '仓→店损耗明细文件_完整版_cplex.csv'))
    print("  ✓ 仓→店损耗明细文件")
    
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
        warehouse_coords[wh_name] = {
            'coords': city_coords[wh_location],
            'type': row['Type']
        }

print(f"  ✓ 加载了 {len(warehouse_coords)} 个仓库坐标")

# ==================== 数据预处理 ====================
print("\n【数据预处理】")

# 合并所有损耗数据
all_loss_links = []

# 1. 仓→仓损耗数据
for _, row in df_wh_loss.iterrows():
    from_wh = row['From_wh']
    to_wh = row['To_wh']
    qty = row['Qty（单位：吨）']
    duration = row['运输时间(分钟)']
    loss = row['总损耗成本(万元)']
    
    if loss > 0:
        all_loss_links.append({
            'from': from_wh,
            'to': to_wh,
            'qty': qty,
            'duration': duration,
            'loss': loss,
            'type': '仓→仓'
        })

print(f"  ✓ 仓→仓损耗数据: {len([l for l in all_loss_links if l['type'] == '仓→仓'])} 条")

# 2. 仓→店损耗数据
for _, row in df_cust_loss.iterrows():
    from_wh = row['From_wh']
    to_city = row['To_city']
    to_store = row['To_store']
    qty = row['Qty（单位：吨）']
    duration = row['运输时间(分钟)']
    loss = row['总损耗成本(万元)']
    
    if loss > 0:
        all_loss_links.append({
            'from': from_wh,
            'to': to_city,
            'to_store': to_store,
            'qty': qty,
            'duration': duration,
            'loss': loss,
            'type': '仓→店'
        })

print(f"  ✓ 仓→店损耗数据: {len([l for l in all_loss_links if l['type'] == '仓→店'])} 条")

# 按损耗成本排序
all_loss_links_sorted = sorted(all_loss_links, key=lambda x: x['loss'], reverse=True)

print(f"\n【损耗路径统计】")
print(f"  总损耗路径数: {len(all_loss_links)} 条")
print(f"  总损耗成本: {sum(l['loss'] for l in all_loss_links):.2f} 万元")

# 显示最高的15条损耗路径
print(f"\n【损耗成本最高的15条路径】")
for i, link in enumerate(all_loss_links_sorted[:15], 1):
    print(f"  {i:2d}. {link['from']} → {link['to']}: {link['loss']:.2f}万元 ({link['qty']:.1f}吨, {link['duration']:.0f}分钟)")

# ==================== 可视化：最高的15条损失路径 ====================
print("\n【可视化】最高的15条损失路径...")

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
    
    # 绘制最高的15条损耗路径
    print("\n  绘制损耗路径...")
    top15_links = all_loss_links_sorted[:15]
    
    for i, link in enumerate(top15_links, 1):
        from_coords = warehouse_coords[link['from']]['coords']
        
        # 获取目标坐标
        if link['type'] == '仓→仓':
            to_coords = warehouse_coords[link['to']]['coords']
        else:  # 仓→店
            to_city = link['to']
            to_coords = city_coords.get(to_city)
            if to_coords is None:
                continue
        
        # 根据损耗成本设置颜色和线宽
        loss = link['loss']
        if loss >= 3000:
            color = 'red'
            alpha = 0.9
            linewidth = 4
            linestyle = '--'
        elif loss >= 1000:
            color = 'orange'
            alpha = 0.8
            linewidth = 3
            linestyle = '-'
        else:
            color = 'darkred'
            alpha = 0.7
            linewidth = 2
            linestyle = '-'
        
        ax.plot([from_coords[0], to_coords[0]], 
               [from_coords[1], to_coords[1]], 
               color=color, linewidth=linewidth, alpha=alpha,
               linestyle=linestyle, transform=ccrs.PlateCarree(), zorder=2)
        
        # 标注损耗成本
        mid_x = (from_coords[0] + to_coords[0]) / 2
        mid_y = (from_coords[1] + to_coords[1]) / 2
        ax.text(mid_x, mid_y + 0.2, f'{loss:.0f}万', fontsize=9, 
               fontproperties='SimHei', transform=ccrs.PlateCarree(),
               bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', 
                        alpha=0.9, edgecolor=color, linewidth=1.5))
        
        print(f"    ✓ {i:2d}. {link['from']} → {link['to']}: {loss:.2f}万元")
    
    ax.set_title('问题2：损耗成本最高的15条路径', fontsize=16, fontweight='bold', fontproperties='SimHei')
    
    # 添加图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor='red', markersize=12, 
               markeredgecolor='darkred', markeredgewidth=2.5, label=f'CDC（中心仓）{cdc_count}个'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='steelblue', markersize=10, 
               markeredgecolor='darkblue', markeredgewidth=2.5, label=f'RDC（区域仓）{rdc_count}个'),
        Line2D([0], [0], marker='^', color='w', markerfacecolor='green', markersize=10, 
               markeredgecolor='darkgreen', markeredgewidth=2.5, label=f'Factory（工厂）{factory_count}个'),
        Line2D([0], [0], color='red', linewidth=4, linestyle='--', alpha=0.9, label='≥3000万元（红色，粗虚线）'),
        Line2D([0], [0], color='orange', linewidth=3, linestyle='-', alpha=0.8, label='1000-3000万元（橙色，中实线）'),
        Line2D([0], [0], color='darkred', linewidth=2, linestyle='-', alpha=0.7, label='1000万元以下（深红，细实线）'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', prop={'family': 'SimHei', 'size': 11})
    
    plt.tight_layout()
    plt.savefig('问题2_损耗成本最高的15条路径.png', dpi=150, bbox_inches='tight')
    print("\n  ✓ 已保存: 问题2_损耗成本最高的15条路径.png")
    plt.close()
    
    # 打印统计信息
    print(f"\n【问题2统计信息】")
    print(f"  开仓数量: {df_performance_loss['开仓数量'].values[0]} 个")
    print(f"  时效满足率: {df_performance_loss['时效满足率'].values[0]:.4f}")
    print(f"  总物流成本: {df_performance_loss['总物流成本（单位：万元）'].values[0]:.2f} 万元")
    print(f"  运输损耗总成本: {df_performance_loss['运输损耗总成本（单位：万元）'].values[0]:.2f} 万元")
    
    if len(all_loss_links) > 15:
        top15_loss = sum(l['loss'] for l in all_loss_links_sorted[:15])
        print(f"  前15条路径损耗占比: {top15_loss/sum(l['loss'] for l in all_loss_links)*100:.2f}%")
    
except ImportError:
    print("  ⚠  跳过：未安装 cartopy 库")

print("\n" + "="*80)
print("可视化完成！")
print("生成的PNG图片：")
print("  - 问题2_损耗成本最高的15条路径.png")
print("="*80)
