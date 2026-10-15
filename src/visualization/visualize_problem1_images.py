# -*- coding: utf-8 -*-
"""
问题1结果可视化脚本（生成PNG图片）

使用 matplotlib 绘制静态图片，方便插入PPT或报告
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
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']  # 支持中文
matplotlib.rcParams['axes.unicode_minus'] = False

print("="*80)
print("问题1结果可视化（生成PNG图片）")
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

# 读取周期数
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

# ==================== 可视化1：仓库分布 ====================
print("\n【可视化1】仓库分布图...")

fig, ax = plt.subplots(figsize=(12, 10))

# 绘制散点图
for wh, coords in warehouse_coords.items():
    qty = wh_qty.get(wh, 0)
    size = 80 + 400 * qty / max(max(wh_qty.values(), default=0), 1)  # 根据数量调整大小
    color = 'red' if qty > 0 else 'blue'
    alpha = 0.7 if qty > 0 else 0.5
    
    ax.scatter(coords[0], coords[1], s=size, c=color, alpha=alpha, 
               edgecolors='black', linewidths=1)
    ax.text(coords[0] + 0.2, coords[1], wh, fontsize=8, fontproperties='SimHei')

ax.set_xlim(100, 135)
ax.set_ylim(15, 55)
ax.set_xlabel('经度', fontsize=12, fontproperties='SimHei')
ax.set_ylabel('纬度', fontsize=12, fontproperties='SimHei')
ax.set_title('问题1：仓库分布图', fontsize=14, fontproperties='SimHei', fontweight='bold')
ax.grid(True, alpha=0.3)

# 添加图例
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=10, 
           label='有订单量'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', markersize=10, 
           label='无订单量'),
]
ax.legend(handles=legend_elements, prop={'family': 'SimHei'})

plt.tight_layout()
plt.savefig(str(_PLOT_DIR / '问题1_仓库分布.png'), dpi=300, bbox_inches='tight')
print("  ✓ 已保存: 问题1_仓库分布.png")
plt.close()

# ==================== 可视化2：业务指标趋势 ====================
print("\n【可视化2】业务指标趋势图...")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

# 子图1：成本趋势
periods = list(range(1, len(df_business) + 1))
costs = df_business['总物流成本（单位：万元）'].tolist()
open_counts = df_business['开仓数量'].tolist()
time_rates = (df_business['时效满足率'] * 100).tolist()

ax1.plot(periods, costs, marker='o', linewidth=2, markersize=8, 
         label='总物流成本', color='blue')
ax1.set_xlabel('周期', fontsize=12, fontproperties='SimHei')
ax1.set_ylabel('成本（万元）', fontsize=12, fontproperties='SimHei')
ax1.set_title('总物流成本趋势', fontsize=14, fontproperties='SimHei', fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.legend(prop={'family': 'SimHei'})

# 子图2：开仓数量和时效满足率
ax2_twin = ax2.twinx()
line1, = ax2.plot(periods, open_counts, marker='s', linewidth=2, markersize=6,
                  label='开仓数量', color='green')
line2, = ax2_twin.plot(periods, time_rates, marker='^', linewidth=2, markersize=6,
                       label='时效满足率', color='red')

ax2.set_xlabel('周期', fontsize=12, fontproperties='SimHei')
ax2.set_ylabel('开仓数量', fontsize=12, fontproperties='SimHei')
ax2_twin.set_ylabel('时效满足率（%）', fontsize=12, fontproperties='SimHei')
ax2.set_title('开仓数量与时效满足率', fontsize=14, fontproperties='SimHei', fontweight='bold')
ax2.grid(True, alpha=0.3)

# 合并图例
lines = [line1, line2]
labels = [l.get_label() for l in lines]
ax2.legend(lines, labels, prop={'family': 'SimHei'})

plt.tight_layout()
plt.savefig(str(_PLOT_DIR / '问题1_业务指标.png'), dpi=300, bbox_inches='tight')
print("  ✓ 已保存: 问题1_业务指标.png")
plt.close()

# ==================== 可视化3：成本构成 ====================
print("\n【可视化3】成本构成饼图...")

total_cost = sum(costs)
transport_cost = sum(df_business['仓库之间的运输总成本（单位：万元）'].tolist())
to_customer_cost = sum(df_business['仓库到门店的运输总成本（单位：万元）'].tolist())
open_cost = sum(df_business['开仓总成本（单位：万元）'].tolist())
process_cost = sum(df_business['出入仓处置总成本（单位：万元）'].tolist())
smart_cost = sum(df_business['智能调度系统采购总成本（单位：万元）'].tolist())

fig, ax = plt.subplots(figsize=(10, 8))

labels = ['仓库间运输', '到门店运输', '开仓成本', '处置成本', '智能系统']
sizes = [transport_cost, to_customer_cost, open_cost, process_cost, smart_cost]
colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#ff99cc']
explode = (0.05, 0.05, 0, 0, 0)

ax.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%',
       startangle=90, textprops={'fontproperties': 'SimHei'})
ax.axis('equal')
ax.set_title(f'问题1：成本构成（总成本: {total_cost:.2f}万元）', 
             fontsize=14, fontproperties='SimHei', fontweight='bold')

plt.tight_layout()
plt.savefig(str(_PLOT_DIR / '问题1_成本构成.png'), dpi=300, bbox_inches='tight')
print("  ✓ 已保存: 问题1_成本构成.png")
plt.close()

# ==================== 可视化4：仓库订单量 ====================
print("\n【可视化4】仓库订单量柱状图...")

fig, ax = plt.subplots(figsize=(14, 6))

# 按订单量排序
sorted_wh = sorted(wh_qty.items(), key=lambda x: x[1], reverse=True)
wh_names = [item[0] for item in sorted_wh]
wh_values = [item[1] for item in sorted_wh]

colors = ['#ff6b6b' if 'CDC' in name else '#4ecdc4' for name in wh_names]
bars = ax.bar(range(len(wh_names)), wh_values, color=colors, alpha=0.7, 
              edgecolor='black', linewidth=1)

ax.set_xlabel('仓库', fontsize=12, fontproperties='SimHei')
ax.set_ylabel('订单量（吨）', fontsize=12, fontproperties='SimHei')
ax.set_title('问题1：各仓库订单量', fontsize=14, fontproperties='SimHei', fontweight='bold')
ax.set_xticks(range(len(wh_names)))
ax.set_xticklabels(wh_names, rotation=45, ha='right', fontsize=9)
ax.grid(True, alpha=0.3, axis='y')

# 添加数值标签
for bar, value in zip(bars, wh_values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 50, 
            f'{value:.1f}', ha='center', va='bottom', fontsize=8)

plt.tight_layout()
plt.savefig(str(_PLOT_DIR / '问题1_仓库订单量.png'), dpi=300, bbox_inches='tight')
print("  ✓ 已保存: 问题1_仓库订单量.png")
plt.close()

# ==================== 可视化5：运输网络 ====================
print("\n【可视化5】运输网络图...")

fig, ax = plt.subplots(figsize=(12, 10))

# 绘制仓库
for wh, coords in warehouse_coords.items():
    ax.scatter(coords[0], coords[1], s=150, c='steelblue', alpha=0.8, 
               edgecolors='darkblue', linewidths=2)
    ax.text(coords[0] + 0.15, coords[1] + 0.15, wh, fontsize=9, 
            fontproperties='SimHei', bbox=dict(boxstyle='round,pad=0.3', 
            facecolor='lightblue', alpha=0.7))

# 绘制运输连接
for link in supply_links[:50]:  # 只显示前50条
    from_wh = link['from']
    to_wh = link['to']
    qty = link['qty']
    
    if from_wh in warehouse_coords and to_wh in warehouse_coords:
        from_coords = warehouse_coords[from_wh]
        to_coords = warehouse_coords[to_wh]
        
        linewidth = min(2, max(0.5, qty / 200))
        ax.plot([from_coords[0], to_coords[0]], 
                [from_coords[1], to_coords[1]], 
                color='orange', linewidth=linewidth, alpha=0.6,
                linestyle='-')

ax.set_xlim(100, 135)
ax.set_ylim(15, 55)
ax.set_xlabel('经度', fontsize=12, fontproperties='SimHei')
ax.set_ylabel('纬度', fontsize=12, fontproperties='SimHei')
ax.set_title('问题1：运输网络图', fontsize=14, fontproperties='SimHei', fontweight='bold')
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(str(_PLOT_DIR / '问题1_运输网络.png'), dpi=300, bbox_inches='tight')
print("  ✓ 已保存: 问题1_运输网络.png")
plt.close()

# ==================== 生成综合报告 ====================
print("\n【生成综合报告】...")

fig = plt.figure(figsize=(16, 12))
fig.suptitle('问题1：仓网配送优化结果综合报告', fontsize=16, fontweight='bold', fontproperties='SimHei')

# 子图1：仓库分布
ax1 = fig.add_subplot(2, 3, 1)
for wh, coords in warehouse_coords.items():
    qty = wh_qty.get(wh, 0)
    size = 80 + 400 * qty / max(max(wh_qty.values(), default=0), 1)
    color = 'red' if qty > 0 else 'blue'
    ax1.scatter(coords[0], coords[1], s=size, c=color, alpha=0.7)
    ax1.text(coords[0] + 0.2, coords[1], wh, fontsize=7)
ax1.set_xlim(100, 135)
ax1.set_ylim(15, 55)
ax1.set_title('仓库分布', fontproperties='SimHei')
ax1.grid(True, alpha=0.3)

# 子图2：成本趋势
ax2 = fig.add_subplot(2, 3, 2)
ax2.plot(periods, costs, marker='o', linewidth=2, markersize=6, color='blue')
ax2.set_xlabel('周期', fontproperties='SimHei')
ax2.set_ylabel('成本（万元）', fontproperties='SimHei')
ax2.set_title('成本趋势', fontproperties='SimHei')
ax2.grid(True, alpha=0.3)

# 子图3：成本构成
ax3 = fig.add_subplot(2, 3, 3)
ax3.pie(sizes, labels=labels, autopct='%1.0f%%', startangle=90, 
        textprops={'fontproperties': 'SimHei'})
ax3.set_title('成本构成', fontproperties='SimHei')

# 子图4：开仓数量
ax4 = fig.add_subplot(2, 3, 4)
ax4.plot(periods, open_counts, marker='s', linewidth=2, markersize=6, color='green')
ax4.set_xlabel('周期', fontproperties='SimHei')
ax4.set_ylabel('数量', fontproperties='SimHei')
ax4.set_title('开仓数量', fontproperties='SimHei')
ax4.grid(True, alpha=0.3)

# 子图5：时效满足率
ax5 = fig.add_subplot(2, 3, 5)
ax5.plot(periods, time_rates, marker='^', linewidth=2, markersize=6, color='red')
ax5.set_xlabel('周期', fontproperties='SimHei')
ax5.set_ylabel('满足率（%）', fontproperties='SimHei')
ax5.set_title('时效满足率', fontproperties='SimHei')
ax5.grid(True, alpha=0.3)

# 子图6：统计信息
ax6 = fig.add_subplot(2, 3, 6)
ax6.axis('off')
stats_text = f"""
【核心指标】
总物流成本：{total_cost:.2f} 万元
平均成本：{total_cost/T:.2f} 万元/周期
开仓数量：{len(wh_qty)} 个
时效满足率：{sum(time_rates)/len(time_rates):.2f}%
"""
ax6.text(0.1, 0.5, stats_text, fontsize=12, verticalalignment='center',
         fontproperties='SimHei')

plt.tight_layout()
plt.savefig(str(_PLOT_DIR / '问题1_综合报告.png'), dpi=300, bbox_inches='tight')
print("  ✓ 已保存: 问题1_综合报告.png")
plt.close()

print("\n" + "="*80)
print("可视化完成！")
print("生成的PNG图片：")
print("  - 问题1_仓库分布.png")
print("  - 问题1_业务指标.png")
print("  - 问题1_成本构成.png")
print("  - 问题1_仓库订单量.png")
print("  - 问题1_运输网络.png")
print("  - 问题1_综合报告.png")
print("="*80)
