from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import numpy as np
import os

BASE_DIR = str(_REPO_ROOT)
INPUT_DIR = os.path.join(BASE_DIR, 'data/raw')

df_wh = pd.read_csv(os.path.join(INPUT_DIR, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))
df_forecast = pd.read_csv(os.path.join(BASE_DIR, 'results/question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = list(df_wh[df_wh['Type'] == 'CDC']['Name'])
rdc_names = list(df_wh[df_wh['Type'] == 'RDC']['Name'])
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
customer_cities = list(df_customer['Name'])
all_wh = cdc_names + rdc_names

dist_det = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
dur_det = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}

dist_rob = {}
dur_rob = {}
for _, row in df_matrix.iterrows():
    dist_rob[(row['From'], row['To'])] = row['Distance']
    dist_rob[(row['To'], row['From'])] = row['Distance']
    dur_rob[(row['From'], row['To'])] = row['Duration']
    dur_rob[(row['To'], row['From'])] = row['Duration']

print("=" * 80)
print("CRITICAL: tai-zhou-shi missing from distance matrix!")
print("=" * 80)

forecast_cities = set()
for _, row in df_forecast.iterrows():
    forecast_cities.add(row['Customer'])

print(f"\nCustomer cities in df_customer: {len(customer_cities)}")
print(f"Customer cities in forecast: {len(forecast_cities)}")

matrix_from = set(df_matrix['From'].unique())
matrix_to = set(df_matrix['To'].unique())
matrix_locations = matrix_from | matrix_to

missing_from_matrix = set(customer_cities) - matrix_locations
print(f"\nCities in customer list but NOT in distance matrix: {sorted(missing_from_matrix)}")

missing_from_matrix_fc = forecast_cities - matrix_locations
print(f"Cities in forecast but NOT in distance matrix: {sorted(missing_from_matrix_fc)}")

print("\n" + "=" * 80)
print("Impact analysis: tai-zhou-shi demand")
print("=" * 80)

tz_demand = {}
forecast_cols = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
for _, row in df_forecast.iterrows():
    if row['Customer'] == 'tai-zhou-shi':
        for col in forecast_cols:
            if col not in tz_demand:
                tz_demand[col] = {'im': 0, 'dm': 0}
            tz_demand[col][row['SKU']] += float(row[col])

print(f"\ntai-zhou-shi demand by day:")
total_tz = 0
for col in sorted(tz_demand.keys()):
    im = tz_demand[col]['im']
    dm = tz_demand[col]['dm']
    total_tz += im + dm
    print(f"  {col}: im={im:.2f}, dm={dm:.2f}, total={im+dm:.2f}")
print(f"  Total 7-day demand: {total_tz:.2f} tons")

total_all_demand = 0
for _, row in df_forecast.iterrows():
    for col in forecast_cols:
        total_all_demand += float(row[col])
print(f"  Total all demand: {total_all_demand:.2f} tons")
print(f"  tai-zhou-shi share: {total_tz/total_all_demand*100:.2f}%")

print("\n" + "=" * 80)
print("What happens in deterministic model with tai-zhou-shi?")
print("=" * 80)

print("\n  In det model: dist.get((wh, 'tai-zhou-shi'), 0) = 0")
print("  In det model: time_matrix.get((wh, 'tai-zhou-shi'), inf) = inf")
print("  In det model: loss_cost_matrix.get((wh, 'tai-zhou-shi'), 0.0) = 0.0")
print("  => transport=0, loss=0, but proc_cost>0")
print("  => CPLEX will serve tai-zhou-shi from cheapest-proc-cost warehouse")

for wh in all_wh:
    d_det = dist_det.get((wh, 'tai-zhou-shi'), 'MISSING')
    d_rob = dist_rob.get((wh, 'tai-zhou-shi'), 'MISSING')
    dur_d = dur_det.get((wh, 'tai-zhou-shi'), 'MISSING')
    dur_r = dur_rob.get((wh, 'tai-zhou-shi'), 'MISSING')
    if d_det != d_rob or d_det == 'MISSING':
        print(f"  {wh}: dist_det={d_det}, dist_rob={d_rob}, dur_det={dur_d}, dur_rob={dur_r}")

print("\n" + "=" * 80)
print("What happens in robust model with tai-zhou-shi?")
print("=" * 80)
print("  dist_matrix.get((wh, 'tai-zhou-shi'), 99999) = 99999 > 5000")
print("  => u variables NOT created")
print("  => single-source constraint skipped (if indices empty)")
print("  => tai-zhou-shi demand NOT SERVED at all!")
print("  => This is a BUG - demand should be served!")

print("\n" + "=" * 80)
print("Cost impact estimation")
print("=" * 80)

proc_cost = {}
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']

min_proc_rdc = min(proc_cost[wh] for wh in rdc_names)
tz_proc_cost = 2.0 * min_proc_rdc * total_tz
print(f"  Min RDC proc_cost: {min_proc_rdc}")
print(f"  tai-zhou-shi proc cost (if served by cheapest RDC): {tz_proc_cost:.2f} wan yuan")
print(f"  This is the EXTRA cost the det model pays (that rob model doesn't)")
print(f"  Gap = 233950 - 225123 = {233950-225123} wan yuan")
print(f"  tai-zhou-shi proc cost / gap = {tz_proc_cost/(233950-225123)*100:.1f}%")

print("\n" + "=" * 80)
print("Other missing cities check")
print("=" * 80)
for city in sorted(customer_cities):
    has_dist = any((wh, city) in dist_rob for wh in all_wh)
    if not has_dist:
        print(f"  {city}: NO distance data to ANY warehouse!")

print("\n" + "=" * 80)
print("df_matrix locations vs customer cities")
print("=" * 80)
cust_in_matrix = [c for c in customer_cities if c in matrix_locations]
cust_not_in_matrix = [c for c in customer_cities if c not in matrix_locations]
print(f"  Customers in matrix: {len(cust_in_matrix)}")
print(f"  Customers NOT in matrix: {len(cust_not_in_matrix)}")
if cust_not_in_matrix:
    print(f"  Missing: {sorted(cust_not_in_matrix)}")

wh_in_matrix = [w for w in all_wh if w in matrix_locations]
wh_not_in_matrix = [w for w in all_wh if w not in matrix_locations]
print(f"  Warehouses in matrix: {len(wh_in_matrix)}")
print(f"  Warehouses NOT in matrix: {len(wh_not_in_matrix)}")
if wh_not_in_matrix:
    print(f"  Missing: {sorted(wh_not_in_matrix)}")
