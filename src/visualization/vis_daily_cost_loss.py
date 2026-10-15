# -*- coding: utf-8 -*-
"""
问题4（有损耗）每日成本与需求趋势
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())

import pandas as pd
import os
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

output_dir = str(_REPO_ROOT / 'results/question4/problem4_loss/output_result')

days = ['06-24', '06-25', '06-26', '06-27', '06-28', '06-29', '06-30']
day_labels = ['24日\n周五', '25日\n周六', '26日\n周日', '27日\n周一', '28日\n周二', '29日\n周三', '30日\n周四']

daily_total = []
demand = []

for day in days:
    df = pd.read_csv(os.path.join(output_dir, f'仓网业务表现文件_2016-{day}.csv'))
    daily_total.append(df.iloc[0]['当天总成本（万元）'])

    df_supply = pd.read_csv(os.path.join(output_dir, f'仓网供应关系文件_2016-{day}.csv'))
    demand.append(df_supply['数量（吨）'].sum())

x = np.arange(len(days))

fig, ax = plt.subplots(figsize=(12, 6))

ax_twin = ax.twinx()

bars = ax.bar(x, daily_total, width=0.5, color='#9b59b6', alpha=0.7, label='当天总成本(万元)')
line = ax_twin.plot(x, demand, 'o-', color='#27ae60', linewidth=2.5, markersize=10, label='总需求(吨)')

ax.set_ylabel('总成本（万元）', fontsize=13, color='#9b59b6')
ax_twin.set_ylabel('总需求（吨）', fontsize=13, color='#27ae60')
ax.set_title('问题4（有损耗）：每日总成本与需求趋势', fontsize=16, fontweight='bold', pad=15)
ax.set_xticks(x)
ax.set_xticklabels(day_labels, fontsize=12)
ax.tick_params(axis='y', labelcolor='#9b59b6')
ax_twin.tick_params(axis='y', labelcolor='#27ae60')

for i, v in enumerate(daily_total):
    ax.text(i, v + 500, f'{v:.0f}', ha='center', va='bottom', fontsize=10, color='#9b59b6', fontweight='bold')

lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax_twin.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=12)

ax.grid(axis='y', alpha=0.3)
ax.set_ylim(0, max(daily_total) * 1.15)
ax_twin.set_ylim(0, max(demand) * 1.15)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, '每日成本变化_有损耗.png'), dpi=200, bbox_inches='tight', facecolor='white')
print(f"已保存: {os.path.join(output_dir, '每日成本变化_有损耗.png')}")
plt.close()
