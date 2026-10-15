# -*- coding: utf-8 -*-
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import sys, io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd, numpy as np, os

BASE = str(_REPO_ROOT)
INPUT = os.path.join(BASE, 'data/raw')

df_wh = pd.read_csv(os.path.join(INPUT, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(INPUT, 'df_proc.csv'))
df_customer = pd.read_csv(os.path.join(INPUT, 'df_customer.csv'))
df_forecast = pd.read_csv(os.path.join(BASE, 'results/question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
sku_cdc = {'im': port_cdc, 'dm': inland_cdc}
all_wh_names = cdc_names + rdc_names

proc_cost = {}
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']

customer_cities = df_customer['Name'].tolist()

dist_det = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
time_det = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}

dist_rob = {}
dur_rob = {}
for _, row in df_matrix.iterrows():
    o, d = row['From'], row['To']
    dist_rob[(o, d)] = row['Distance']
    dist_rob[(d, o)] = row['Distance']
    dur_rob[(o, d)] = row['Duration']
    dur_rob[(d, o)] = row['Duration']

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand = {}
for t_idx, date_col in enumerate(forecast_dates):
    demand[t_idx] = {}
    for _, row in df_forecast.iterrows():
        demand[t_idx][(row['Customer'], row['SKU'])] = float(row[date_col])

LOSS_THRESHOLD = 500.0
def calc_loss(minutes):
    if minutes <= LOSS_THRESHOLD:
        return 0.0
    return 0.2 * (minutes - LOSS_THRESHOLD) ** 2 / 10000.0

loss_det = {(f, t): calc_loss(time_det[(f, t)]) for f, t in time_det.keys()}
loss_rob = {}
for wh in all_wh_names:
    for c in customer_cities:
        tt = dur_rob.get((wh, c), 10000)
        loss_rob[(wh, c)] = calc_loss(tt)
for cdc in cdc_names:
    for rdc in rdc_names:
        tt = dur_rob.get((cdc, rdc), 10000)
        loss_rob[(cdc, rdc)] = calc_loss(tt)

print('=== u variable objective coefficient differences ===')
diff_count = 0
zero_det_nonzero_rob = 0
total_det_u = 0
total_rob_u = 0
sample = []

for t in range(T):
    for (c, s), qty in demand[t].items():
        eligible = [sku_cdc[s]] + rdc_names
        for wh in eligible:
            d_det = dist_det.get((wh, c), 0)
            d_rob = dist_rob.get((wh, c), 99999)
            l_det = loss_det.get((wh, c), 0.0)
            l_rob = loss_rob.get((wh, c), 0.0)
            obj_det = 1.45e-4 * d_det * qty + l_det * qty + 2.0 * proc_cost.get(wh, 0.0) * qty
            obj_rob = 1.45e-4 * d_rob * qty + l_rob * qty + 2.0 * proc_cost.get(wh, 0.0) * qty
            total_det_u += obj_det
            total_rob_u += obj_rob
            if abs(obj_det - obj_rob) > 0.001:
                diff_count += 1
                if d_det == 0 and d_rob > 0:
                    zero_det_nonzero_rob += 1
                if len(sample) < 15:
                    sample.append(f'  u_{t}_{wh}_{c}_{s}: dist({d_det:.0f} vs {d_rob:.0f}) loss({l_det:.4f} vs {l_rob:.4f}) obj({obj_det:.2f} vs {obj_rob:.2f}) diff={obj_det-obj_rob:.2f} qty={qty:.2f}')

print(f'Diff u-vars: {diff_count}')
print(f'  det_dist=0 but rob>0: {zero_det_nonzero_rob}')
print(f'  Det total: {total_det_u:.2f}')
print(f'  Rob total: {total_rob_u:.2f}')
print(f'  Diff: {total_det_u - total_rob_u:.2f}')
for s in sample:
    print(s)

print()
print('=== Zero-distance routes (missing reverse in det) ===')
zero_routes = []
for t in range(T):
    for (c, s), qty in demand[t].items():
        eligible = [sku_cdc[s]] + rdc_names
        for wh in eligible:
            d_det = dist_det.get((wh, c), 0)
            d_rob = dist_rob.get((wh, c), 99999)
            if d_det == 0 and d_rob > 0:
                zero_routes.append((t, wh, c, s, qty, d_rob))

print(f'Zero-dist routes: {len(zero_routes)}')
if zero_routes:
    total_qty = sum(r[4] for r in zero_routes)
    print(f'Affected demand: {total_qty:.2f} tons')
    for r in zero_routes[:15]:
        print(f'  t={r[0]} {r[1]}->{r[2]}({r[3]}): det=0, actual={r[5]:.0f}km, qty={r[4]:.2f}')

print()
print('=== f variable differences ===')
f_diff = 0
for t in range(T):
    for cdc in cdc_names:
        s = 'im' if cdc == port_cdc else 'dm'
        for rdc in rdc_names:
            d_det = dist_det.get((cdc, rdc), 0)
            d_rob = dist_rob.get((cdc, rdc), 99999)
            l_det = loss_det.get((cdc, rdc), 0.0)
            l_rob = loss_rob.get((cdc, rdc), 0.0)
            obj_det = 0.9e-4 * d_det + l_det + 2.0 * proc_cost.get(cdc, 0.0)
            obj_rob = 0.9e-4 * d_rob + l_rob + 2.0 * proc_cost.get(cdc, 0.0)
            if abs(obj_det - obj_rob) > 0.001:
                f_diff += 1
                if f_diff <= 5:
                    print(f'  f_{t}_{cdc}_{rdc}_{s}: dist({d_det:.0f} vs {d_rob:.0f}) obj({obj_det:.6f} vs {obj_rob:.6f})')
print(f'f-var diffs: {f_diff}')
