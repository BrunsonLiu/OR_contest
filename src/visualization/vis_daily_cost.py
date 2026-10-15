from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _runtime_sys
_runtime_sys.path.insert(0, str(_REPO_ROOT))
from src.runtime import results_root as _results_root, read_forecast as _read_forecast, configure_solver as _configure_solver, record_solver as _record_solver
_RESULTS_ROOT = _results_root()
import pandas as pd
import os
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

output_dir = str(_RESULTS_ROOT / 'question4/problem4_noloss/output_result')

days = []
trans_wh = []
trans_cust = []
proc = []
daily_total = []

for day in ['06-24', '06-25', '06-26', '06-27', '06-28', '06-29', '06-30']:
    df = pd.read_csv(os.path.join(output_dir, f'仓网业务表现文件_2016-{day}.csv'))
    day_num = day.split('-')[1]
    days.append(f'6/{int(day_num)}')
    trans_wh.append(df['仓库之间的运输总成本（万元）'].values[0])
    trans_cust.append(df['仓库到门店的运输总成本（万元）'].values[0])
    proc.append(df['处置总成本（万元）'].values[0])
    daily_total.append(df['当天总成本（万元）'].values[0])

fig, ax = plt.subplots(figsize=(12, 6))
x = range(len(days))
width = 0.2

ax.bar([i - 1.5*width for i in x], trans_wh, width, label='仓库间运输', color='#2E86AB')
ax.bar([i - 0.5*width for i in x], trans_cust, width, label='仓库到门店', color='#A23B72')
ax.bar([i + 0.5*width for i in x], proc, width, label='处置成本', color='#F18F01')
ax.bar([i + 1.5*width for i in x], daily_total, width, label='当天总成本', color='#C73E1D')

ax.set_xlabel('日期', fontsize=12)
ax.set_ylabel('成本（万元）', fontsize=12)
ax.set_title('多周期仓网优化 - 每日成本变化（不含损耗）', fontsize=14)
ax.set_xticks(x)
ax.set_xticklabels(days)
ax.legend(loc='upper right')
ax.grid(axis='y', alpha=0.3)

for i, total in enumerate(daily_total):
    ax.text(i + 1.5*width, total + 30, f'{total:.0f}', ha='center', va='bottom', fontsize=8)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, '每日成本变化.png'), dpi=150, bbox_inches='tight')
print('可视化已保存')
