# -*- coding: utf-8 -*-
"""
问题1：所有备选仓库位置可视化

显示所有备选的CDC、RDC和Factory位置，用于论文展示候选集
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
print("问题1：所有备选仓库位置可视化")
print("="*80)

# ==================== 数据加载 ====================
input_dir = str(_REPO_ROOT / 'data/raw')

print("\n【数据加载】")
try:
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
        print(f"  ✓ {wh_name} ({row['Type']}): {city_coords[wh_location]}")
    else:
        print(f"  ⚠ 未找到 {wh_name} ({wh_location}) 的坐标")

# ==================== 可视化：所有备选仓库 ====================
print("\n【可视化】所有备选仓库位置...")

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
    
    ax.set_title('问题1：所有备选仓库位置（候选集）', fontsize=16, fontweight='bold', fontproperties='SimHei')
    
    # 添加图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor='red', markersize=12, 
               markeredgecolor='darkred', markeredgewidth=2.5, label=f'CDC（中心仓）{cdc_count}个'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='steelblue', markersize=10, 
               markeredgecolor='darkblue', markeredgewidth=2.5, label=f'RDC（区域仓）{rdc_count}个'),
        Line2D([0], [0], marker='^', color='w', markerfacecolor='green', markersize=10, 
               markeredgecolor='darkgreen', markeredgewidth=2.5, label=f'Factory（工厂）{factory_count}个'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', prop={'family': 'SimHei', 'size': 12})
    
    plt.tight_layout()
    plt.savefig(str(_PLOT_DIR / '问题1_所有备选仓库位置.png'), dpi=300, bbox_inches='tight')
    print("  ✓ 已保存: 问题1_所有备选仓库位置.png")
    plt.close()
    
    # 打印统计信息
    print(f"\n【统计信息】")
    print(f"  CDC（中心仓）: {cdc_count} 个")
    print(f"  RDC（区域仓）: {rdc_count} 个")
    print(f"  Factory（工厂）: {factory_count} 个")
    print(f"  总计: {len(warehouse_coords)} 个备选仓库")
    
except ImportError:
    print("  ⚠  跳过：未安装 cartopy 库")

print("\n" + "="*80)
print("可视化完成！")
print("生成的PNG图片：")
print("  - 问题1_所有备选仓库位置.png")
print("="*80)
