# -*- coding: utf-8 -*-
"""
问题4路线变化可视化
在地图上显示7天运输量变化最大的路线
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _runtime_sys
_runtime_sys.path.insert(0, str(_REPO_ROOT))
from src.runtime import results_root as _results_root, read_forecast as _read_forecast, configure_solver as _configure_solver, record_solver as _record_solver
_RESULTS_ROOT = _results_root()

import pandas as pd
import os
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.lines import Line2D
from collections import defaultdict
import numpy as np

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

print("="*80)
print("问题4路线变化地图可视化")
print("="*80)

output_dir = str(_RESULTS_ROOT / 'question4/problem4_noloss/output_result')
input_dir = str(_REPO_ROOT / 'data/raw')

print("\n【数据加载】")
df_wh = pd.read_csv(os.path.join(input_dir, 'df_wh.csv'))
df_loc = pd.read_csv(os.path.join(input_dir, 'df_loc.csv'))
print("  ✓ 仓库文件")
print("  ✓ 城市位置文件")

city_coords = {}
for _, row in df_loc.iterrows():
    city_name = row['Location']
    longitude = row['Longitude']
    latitude = row['Latitude']
    if pd.notna(longitude) and pd.notna(latitude):
        city_coords[city_name] = [longitude, latitude]

warehouse_coords = {}
location_to_city = {}
for _, row in df_wh.iterrows():
    wh_name = row['Name']
    wh_location = row['Location']
    if wh_location in city_coords:
        warehouse_coords[wh_name] = {
            'coords': city_coords[wh_location],
            'type': row['Type']
        }
        location_to_city[wh_name] = wh_location

print(f"  ✓ 加载了 {len(city_coords)} 个城市坐标")
print(f"  ✓ 加载了 {len(warehouse_coords)} 个仓库坐标")

def get_coords(name):
    if name in warehouse_coords:
        return warehouse_coords[name]['coords']
    if name in city_coords:
        return city_coords[name]
    return None

days = ['06-24', '06-25', '06-26', '06-27', '06-28', '06-29', '06-30']
all_keys = defaultdict(list)

for day in days:
    df = pd.read_csv(os.path.join(output_dir, f'仓网供应关系文件_2016-{day}.csv'))
    df['key'] = df['仓库名称'] + '|' + df['服务对象'] + '|' + df['商品类型']
    for idx, row in df.iterrows():
        key = row['key']
        all_keys[key].append({'day': day, 'qty': row['数量（吨）']})

print(f"  ✓ 加载了 {len(all_keys)} 条路线")

key_var = {}
for key, records in all_keys.items():
    qties = [r['qty'] for r in records]
    key_var[key] = max(qties) - min(qties)

top_changed = sorted(key_var.items(), key=lambda x: x[1], reverse=True)[:20]

print("\n【变化最大的20条路线】")
for i, (key, var) in enumerate(top_changed[:10], 1):
    records = all_keys[key]
    parts = key.split('|')
    from_wh = parts[0]
    to_loc = parts[1]
    sku = parts[2]
    print(f"  {i:2d}. {from_wh} → {to_loc} ({sku}): 波动 {var:.1f}吨")

print("\n【可视化】")

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    fig = plt.figure(figsize=(18, 14))
    ax = plt.axes(projection=ccrs.PlateCarree())

    ax.add_feature(cfeature.COASTLINE, linewidth=0.6)
    ax.add_feature(cfeature.BORDERS, linestyle='-', linewidth=0.9)
    ax.add_feature(cfeature.LAKES, alpha=0.3)
    ax.add_feature(cfeature.RIVERS, linewidth=0.4)

    ax.set_extent([73, 136, 18, 54], crs=ccrs.PlateCarree())

    cdc_count = 0
    rdc_count = 0
    city_count = 0

    for wh, info in warehouse_coords.items():
        if info['type'] == 'CDC':
            coords = info['coords']
            ax.scatter(coords[0], coords[1], s=300, c='red', alpha=0.9,
                      marker='s', edgecolors='darkred', linewidths=3,
                      transform=ccrs.PlateCarree(), zorder=5)
            ax.text(coords[0] + 0.3, coords[1] + 0.3, wh, fontsize=10,
                   fontproperties='SimHei', transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                            alpha=0.9, edgecolor='darkred', linewidth=2))
            cdc_count += 1

    for wh, info in warehouse_coords.items():
        if info['type'] == 'RDC':
            coords = info['coords']
            ax.scatter(coords[0], coords[1], s=200, c='steelblue', alpha=0.9,
                      marker='o', edgecolors='darkblue', linewidths=2.5,
                      transform=ccrs.PlateCarree(), zorder=5)
            ax.text(coords[0] + 0.3, coords[1] + 0.3, wh, fontsize=9,
                   fontproperties='SimHei', transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                            alpha=0.9, edgecolor='darkblue', linewidth=1.5))
            rdc_count += 1

    plotted_cities = set()
    print("\n  绘制路线...")
    top15 = top_changed[:15]

    for rank, (key, var) in enumerate(top15, 1):
        records = all_keys[key]
        parts = key.split('|')
        from_wh = parts[0]
        to_loc = parts[1]
        sku = parts[2]

        from_coords = get_coords(from_wh)
        to_coords = get_coords(to_loc)

        if from_coords is None:
            print(f"    ⚠ 起点 {from_wh} 无坐标，跳过")
            continue
        if to_coords is None:
            print(f"    ⚠ 终点 {to_loc} 无坐标，跳过")
            continue

        if var >= 250:
            color = 'red'
            alpha = 0.9
            linewidth = 4
            style = '--'
        elif var >= 150:
            color = 'darkorange'
            alpha = 0.8
            linewidth = 3
            style = '-'
        elif var >= 100:
            color = 'purple'
            alpha = 0.7
            linewidth = 2.5
            style = '-.'
        else:
            color = 'gray'
            alpha = 0.6
            linewidth = 1.5
            style = ':'

        ax.plot([from_coords[0], to_coords[0]],
               [from_coords[1], to_coords[1]],
               color=color, linewidth=linewidth, alpha=alpha,
               linestyle=style, transform=ccrs.PlateCarree(), zorder=2)

        mid_x = (from_coords[0] + to_coords[0]) / 2
        mid_y = (from_coords[1] + to_coords[1]) / 2

        offset_y = 0.5 if rank % 2 == 0 else -0.8

        ax.text(mid_x, mid_y + offset_y, f'#{rank} {var:.0f}t',
               fontsize=8, fontproperties='SimHei', transform=ccrs.PlateCarree(),
               bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow',
                        alpha=0.9, edgecolor=color, linewidth=1),
               ha='center')

        if to_loc not in plotted_cities and to_loc not in warehouse_coords:
            ax.scatter(to_coords[0], to_coords[1], s=50, c='green', alpha=0.6,
                      marker='^', transform=ccrs.PlateCarree(), zorder=4)
            ax.text(to_coords[0] + 0.2, to_coords[1] + 0.2, to_loc, fontsize=7,
                   fontproperties='SimHei', transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.1', facecolor='white', alpha=0.7))
            plotted_cities.add(to_loc)
            city_count += 1

        print(f"    ✓ #{rank} {from_wh} → {to_loc}: {var:.1f}吨 ({color})")

    ax.set_title('问题4：7天运输量变化最大的15条路线\n（路线旁标注为波动幅度，单位：吨）',
                fontsize=16, fontweight='bold', pad=20)

    legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor='red', markersize=14,
               markeredgecolor='darkred', markeredgewidth=2.5, label=f'CDC（中心仓）{cdc_count}个'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='steelblue', markersize=12,
               markeredgecolor='darkblue', markeredgewidth=2.5, label=f'RDC（区域仓）{rdc_count}个'),
        Line2D([0], [0], marker='^', color='w', markerfacecolor='green', markersize=10,
               markeredgecolor='darkgreen', markeredgewidth=2, label=f'目的城市{city_count}个'),
        Line2D([0], [0], color='red', linewidth=4, linestyle='--', alpha=0.9, label='波动≥250吨'),
        Line2D([0], [0], color='darkorange', linewidth=3, linestyle='-', alpha=0.8, label='波动150-250吨'),
        Line2D([0], [0], color='purple', linewidth=2.5, linestyle='-.', alpha=0.7, label='波动100-150吨'),
        Line2D([0], [0], color='gray', linewidth=1.5, linestyle=':', alpha=0.6, label='波动<100吨'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', prop={'family': 'SimHei', 'size': 10},
             framealpha=0.95)

    fig.text(0.5, 0.02,
            '分析结论：主要调拨路线（CDC→RDC）波动最大，反映跨区域调拨的灵活性需求 | 配送路线（仓→店）相对稳定',
            ha='center', fontsize=11, style='italic',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    plt.savefig(os.path.join(output_dir, '路线变化地图_问题4.png'),
               dpi=200, bbox_inches='tight', facecolor='white')
    print(f"\n  ✓ 已保存: 路线变化地图_问题4.png")
    plt.close()

except ImportError:
    print("  ⚠ 跳过：未安装 cartopy 库，使用简化可视化")

    fig, ax = plt.subplots(figsize=(16, 12))

    x_coords = []
    y_coords = []
    labels = []

    for wh, info in warehouse_coords.items():
        coords = info['coords']
        x_coords.append(coords[0])
        y_coords.append(coords[1])
        labels.append(wh)

    ax.scatter(x_coords, y_coords, s=200, c='steelblue', alpha=0.8, zorder=5)
    for i, label in enumerate(labels):
        ax.annotate(label, (x_coords[i], y_coords[i]), fontsize=8, ha='left')

    top15 = top_changed[:15]
    for rank, (key, var) in enumerate(top15, 1):
        records = all_keys[key]
        parts = key.split('|')
        from_wh = parts[0]
        to_loc = parts[1]

        from_c = get_coords(from_wh)
        to_c = get_coords(to_loc)

        if from_c is None or to_c is None:
            continue

        color = 'red' if var >= 200 else 'orange' if var >= 100 else 'gray'
        ax.plot([from_c[0], to_c[0]], [from_c[1], to_c[1]],
               color=color, linewidth=var/50, alpha=0.7)
        ax.text((from_c[0] + to_c[0])/2, (from_c[1] + to_c[1])/2,
               f'#{rank}', fontsize=7)

    ax.set_title('问题4：运输量变化最大的15条路线（简化视图）', fontsize=14, fontweight='bold')
    plt.savefig(os.path.join(output_dir, '路线变化地图_问题4.png'),
               dpi=200, bbox_inches='tight')
    print(f"\n  ✓ 已保存: 路线变化地图_问题4.png")
    plt.close()

print("\n" + "="*80)
print("可视化完成！")
print("="*80)
