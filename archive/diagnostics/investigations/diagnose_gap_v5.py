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
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))
df_forecast = pd.read_csv(os.path.join(BASE_DIR, 'results/question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
all_wh_names = cdc_names + rdc_names
customer_cities = df_customer['Name'].tolist()

cap = {}
proc_cost = {}
open_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost[row['Name']] = row['Processing_fee']
    open_cost[row['Name']] = row['Opening_fee']

dist_det = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
time_det = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}

dist_rob = {}
dur_rob = {}
for _, row in df_matrix.iterrows():
    origin = row['From']
    dest = row['To']
    dist_rob[(origin, dest)] = row['Distance']
    dist_rob[(dest, origin)] = row['Distance']
    dur_rob[(origin, dest)] = row['Duration']
    dur_rob[(dest, origin)] = row['Duration']

def calc_loss(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

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

periods = df_forecast.columns[2:]
T = len(periods)
demand = {}
for t_idx, period in enumerate(periods):
    demand[t_idx] = {}
    for _, row in df_forecast.iterrows():
        store = row['Customer']
        sku = row['SKU']
        qty = float(row[period])
        demand[t_idx][(store, sku)] = qty

sku_cdc = {'im': port_cdc, 'dm': inland_cdc}

print("=" * 80)
print("DIAGNOSTIC: Robust vs Deterministic Model Gap Analysis")
print("=" * 80)

# 1. Check distance matrix differences
print("\n--- 1. Distance Matrix Differences ---")
missing_in_det = 0
missing_in_rob = 0
diff_values = 0
for wh in all_wh_names:
    for c in customer_cities:
        d_det = dist_det.get((wh, c), None)
        d_rob = dist_rob.get((wh, c), None)
        if d_det is None and d_rob is not None:
            missing_in_det += 1
        elif d_det is not None and d_rob is None:
            missing_in_rob += 1
        elif d_det is not None and d_rob is not None and abs(d_det - d_rob) > 0.01:
            diff_values += 1
            if diff_values <= 3:
                print(f"  DIFF: ({wh}, {c}): det={d_det}, rob={d_rob}")

print(f"  Missing in deterministic: {missing_in_det}")
print(f"  Missing in robust: {missing_in_rob}")
print(f"  Different values: {diff_values}")

# 2. Check loss cost matrix differences
print("\n--- 2. Loss Cost Matrix Differences ---")
loss_diffs = []
for wh in all_wh_names:
    for c in customer_cities:
        l_det = loss_det.get((wh, c), 0.0)
        l_rob = loss_rob.get((wh, c), 0.0)
        if abs(l_det - l_rob) > 0.001:
            loss_diffs.append((wh, c, l_det, l_rob))

print(f"  Loss cost differences: {len(loss_diffs)}")
for wh, c, l_det, l_rob in loss_diffs[:10]:
    print(f"  ({wh}, {c}): det={l_det:.4f}, rob={l_rob:.4f}, diff={l_rob-l_det:.4f}")

# 3. Check CDC-RDC loss cost differences
print("\n--- 3. CDC-RDC Loss Cost Differences ---")
cdc_rdc_diffs = []
for cdc in cdc_names:
    for rdc in rdc_names:
        l_det = loss_det.get((cdc, rdc), 0.0)
        l_rob = loss_rob.get((cdc, rdc), 0.0)
        if abs(l_det - l_rob) > 0.001:
            cdc_rdc_diffs.append((cdc, rdc, l_det, l_rob))
print(f"  CDC-RDC loss cost differences: {len(cdc_rdc_diffs)}")
for cdc, rdc, l_det, l_rob in cdc_rdc_diffs[:10]:
    print(f"  ({cdc}, {rdc}): det={l_det:.4f}, rob={l_rob:.4f}")

# 4. Analyze deterministic model's CDC direct service
print("\n--- 4. Deterministic Model CDC Direct Service Analysis ---")
det_dir = os.path.join(BASE_DIR, 'results/question4', 'problem4_loss_v2', 'output_result')
total_cdc_direct_loss = 0
total_cdc_direct_qty = 0
total_rdc_loss = 0
total_rdc_qty = 0

for t in range(T):
    period = periods[t].replace('/', '-')
    fname = os.path.join(det_dir, f'仓网供应关系文件_{period}.csv')
    if not os.path.exists(fname):
        continue
    df_rel = pd.read_csv(fname, encoding='utf-8-sig')
    
    for _, row in df_rel.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        sku = row['商品类型']
        qty = row['数量（吨）']
        
        if 'DC' in cust or 'CDC' in cust:
            continue
        
        loss_val = loss_det.get((wh, cust), 0.0)
        loss_cost = loss_val * qty
        
        if 'CDC' in wh:
            total_cdc_direct_loss += loss_cost
            total_cdc_direct_qty += qty
        else:
            total_rdc_loss += loss_cost
            total_rdc_qty += qty

print(f"  CDC direct: qty={total_cdc_direct_qty:.2f}, loss={total_cdc_direct_loss:.2f}")
print(f"  RDC serve:  qty={total_rdc_qty:.2f}, loss={total_rdc_loss:.2f}")
print(f"  Total customer loss: {total_cdc_direct_loss + total_rdc_loss:.2f}")

# 5. Calculate what the loss cost WOULD BE if CDC-served customers were served by best RDC
print("\n--- 5. Optimal Reassignment of CDC Direct Customers ---")
cdc_reassign_savings = 0
cdc_customers = []

for t in range(T):
    period = periods[t].replace('/', '-')
    fname = os.path.join(det_dir, f'仓网供应关系文件_{period}.csv')
    if not os.path.exists(fname):
        continue
    df_rel = pd.read_csv(fname, encoding='utf-8-sig')
    
    for _, row in df_rel.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        sku = row['商品类型']
        qty = row['数量（吨）']
        
        if 'CDC' not in wh:
            continue
        if 'DC' in cust or 'CDC' in cust:
            continue
        
        current_loss = loss_det.get((wh, cust), 0.0) * qty
        
        best_rdc_loss = float('inf')
        best_rdc = None
        for rdc in rdc_names:
            rdc_loss = loss_det.get((rdc, cust), 0.0) * qty
            if rdc_loss < best_rdc_loss:
                best_rdc_loss = rdc_loss
                best_rdc = rdc
        
        savings = current_loss - best_rdc_loss
        if savings > 0.1:
            cdc_customers.append({
                'day': t, 'cdc': wh, 'customer': cust, 'sku': sku, 'qty': qty,
                'cdc_loss': current_loss, 'best_rdc': best_rdc, 'best_rdc_loss': best_rdc_loss,
                'savings': savings
            })
        cdc_reassign_savings += max(0, savings)

print(f"  Total savings from reassigning CDC customers to best RDC: {cdc_reassign_savings:.2f}")
print(f"  Number of CDC-customer assignments that could be improved: {len(cdc_customers)}")
if cdc_customers:
    cdc_df = pd.DataFrame(cdc_customers)
    top10 = cdc_df.nlargest(10, 'savings')
    print("\n  Top 10 savings opportunities:")
    for _, r in top10.iterrows():
        print(f"    Day {r['day']}: {r['cdc']} -> {r['customer']} ({r['sku']}, {r['qty']:.2f}t): "
              f"loss {r['cdc_loss']:.2f} -> {r['best_rdc_loss']:.2f}, save {r['savings']:.2f}")

# 6. Check if the deterministic model has suboptimal RDC-customer assignments
print("\n--- 6. Suboptimal RDC-Customer Assignments in Deterministic Model ---")
subopt_savings = 0
subopt_count = 0

for t in range(T):
    period = periods[t].replace('/', '-')
    fname = os.path.join(det_dir, f'仓网供应关系文件_{period}.csv')
    if not os.path.exists(fname):
        continue
    df_rel = pd.read_csv(fname, encoding='utf-8-sig')
    
    for _, row in df_rel.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        sku = row['商品类型']
        qty = row['数量（吨）']
        
        if 'DC' in cust or 'CDC' in cust:
            continue
        if 'CDC' in wh:
            continue
        
        current_loss = loss_det.get((wh, cust), 0.0) * qty
        
        best_loss = float('inf')
        best_wh = None
        for w in all_wh_names:
            if sku == 'im' and w == inland_cdc:
                continue
            if sku == 'dm' and w == port_cdc:
                continue
            l = loss_det.get((w, cust), 0.0) * qty
            if l < best_loss:
                best_loss = l
                best_wh = w
        
        if best_loss < current_loss - 0.01:
            subopt_savings += current_loss - best_loss
            subopt_count += 1

print(f"  Suboptimal RDC-customer assignments: {subopt_count}")
print(f"  Total potential savings: {subopt_savings:.2f}")

# 7. Key comparison: transport cost calculation
print("\n--- 7. Transport Cost Calculation Differences ---")
diff_count = 0
for wh in all_wh_names:
    for c in customer_cities:
        d_det = dist_det.get((wh, c), 0)
        d_rob = dist_rob.get((wh, c), 99999)
        if d_det != d_rob and d_rob < 5000:
            diff_count += 1
            if diff_count <= 5:
                print(f"  ({wh}, {c}): det_dist={d_det}, rob_dist={d_rob}")
print(f"  Total (wh, cust) pairs with different distances (robust < 5000): {diff_count}")

# 8. Check CDC-RDC transport cost differences
print("\n--- 8. CDC-RDC Transport Cost Differences ---")
cdc_rdc_transport_diff = 0
for cdc in cdc_names:
    for rdc in rdc_names:
        d_det = dist_det.get((cdc, rdc), 0)
        d_rob = dist_rob.get((cdc, rdc), 99999)
        if d_det != d_rob:
            print(f"  ({cdc}, {rdc}): det_dist={d_det}, rob_dist={d_rob}")
            cdc_rdc_transport_diff += 1
print(f"  CDC-RDC pairs with different distances: {cdc_rdc_transport_diff}")

# 9. Calculate total cost for deterministic model solution using robust model's cost method
print("\n--- 9. Recalculate Deterministic Model Cost Using Robust Model's Method ---")
total_loss_rob_method = 0
total_trans_cust_rob = 0
total_trans_wh_rob = 0
total_proc_rob = 0

for t in range(T):
    period = periods[t].replace('/', '-')
    fname = os.path.join(det_dir, f'仓网供应关系文件_{period}.csv')
    if not os.path.exists(fname):
        continue
    df_rel = pd.read_csv(fname, encoding='utf-8-sig')
    
    for _, row in df_rel.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        sku = row['商品类型']
        qty = row['数量（吨）']
        
        if 'DC' in cust or 'CDC' in cust:
            # This is a CDC-RDC transfer
            d_rob = dist_rob.get((wh, cust), 99999)
            l_rob = loss_rob.get((wh, cust), 0.0)
            total_trans_wh_rob += 0.9e-4 * d_rob * qty
            total_loss_rob_method += l_rob * qty
            total_proc_rob += 2.0 * proc_cost.get(wh, 0.0) * qty
        else:
            # This is a warehouse-customer assignment
            d_rob = dist_rob.get((wh, cust), 99999)
            l_rob = loss_rob.get((wh, cust), 0.0)
            total_trans_cust_rob += 1.45e-4 * d_rob * qty
            total_loss_rob_method += l_rob * qty
            total_proc_rob += 2.0 * proc_cost.get(wh, 0.0) * qty

print(f"  Loss (robust method): {total_loss_rob_method:.2f}")
print(f"  Transport cust (robust method): {total_trans_cust_rob:.2f}")
print(f"  Transport wh (robust method): {total_trans_wh_rob:.2f}")
print(f"  Proc (robust method): {total_proc_rob:.2f}")

# Compare with deterministic model's reported costs
print(f"\n  Deterministic model reported loss: 219875.88")
print(f"  Recalculated loss (robust method): {total_loss_rob_method:.2f}")
print(f"  Difference: {total_loss_rob_method - 219875.88:.2f}")

# 10. Calculate total cost for deterministic model solution using deterministic model's cost method
print("\n--- 10. Recalculate Deterministic Model Cost Using Deterministic Model's Method ---")
total_loss_det_method = 0
total_trans_cust_det = 0
total_trans_wh_det = 0
total_proc_det = 0

for t in range(T):
    period = periods[t].replace('/', '-')
    fname = os.path.join(det_dir, f'仓网供应关系文件_{period}.csv')
    if not os.path.exists(fname):
        continue
    df_rel = pd.read_csv(fname, encoding='utf-8-sig')
    
    for _, row in df_rel.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        sku = row['商品类型']
        qty = row['数量（吨）']
        
        if 'DC' in cust or 'CDC' in cust:
            d_det = dist_det.get((wh, cust), 0)
            l_det = loss_det.get((wh, cust), 0.0)
            total_trans_wh_det += 0.9e-4 * d_det * qty
            total_loss_det_method += l_det * qty
            total_proc_det += 2.0 * proc_cost.get(wh, 0.0) * qty
        else:
            d_det = dist_det.get((wh, cust), 0)
            l_det = loss_det.get((wh, cust), 0.0)
            total_trans_cust_det += 1.45e-4 * d_det * qty
            total_loss_det_method += l_det * qty
            total_proc_det += 2.0 * proc_cost.get(wh, 0.0) * qty

print(f"  Loss (det method): {total_loss_det_method:.2f}")
print(f"  Transport cust (det method): {total_trans_cust_det:.2f}")
print(f"  Transport wh (det method): {total_trans_wh_det:.2f}")
print(f"  Proc (det method): {total_proc_det:.2f}")
print(f"\n  Deterministic model reported loss: 219875.88")
print(f"  Difference: {total_loss_det_method - 219875.88:.2f}")

print("\n" + "=" * 80)
print("SUMMARY: Key differences between models")
print("=" * 80)
print(f"  1. Loss cost matrix differences: {len(loss_diffs)} pairs")
print(f"  2. CDC direct service in deterministic: {total_cdc_direct_qty:.2f} tons, loss={total_cdc_direct_loss:.2f}")
print(f"  3. Reassignment savings (CDC->best RDC): {cdc_reassign_savings:.2f}")
print(f"  4. Suboptimal RDC assignments: {subopt_count}, savings: {subopt_savings:.2f}")
print(f"  5. Loss cost recalc difference (robust-det method): {total_loss_rob_method - total_loss_det_method:.2f}")
