# -*- coding: utf-8 -*-
"""
问题4动态路线可视化
展示路线的新增/消失模式
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())

import pandas as pd
import os
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from collections import defaultdict
import numpy as np

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

print("="*80)
print("问题4动态路线可视化")
print("="*80)

output_dir = str(_REPO_ROOT / 'results/question4/problem4_noloss/output_result')
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
for _, row in df_wh.iterrows():
    wh_name = row['Name']
    wh_location = row['Location']
    if wh_location in city_coords:
        warehouse_coords[wh_name] = {
            'coords': city_coords[wh_location],
            'type': row['Type']
        }

print(f"  ✓ 加载了 {len(city_coords)} 个城市坐标")
print(f"  ✓ 加载了 {len(warehouse_coords)} 个仓库坐标")

def get_coords(name):
    if name in warehouse_coords:
        return warehouse_coords[name]['coords']
    if name in city_coords:
        return city_coords[name]
    return None

days = ['06-24', '06-25', '06-26', '06-27', '06-28', '06-29', '06-30']
day_routes = {}
all_keys = defaultdict(lambda: defaultdict(list))

for day in days:
    df = pd.read_csv(os.path.join(output_dir, f'仓网供应关系文件_2016-{day}.csv'))
    df['key'] = df['仓库名称'] + '|' + df['服务对象'] + '|' + df['商品类型']
    day_routes[day] = set(df['key'].tolist())
    for idx, row in df.iterrows():
        key = row['key']
        all_keys[key][day] = row['数量（吨）']

common_routes = day_routes['06-24']
for day in days[1:]:
    common_routes = common_routes & day_routes[day]

all_routes = set()
for routes in day_routes.values():
    all_routes = all_routes | routes

partial_routes = all_routes - common_routes

print(f"  ✓ 稳定路线: {len(common_routes)} 条")
print(f"  ✓ 动态路线: {len(partial_routes)} 条")

print("\n【动态路线详情】")
dynamic_route_info = {}
for route in partial_routes:
    days_exist = [day for day in days if route in day_routes[day]]
    days_absent = [day for day in days if route not in day_routes[day]]
    parts = route.split('|')
    from_wh = parts[0]
    to_loc = parts[1]
    sku = parts[2]
    dynamic_route_info[route] = {
        'from': from_wh,
        'to': to_loc,
        'sku': sku,
        'days_exist': days_exist,
        'days_absent': days_absent
    }
    print(f"  {from_wh} → {to_loc} ({sku})")
    print(f"    存在: {days_exist}, 消失: {days_absent}")

print("\n【可视化】")

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    fig = plt.figure(figsize=(20, 16))
    ax = plt.axes(projection=ccrs.PlateCarree())

    ax.add_feature(cfeature.COASTLINE, linewidth=0.6)
    ax.add_feature(cfeature.BORDERS, linestyle='-', linewidth=0.9)
    ax.add_feature(cfeature.LAKES, alpha=0.3)
    ax.add_feature(cfeature.RIVERS, linewidth=0.4)

    ax.set_extent([110, 130, 28, 46], crs=ccrs.PlateCarree())

    cdc_count = 0
    rdc_count = 0
    city_count = 0

    for wh, info in warehouse_coords.items():
        if info['type'] == 'CDC':
            coords = info['coords']
            if coords[0] >= 110 and coords[0] <= 130 and coords[1] >= 28 and coords[1] <= 46:
                ax.scatter(coords[0], coords[1], s=400, c='red', alpha=0.9,
                          marker='s', edgecolors='darkred', linewidths=3,
                          transform=ccrs.PlateCarree(), zorder=5)
                ax.text(coords[0] + 0.3, coords[1] + 0.3, wh, fontsize=11,
                       fontproperties='SimHei', transform=ccrs.PlateCarree(),
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                                alpha=0.9, edgecolor='darkred', linewidth=2))
                cdc_count += 1

    for wh, info in warehouse_coords.items():
        if info['type'] == 'RDC':
            coords = info['coords']
            if coords[0] >= 110 and coords[0] <= 130 and coords[1] >= 28 and coords[1] <= 46:
                ax.scatter(coords[0], coords[1], s=250, c='steelblue', alpha=0.9,
                          marker='o', edgecolors='darkblue', linewidths=2.5,
                          transform=ccrs.PlateCarree(), zorder=5)
                ax.text(coords[0] + 0.3, coords[1] + 0.3, wh, fontsize=10,
                       fontproperties='SimHei', transform=ccrs.PlateCarree(),
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                                alpha=0.9, edgecolor='darkblue', linewidth=1.5))
                rdc_count += 1

    day_colors = {
        '06-24': '#1a53ff',
        '06-25': '#00cc00',
        '06-26': '#ffcc00',
        '06-27': '#ff6600',
        '06-28': '#cc0099',
        '06-29': '#00cccc',
        '06-30': '#990000'
    }

    route_pairs = defaultdict(list)
    for route, info in dynamic_route_info.items():
        pair_key = (info['from'], info['to'])
        route_pairs[pair_key].append(route)

    plotted_cities = set()
    pair_idx = {}

    for route, info in dynamic_route_info.items():
        from_coords = get_coords(info['from'])
        to_coords = get_coords(info['to'])

        if from_coords is None or to_coords is None:
            continue

        from_wh = info['from']
        to_loc = info['to']
        pair_key = (from_wh, to_loc)

        if pair_key not in pair_idx:
            pair_idx[pair_key] = 0
        else:
            pair_idx[pair_key] += 1
        offset_idx = pair_idx[pair_key]

        base_mid_x = (from_coords[0] + to_coords[0]) / 2
        base_mid_y = (from_coords[1] + to_coords[1]) / 2

        dx = to_coords[0] - from_coords[0]
        dy = to_coords[1] - from_coords[1]
        perp_x = -dy * 0.02 * (1 if offset_idx % 2 == 0 else -1)
        perp_y = dx * 0.02 * (1 if offset_idx % 2 == 0 else -1)

        days_exist = info['days_exist']
        days_absent = info['days_absent']

        legend_label = f"{from_wh} → {to_loc}\n存在: {','.join(days_exist)}"
        legend_label_absent = f"消失: {','.join(days_absent)}"

        exist_color = day_colors[days_exist[0]]
        for i, day in enumerate(days_exist):
            color = day_colors[day]
            offset = i * 0.15
            ax.plot([from_coords[0] + perp_x * (i+1), to_coords[0] + perp_x * (i+1)],
                   [from_coords[1] + perp_y * (i+1), to_coords[1] + perp_y * (i+1)],
                   color=color, linewidth=3.5, alpha=0.85,
                   linestyle='-', transform=ccrs.PlateCarree(), zorder=3)

        ax.scatter([from_coords[0] + perp_x], [from_coords[1] + perp_y],
                  s=100, c='white', alpha=0.9, edgecolors='black', linewidths=2,
                  marker='o', transform=ccrs.PlateCarree(), zorder=6)
        ax.text(from_coords[0] + perp_x - 0.3, from_coords[1] + perp_y - 0.3,
               f"#{len(days_exist)}天", fontsize=9, fontweight='bold',
               fontproperties='SimHei', transform=ccrs.PlateCarree(),
               bbox=dict(boxstyle='round,pad=0.2', facecolor='lime', alpha=0.9))

        mid_x = base_mid_x + perp_x * 3
        mid_y = base_mid_y + perp_y * 3

        ax.text(mid_x, mid_y + 0.3, f"{from_wh} → {to_loc}",
               fontsize=9, fontweight='bold', fontproperties='SimHei',
               transform=ccrs.PlateCarree(),
               bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow',
                        alpha=0.95, edgecolor='black', linewidth=1.5),
               ha='center')

        day_labels = ' '.join([f"●{d}" for d in days_exist])
        ax.text(mid_x, mid_y - 0.4, day_labels,
               fontsize=8, fontproperties='SimHei',
               transform=ccrs.PlateCarree(), ha='center',
               bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))

        if to_loc not in plotted_cities and to_loc not in warehouse_coords:
            tc = get_coords(to_loc)
            if tc:
                ax.scatter(tc[0], tc[1], s=80, c='green', alpha=0.7,
                          marker='^', transform=ccrs.PlateCarree(), zorder=4)
                ax.text(tc[0] + 0.2, tc[1] + 0.2, to_loc, fontsize=9,
                       fontproperties='SimHei', transform=ccrs.PlateCarree(),
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))
                plotted_cities.add(to_loc)
                city_count += 1

        print(f"  ✓ {from_wh} → {to_loc}: 存在{days_exist}")

    ax.set_title('问题4：7天中新增/消失的动态路线\n（标注"存在天数"和具体日期，同一对城市可能由不同仓库轮流服务）',
                fontsize=16, fontweight='bold', pad=20)

    legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor='red', markersize=16,
               markeredgecolor='darkred', markeredgewidth=2.5, label=f'CDC（中心仓）{cdc_count}个'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='steelblue', markersize=14,
               markeredgecolor='darkblue', markeredgewidth=2.5, label=f'RDC（区域仓）{rdc_count}个'),
        Line2D([0], [0], color='white', linewidth=0, label=''),
        Patch(facecolor='lime', edgecolor='black', label='●存在天数标注'),
    ]

    day_legend = [Line2D([0], [0], color=day_colors[day], linewidth=3, label=f'{day}({len([r for r in dynamic_route_info.values() if day in r["days_exist"]])}条)')
                  for day in days]
    legend_elements.extend(day_legend)

    ax.legend(handles=legend_elements, loc='upper left', prop={'family': 'SimHei', 'size': 10},
             framealpha=0.95, ncol=2)

    fig.text(0.5, 0.02,
            '发现：同一配送需求可能由不同仓库轮流服务，反映供应链的灵活性与冗余机制',
            ha='center', fontsize=12, style='italic',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9, edgecolor='orange', linewidth=2))

    plt.tight_layout(rect=[0, 0.05, 1, 1])
    plt.savefig(os.path.join(output_dir, '动态路线可视化_问题4.png'),
               dpi=200, bbox_inches='tight', facecolor='white')
    print(f"\n  ✓ 已保存: 动态路线可视化_问题4.png")
    plt.close()

except ImportError:
    print("  ⚠ 未安装 cartopy 库")
    plt.close()

print("\n" + "="*80)
print("可视化完成！")
print("="*80)
