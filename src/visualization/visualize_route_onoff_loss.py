# -*- coding: utf-8 -*-
"""
问题4（有损耗）动态路线开关状态可视化
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
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from collections import defaultdict
import numpy as np

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False

print("="*80)
print("问题4（有损耗）动态路线可视化 - 启动")
print("="*80)

from src.runtime import loss_results_dir
output_dir = str(loss_results_dir())
input_dir = str(_REPO_ROOT / 'data/raw')

df_wh = pd.read_csv(os.path.join(input_dir, 'df_wh.csv'))
df_loc = pd.read_csv(os.path.join(input_dir, 'df_loc.csv'))

city_coords = {row['Location']: [row['Longitude'], row['Latitude']]
               for _, row in df_loc.iterrows() if pd.notna(row['Longitude'])}

warehouse_coords = {}
for _, row in df_wh.iterrows():
    if row['Location'] in city_coords:
        warehouse_coords[row['Name']] = {
            'coords': city_coords[row['Location']],
            'type': row['Type']
        }

def get_coords(name):
    if name in warehouse_coords:
        return warehouse_coords[name]['coords']
    if name in city_coords:
        return city_coords[name]
    name_no_shi = name.replace('-shi', '')
    if name_no_shi in city_coords:
        return city_coords[name_no_shi]
    return None

days = ['06-24', '06-25', '06-26', '06-27', '06-28', '06-29', '06-30']
day_routes = {}

for day in days:
    file_path = os.path.join(output_dir, f'仓网供应关系文件_2016-{day}.csv')
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        df['key'] = df['仓库名称'] + '|' + df['服务对象'] + '|' + df['商品类型']
        day_routes[day] = set(df['key'].tolist())
    else:
        raise FileNotFoundError(f"缺少每日路线文件，不能把缺失数据视为无路线: {file_path}")

all_routes = set().union(*day_routes.values())
common_routes = set.intersection(*day_routes.values()) if day_routes else set()
all_routes = set().union(*day_routes.values())
partial_routes = all_routes - common_routes

common_route_list = []
for route in common_routes:
    parts = route.split('|')
    common_route_list.append({
        'from': parts[0], 'to': parts[1], 'sku': parts[2], 'key': route
    })

dynamic_route_info = []
for route in sorted(list(partial_routes)):
    parts = route.split('|')
    days_exist = [day for day in days if route in day_routes[day]]
    dynamic_route_info.append({
        'from': parts[0], 'to': parts[1], 'sku': parts[2], 'days': days_exist, 'key': route
    })

print(f"静态路线: {len(common_route_list)} 条")
print(f"动态路线: {len(dynamic_route_info)} 条")

fig = plt.figure(figsize=(28, 16), dpi=120)
gs = gridspec.GridSpec(1, 2, width_ratios=[1, 1.3], wspace=0.15)

ax_heatmap = fig.add_subplot(gs[0])

heatmap_data = []
row_labels = []
for info in dynamic_route_info:
    route_name = f"{info['from']} → {info['to']}"
    row_labels.append(route_name)
    heatmap_data.append([1 if d in info['days'] else 0 for d in days])

heatmap_data = np.array(heatmap_data)
cmap = matplotlib.colors.ListedColormap(['#f0f0f0', '#e74c3c'])

if len(heatmap_data):
    ax_heatmap.imshow(heatmap_data, cmap=cmap, aspect='auto', vmin=0, vmax=1)
else:
    ax_heatmap.text(0.5, 0.5, '无动态路线', ha='center', transform=ax_heatmap.transAxes)

ax_heatmap.set_xticks(np.arange(len(days)))
ax_heatmap.set_xticklabels(['24日\n周五', '25日\n周六', '26日\n周日', '27日\n周一', '28日\n周二', '29日\n周三', '30日\n周四'], fontsize=13)
ax_heatmap.set_yticks(np.arange(len(row_labels)))
ax_heatmap.set_yticklabels(row_labels, fontsize=11)
ax_heatmap.set_title('动态路线每日开通状态（损耗模型）', fontsize=18, fontweight='bold', pad=20)
ax_heatmap.set_xlabel('日期', fontsize=14, fontweight='bold')
ax_heatmap.set_ylabel('路线', fontsize=14, fontweight='bold')

ax_heatmap.set_xticks(np.arange(-.5, len(days), 1), minor=True)
ax_heatmap.set_yticks(np.arange(-.5, len(row_labels), 1), minor=True)
ax_heatmap.grid(which="minor", color="white", linestyle='-', linewidth=2)
ax_heatmap.tick_params(which="minor", bottom=False, left=False)

for i in range(len(row_labels)):
    for j in range(len(days)):
        if heatmap_data[i, j] == 1:
            ax_heatmap.text(j, i, '●', ha='center', va='center', fontsize=14, color='white', fontweight='bold')
        else:
            ax_heatmap.text(j, i, '○', ha='center', va='center', fontsize=14, color='#cccccc', fontweight='bold')

legend_elements = [
    Patch(facecolor='#e74c3c', label='开通'),
    Patch(facecolor='#f0f0f0', edgecolor='#cccccc', label='关闭')
]
ax_heatmap.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.02),
                 ncol=2, fontsize=14, frameon=False)

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    ax_map = fig.add_subplot(gs[1], projection=ccrs.PlateCarree())

    ax_map.add_feature(cfeature.LAND, facecolor='#f5f5f5')
    ax_map.add_feature(cfeature.COASTLINE, linewidth=0.6, color='#666666')
    ax_map.add_feature(cfeature.BORDERS, linestyle=':', linewidth=0.6)

    all_lons = [c[0] for c in city_coords.values()]
    all_lats = [c[1] for c in city_coords.values()]
    ax_map.set_extent([min(all_lons)-2, max(all_lons)+2, min(all_lats)-2, max(all_lats)+2], crs=ccrs.PlateCarree())

    for name, info in warehouse_coords.items():
        color = '#d9534f' if info['type'] == 'CDC' else '#5bc0de'
        marker = 's' if info['type'] == 'CDC' else 'o'
        size = 180 if info['type'] == 'CDC' else 120
        ax_map.scatter(info['coords'][0], info['coords'][1], s=size, c=color,
                       marker=marker, edgecolors='white', linewidths=2, zorder=5, transform=ccrs.PlateCarree())
        ax_map.text(info['coords'][0]+0.3, info['coords'][1]+0.3, name, fontsize=18,
                    fontweight='bold', transform=ccrs.PlateCarree(),
                    bbox=dict(facecolor='white', alpha=0.85, edgecolor='gray', pad=3))

    warehouse_locations = set(warehouse_coords.keys())
    customer_cities = {loc: coords for loc, coords in city_coords.items() if loc not in warehouse_locations}
    for loc, coords in customer_cities.items():
        ax_map.scatter(coords[0], coords[1], s=50, c='gray', alpha=0.4,
                      marker='o', zorder=1, transform=ccrs.PlateCarree())
        ax_map.text(coords[0], coords[1]-0.4, loc, fontsize=7, alpha=0.5,
                   transform=ccrs.PlateCarree(), ha='center')

    for route_info in common_route_list:
        p1 = get_coords(route_info['from'])
        p2 = get_coords(route_info['to'])
        if not p1 or not p2:
            continue
        ax_map.plot([p1[0], p2[0]], [p1[1], p2[1]],
                   color='gray', linewidth=0.8, alpha=0.12,
                   transform=ccrs.PlateCarree(), zorder=1)

    unique_pairs = defaultdict(list)
    for info in dynamic_route_info:
        unique_pairs[(info['from'], info['to'])].append(info)

    line_colors = plt.cm.get_cmap('tab20')(np.linspace(0, 1, len(unique_pairs)))

    for idx, ((start_node, end_node), infos) in enumerate(unique_pairs.items()):
        p1 = get_coords(start_node)
        p2 = get_coords(end_node)
        if not p1 or not p2:
            continue

        color = line_colors[idx % len(line_colors)]

        ax_map.plot([p1[0], p2[0]], [p1[1], p2[1]],
                   color=color, linewidth=2.5, alpha=0.6,
                   transform=ccrs.PlateCarree(), zorder=2)

    ax_map.set_title(f'动态路线空间分布（损耗模型，{len(dynamic_route_info)}条）', fontsize=18, fontweight='bold', pad=20)

    map_legends = [
        Line2D([0], [0], marker='s', color='w', label='CDC 仓库', markerfacecolor='#d9534f', markersize=12),
        Line2D([0], [0], marker='o', color='w', label='RDC 仓库', markerfacecolor='#5bc0de', markersize=10),
        Line2D([0], [0], color='#e74c3c', lw=3, label=f'动态路线 ({len(dynamic_route_info)}条)'),
        Line2D([0], [0], color='gray', lw=1, alpha=0.15, label=f'静态路线 ({len(common_route_list)}条)'),
        Line2D([0], [0], marker='o', color='w', label='客户点', markerfacecolor='gray', markersize=6, alpha=0.5),
    ]
    ax_map.legend(handles=map_legends, loc='lower right', fontsize=11, frameon=True, facecolor='white', framealpha=0.9)

except ImportError:
    ax_map = fig.add_subplot(gs[1])
    ax_map.text(0.5, 0.5, "未检测到 Cartopy 库", ha='center', fontsize=14)

plt.suptitle('问题4（损耗模型）：配送网络动态路线', fontsize=22, fontweight='bold', y=0.98)
output_path = os.path.join(output_dir, '动态路线优化可视化_问题4_有损耗.png')
plt.savefig(output_path, dpi=200, bbox_inches='tight', facecolor='white')
print(f"可视化保存成功: {output_path}")
plt.close()
