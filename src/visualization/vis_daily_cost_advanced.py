from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _runtime_sys
_runtime_sys.path.insert(0, str(_REPO_ROOT))
from src.runtime import results_root as _results_root, read_forecast as _read_forecast, configure_solver as _configure_solver, record_solver as _record_solver
_RESULTS_ROOT = _results_root()
import pandas as pd
import os
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

output_dir = str(_RESULTS_ROOT / 'question4/problem4_noloss/output_result')
input_dir = str(_RESULTS_ROOT / 'question3')

df_demand = _read_forecast()

days = []
trans_wh = []
trans_cust = []
proc = []
daily_total = []
total_demand = []

date_cols = ['2016/06/24', '2016/06/25', '2016/06/26', '2016/06/27', '2016/06/28', '2016/06/29', '2016/06/30']
total_demand = df_demand[date_cols].sum().tolist()

for i, day in enumerate(['06-24', '06-25', '06-26', '06-27', '06-28', '06-29', '06-30']):
    df = pd.read_csv(os.path.join(output_dir, f'仓网业务表现文件_2016-{day}.csv'))
    day_num = day.split('-')[1]
    days.append(f'6/{int(day_num)}')
    trans_wh.append(df['仓库之间的运输总成本（万元）'].values[0])
    trans_cust.append(df['仓库到门店的运输总成本（万元）'].values[0])
    proc.append(df['处置总成本（万元）'].values[0])
    daily_total.append(df['当天总成本（万元）'].values[0])

fig = plt.figure(figsize=(14, 12))
gs = GridSpec(3, 2, figure=fig, height_ratios=[1.2, 1, 1])

ax1 = fig.add_subplot(gs[0, :])
x = np.arange(len(days))
width = 0.25

bars1 = ax1.bar(x - width, trans_wh, width, label='仓库间运输', color='#3498DB', alpha=0.9)
bars2 = ax1.bar(x, trans_cust, width, label='仓库到门店', color='#E74C3C', alpha=0.9)
bars3 = ax1.bar(x + width, proc, width, label='处置成本', color='#2ECC71', alpha=0.9)

ax1.set_ylabel('成本（万元）', fontsize=12, fontweight='bold')
ax1.set_xlabel('日期', fontsize=12, fontweight='bold')
ax1.set_title('多周期仓网优化 - 每日运营成本构成分析（不含损耗）', fontsize=14, fontweight='bold', pad=15)
ax1.set_xticks(x)
ax1.set_xticklabels(days, fontsize=11)
ax1.legend(loc='upper right', fontsize=10)
ax1.grid(axis='y', alpha=0.3, linestyle='--')
ax1.set_ylim(0, max(daily_total) * 1.2)

for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        ax1.annotate(f'{height:.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=7, rotation=45)

ax2 = fig.add_subplot(gs[1, :])
ax2_twin = ax2.twinx()

ax2.bar(days, daily_total, color='#9B59B6', alpha=0.7, label='当天总成本')
ax2.set_ylabel('成本（万元）', fontsize=11, fontweight='bold', color='#9B59B6')
ax2.tick_params(axis='y', labelcolor='#9B59B6')
ax2.set_ylim(0, max(daily_total) * 1.3)

demand_tons = [d / 1000 for d in total_demand]
ax2_twin.plot(days, demand_tons, 'o-', color='#E67E22', linewidth=2.5, markersize=10, label='总需求(吨/1000)')
ax2_twin.set_ylabel('总需求（吨/1000）', fontsize=11, fontweight='bold', color='#E67E22')
ax2_twin.tick_params(axis='y', labelcolor='#E67E22')
ax2_twin.set_ylim(0, max(demand_tons) * 1.3)

ax2.set_xlabel('日期', fontsize=11, fontweight='bold')
ax2.set_title('每日总成本与需求趋势对比', fontsize=12, fontweight='bold')
ax2.grid(True, alpha=0.3, linestyle='--')

lines1, labels1 = ax2.get_legend_handles_labels()
lines2, labels2 = ax2_twin.get_legend_handles_labels()
ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper right')

cost_components = [sum(trans_wh), sum(trans_cust), sum(proc)]
labels = ['仓库间运输', '仓库到门店', '处置成本']
colors = ['#3498DB', '#E74C3C', '#2ECC71']
explode = (0.02, 0.02, 0.02)

ax3 = fig.add_subplot(gs[2, 0])
wedges, texts, autotexts = ax3.pie(cost_components, explode=explode, labels=labels, colors=colors,
                                    autopct='%1.1f%%', startangle=90, pctdistance=0.75,
                                    textprops={'fontsize': 10})
ax3.set_title('7天成本构成比例', fontsize=12, fontweight='bold')

for i, autotext in enumerate(autotexts):
    autotext.set_fontsize(9)
    autotext.set_fontweight('bold')
    amount = cost_components[i]
    ax3.annotate(f'{amount/100:.1f}万',
                xy=(autotext.get_position()[0] * 1.2, autotext.get_position()[1] * 1.2),
                ha='center', va='center', fontsize=8)

ax4 = fig.add_subplot(gs[2, 1])
demand_normalized = [d / max(total_demand) * max(daily_total) for d in total_demand]
ax4.plot(days, daily_total, 'o-', color='#9B59B6', linewidth=2, markersize=8, label='当天总成本')
ax4.plot(days, demand_normalized, 's--', color='#E67E22', linewidth=2, markersize=8, label='需求(标准化)')
ax4.set_xlabel('日期', fontsize=11, fontweight='bold')
ax4.set_ylabel('成本/需求', fontsize=11, fontweight='bold')
ax4.set_title('成本-需求相关性', fontsize=12, fontweight='bold')
ax4.legend(loc='upper right')
ax4.grid(True, alpha=0.3, linestyle='--')

corr = np.corrcoef(total_demand, daily_total)[0, 1]
ax4.text(0.05, 0.95, f'相关系数: {corr:.3f}', transform=ax4.transAxes,
         fontsize=10, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

fig.text(0.5, 0.01, f'7天运营成本合计: {sum(daily_total):.2f}万元 | 开仓成本: 425万元 | 智能系统: 28.5万元 | 总计: {sum(daily_total)+453.5:.2f}万元 | 需求-成本相关系数: {corr:.3f}',
         ha='center', fontsize=10, style='italic')

plt.tight_layout(rect=[0, 0.03, 1, 1])
plt.savefig(os.path.join(output_dir, '每日成本变化_高级.png'), dpi=200, bbox_inches='tight', facecolor='white')
print('高级可视化已保存')
print(f'需求-成本相关系数: {corr:.3f}')
