from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import json

# Read deterministic model supply relationships for day 0
df = pd.read_csv('results/question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-24.csv')

# Separate CDC direct service vs RDC service vs CDC-to-RDC transfers
cdc_names = ['nei-lu-CDC', 'gang-kou-CDC']
rdc_service = df[~df['仓库名称'].isin(cdc_names)]
cdc_to_rdc = df[df['仓库名称'].isin(cdc_names) & df['服务对象'].str.contains('DC')]
cdc_to_cust = df[df['仓库名称'].isin(cdc_names) & ~df['服务对象'].str.contains('DC')]

col = '数量（吨）'

print('=== Day 0 Supply Relationships (Deterministic) ===')
print(f'RDC -> Customer: {len(rdc_service)} routes, total={rdc_service[col].sum():.2f} tons')
print(f'CDC -> RDC: {len(cdc_to_rdc)} routes, total={cdc_to_rdc[col].sum():.2f} tons')
print(f'CDC -> Customer (direct): {len(cdc_to_cust)} routes, total={cdc_to_cust[col].sum():.2f} tons')

print()
for cdc in cdc_names:
    cdc_direct = cdc_to_cust[cdc_to_cust['仓库名称'] == cdc]
    print(f'{cdc} direct service: {len(cdc_direct)} customers, total={cdc_direct[col].sum():.2f} tons')
    for _, row in cdc_direct.iterrows():
        print(f'  -> {row["服务对象"]} ({row["商品类型"]}): {row[col]:.2f}')

# Now read the robust model results
with open('results/question4/problem4_robust/robust_results.json', 'r') as f:
    results = json.load(f)

gamma0 = results[0]
print(f'\n=== Robust Model Gamma=0% ===')
print(f'Total cost: {gamma0["total_cost"]:.2f}')
print(f'Loss cost: {gamma0["loss_cost"]:.2f}')
print(f'Proc cost (actual): {gamma0["proc_cost_actual"]:.2f}')
print(f'Transport customer: {gamma0["transport_cost_customer"]:.2f}')
print(f'Transport warehouse: {gamma0["transport_cost_warehouse"]:.2f}')

# Read deterministic model summary
det_summary = pd.read_csv('results/question4/problem4_loss_v2/output_result/仓网业务表现文件_汇总.csv')
print(f'\n=== Deterministic Model Summary ===')
print(det_summary.to_string())

# Calculate CDC direct service demand for all days in deterministic model
import os
det_dir = 'results/question4/problem4_loss_v2/output_result'
total_cdc_direct = 0
total_rdc_cust = 0
for f in sorted(os.listdir(det_dir)):
    if f.startswith('仓网供应关系文件'):
        df_day = pd.read_csv(os.path.join(det_dir, f))
        cdc_direct = df_day[df_day['仓库名称'].isin(cdc_names) & ~df_day['服务对象'].str.contains('DC')]
        rdc_cust = df_day[~df_day['仓库名称'].isin(cdc_names)]
        total_cdc_direct += cdc_direct[col].sum()
        total_rdc_cust += rdc_cust[col].sum()

print(f'\n=== 7-Day Totals (Deterministic) ===')
print(f'CDC direct to customer: {total_cdc_direct:.2f} tons')
print(f'RDC to customer: {total_rdc_cust:.2f} tons')
print(f'CDC direct fraction: {total_cdc_direct/(total_cdc_direct+total_rdc_cust)*100:.2f}%')
