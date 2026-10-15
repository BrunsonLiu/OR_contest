"""
终极定位: 从确定性模型的CPLEX解中提取路由，与鲁棒模型对比
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd, numpy as np, os

BASE = str(_REPO_ROOT)
det_dir = f'{BASE}/results/question4/problem4_loss_v2/output_result'

if not os.path.exists(det_dir):
    det_dir = f'{BASE}/results/question4/problem4_loss/output_result'

df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
dur = {}
for _, r in df_matrix.iterrows():
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

def loss_per_ton(t):
    return 0.0 if t<=500 else 0.2*(t-500)**2/10000

forecast_dates = ['2016-06-24','2016-06-25','2016-06-26','2016-06-27',
                  '2016-06-28','2016-06-29','2016-06-30']

# 读取确定性模型第一天(2016-06-24)的供应关系
csv_file = f'{det_dir}/仓网供应关系文件_2016-06-24.csv'
if not os.path.exists(csv_file):
    print(f"文件不存在: {csv_file}")
    print(f"可用文件: {os.listdir(det_dir) if os.path.exists(det_dir) else 'DIR NOT FOUND'}")
    exit()

df = pd.read_csv(csv_file)
col_wh = df.columns[0]
col_to = df.columns[1]
col_sku = df.columns[2]
col_qty = df.columns[3]

print("=" * 70)
print(f"确定性模型 Day 0 ({forecast_dates[0]}) 路由分析")
print("=" * 70)

cdc_to_cust = 0
rdc_to_cust = 0
cdc_to_cust_loss = 0
rdc_to_cust_loss = 0
cdc_to_rdc_loss = 0
cdc_to_rdc_tons = 0

for _, row in df.iterrows():
    wh = row[col_wh]
    to = row[col_to]
    sku = row[col_sku]
    qty = float(row[col_qty])
    
    t_min = dur.get((wh, to), dur.get((to, wh), 0))
    loss = loss_per_ton(t_min) * qty
    
    if 'CDC' in wh and 'DC' in to and 'CDC' not in to:
        # CDC → RDC 调拨
        cdc_to_rdc_loss += loss
        cdc_to_rdc_tons += qty
    elif 'CDC' in wh:
        # CDC → 门店 直送
        cdc_to_cust += qty
        cdc_to_cust_loss += loss
    else:
        # RDC → 门店
        rdc_to_cust += qty
        rdc_to_cust_loss += loss

print(f"  CDC→RDC: {cdc_to_rdc_tons:.0f} 吨, 损耗 {cdc_to_rdc_loss:.0f} 万, "
      f"均值 {cdc_to_rdc_loss/cdc_to_rdc_tons:.4f} 万/吨" if cdc_to_rdc_tons > 0 else "  CDC→RDC: 0")
print(f"  CDC→门店: {cdc_to_cust:.0f} 吨, 损耗 {cdc_to_cust_loss:.0f} 万")
print(f"  RDC→门店: {rdc_to_cust:.0f} 吨, 损耗 {rdc_to_cust_loss:.0f} 万, "
      f"均值 {rdc_to_cust_loss/rdc_to_cust:.4f} 万/吨" if rdc_to_cust > 0 else "  RDC→门店: 0")
print(f"  总损耗: {cdc_to_rdc_loss + cdc_to_cust_loss + rdc_to_cust_loss:.0f} 万")

# 关键: CDC直送门店的比例
total_cust = cdc_to_cust + rdc_to_cust
print(f"\n  CDC直送占比: {cdc_to_cust/total_cust*100:.1f}%")
print(f"  RDC配送占比: {rdc_to_cust/total_cust*100:.1f}%")

# 列出CDC直送的具体门店
print(f"\n  CDC直送门店明细:")
for _, row in df.iterrows():
    wh = row[col_wh]
    to = row[col_to]
    sku = row[col_sku]
    qty = float(row[col_qty])
    if 'CDC' in wh and ('DC' not in to or 'CDC' in to):
        t_min = dur.get((wh, to), dur.get((to, wh), 0))
        loss = loss_per_ton(t_min)
        print(f"    {wh} → {to} ({sku}): {qty:.0f}吨, {t_min}min, loss={loss:.4f}万/吨")
