from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import numpy as np
import os
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = str(_REPO_ROOT)
INPUT_DIR = os.path.join(BASE_DIR, 'data/raw')

df_wh = pd.read_csv(os.path.join(INPUT_DIR, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_forecast = pd.read_csv(os.path.join(BASE_DIR, 'results/question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
skus = ['im', 'dm']
sku_cdc = {'im': port_cdc, 'dm': inland_cdc}
cdc_sku = {port_cdc: 'im', inland_cdc: 'dm'}

cap = {}; proc_cost = {}; open_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost[row['Name']] = row['Processing_fee']
    open_cost[row['Name']] = row['Opening_fee']

dist_oneway = {}
time_oneway = {}
for _, row in df_matrix.iterrows():
    dist_oneway[(row['From'], row['To'])] = row['Distance']
    time_oneway[(row['From'], row['To'])] = row['Duration']

dist_sym = {}
dur_sym = {}
for _, row in df_matrix.iterrows():
    dist_sym[(row['From'], row['To'])] = row['Distance']
    dist_sym[(row['To'], row['From'])] = row['Distance']
    dur_sym[(row['From'], row['To'])] = row['Duration']
    dur_sym[(row['To'], row['From'])] = row['Duration']

def calculate_loss_cost(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

loss_det = {(f, t): calculate_loss_cost(time_oneway[(f, t)]) for f, t in time_oneway.keys()}

loss_robust = {}
for wh_name in cdc_names + rdc_names:
    for c_city in df_customer['Name'].tolist():
        travel_time = dur_sym.get((wh_name, c_city), 10000)
        loss_robust[(wh_name, c_city)] = calculate_loss_cost(travel_time)
for cdc in cdc_names:
    for rdc in rdc_names:
        travel_time = dur_sym.get((cdc, rdc), 10000)
        loss_robust[(cdc, rdc)] = calculate_loss_cost(travel_time)

# === 检查A: CDC-RDC距离条目的方向性 ===
print("=" * 70)
print("检查A: CDC-RDC距离/时间条目的方向性")
print("=" * 70)

for cdc in cdc_names:
    for rdc in rdc_names:
        d_fwd = dist_oneway.get((cdc, rdc), None)
        d_rev = dist_oneway.get((rdc, cdc), None)
        t_fwd = time_oneway.get((cdc, rdc), None)
        t_rev = time_oneway.get((rdc, cdc), None)
        if d_fwd is None or t_fwd is None:
            print(f"  缺失正向: ({cdc}, {rdc}): dist_fwd={d_fwd}, dist_rev={d_rev}, time_fwd={t_fwd}, time_rev={t_rev}")
        if d_rev is None or t_rev is None:
            print(f"  缺失反向: ({rdc}, {cdc}): dist_rev={d_rev}, dist_fwd={d_fwd}, time_rev={t_rev}, time_fwd={t_fwd}")

# === 检查B: f变量目标系数差异 ===
print("\n" + "=" * 70)
print("检查B: f变量 (CDC->RDC调拨) 目标系数差异")
print("=" * 70)

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand = {t: {} for t in range(T)}
for _, row in df_forecast.iterrows():
    city = row['Customer']
    sku = row['SKU']
    for t_idx, date_col in enumerate(forecast_dates):
        demand[t_idx][(city, sku)] = float(row[date_col])

total_f_obj_diff = 0
for t in range(T):
    for cdc in cdc_names:
        s = cdc_sku[cdc]
        for rdc in rdc_names:
            # 确定性模型
            d_det = dist_oneway.get((cdc, rdc), 0)
            l_det = loss_det.get((cdc, rdc), 0.0)
            p_det = 2.0 * proc_cost.get(cdc, 0.0)
            obj_det = 0.9e-4 * d_det + l_det + p_det

            # 鲁棒模型
            d_rob = dist_sym.get((cdc, rdc), 99999)
            l_rob = loss_robust.get((cdc, rdc), 0.0)
            p_rob = 2.0 * proc_cost.get(cdc, 0.0)
            obj_rob = 0.9e-4 * d_rob + l_rob + p_rob

            diff = obj_det - obj_rob
            if abs(diff) > 0.001:
                total_f_obj_diff += diff * T
                print(f"  t={t}, {cdc}->{rdc}({s}): 确定性obj={obj_det:.6f}, 鲁棒obj={obj_rob:.6f}, 差={diff:.6f}")
                print(f"    dist: 确定性={d_det}, 鲁棒={d_rob}")
                print(f"    loss: 确定性={l_det:.6f}, 鲁棒={l_rob:.6f}")
                print(f"    time: 确定性={time_oneway.get((cdc, rdc), 'MISSING')}, 鲁棒={dur_sym.get((cdc, rdc), 'MISSING')}")

print(f"\n  f变量目标系数总差异 (×7周期): {total_f_obj_diff:.4f}")

# === 检查C: 确定性模型中缺失的loss_cost_matrix条目 ===
print("\n" + "=" * 70)
print("检查C: 确定性模型loss_cost_matrix中缺失的CDC-RDC条目")
print("=" * 70)

for cdc in cdc_names:
    for rdc in rdc_names:
        l_det = loss_det.get((cdc, rdc), None)
        l_rob = loss_robust.get((cdc, rdc), 0.0)
        if l_det is None:
            print(f"  缺失: ({cdc}, {rdc}): 确定性loss=0(默认), 鲁棒loss={l_rob:.4f}")
        elif abs(l_det - l_rob) > 0.001:
            print(f"  不同: ({cdc}, {rdc}): 确定性loss={l_det:.4f}, 鲁棒loss={l_rob:.4f}")

# === 检查D: 确定性模型中缺失的dist条目对u变量目标系数的影响 ===
print("\n" + "=" * 70)
print("检查D: 确定性模型中 (wh, customer) 对的dist/time条目完整性")
print("=" * 70)

customer_cities = df_customer['Name'].tolist()
all_wh_names = cdc_names + rdc_names

missing_dist_count = 0
missing_time_count = 0
for wh in all_wh_names:
    for c in customer_cities:
        if (wh, c) not in dist_oneway:
            missing_dist_count += 1
        if (wh, c) not in time_oneway:
            missing_time_count += 1

print(f"  缺失dist条目的(wh,customer)对: {missing_dist_count}")
print(f"  缺失time条目的(wh,customer)对: {missing_time_count}")

# === 检查E: 确定性模型中dist矩阵的完整性 (检查反向条目) ===
print("\n" + "=" * 70)
print("检查E: df_matrix.csv中的条目方向性")
print("=" * 70)

from_count = 0
to_count = 0
for _, row in df_matrix.iterrows():
    f = row['From']
    t = row['To']
    if f in all_wh_names:
        from_count += 1
    if t in all_wh_names:
        to_count += 1

print(f"  df_matrix总行数: {len(df_matrix)}")
print(f"  From是仓库的行数: {from_count}")
print(f"  To是仓库的行数: {to_count}")

# 检查: 对于每个(wh, customer)对，是否有正向和反向条目
both_dirs = 0
fwd_only = 0
rev_only = 0
neither = 0
for wh in all_wh_names:
    for c in customer_cities:
        has_fwd = (wh, c) in dist_oneway
        has_rev = (c, wh) in dist_oneway
        if has_fwd and has_rev:
            both_dirs += 1
        elif has_fwd:
            fwd_only += 1
        elif has_rev:
            rev_only += 1
        else:
            neither += 1

print(f"\n  (wh, customer)对的方向性:")
print(f"    双向都有: {both_dirs}")
print(f"    仅正向(wh->c): {fwd_only}")
print(f"    仅反向(c->wh): {rev_only}")
print(f"    都没有: {neither}")

# === 检查F: 关键对比 - 确定性模型用dist.get默认0 vs 实际距离 ===
print("\n" + "=" * 70)
print("检查F: 确定性模型中dist.get默认0的影响 (仅限有需求的customer)")
print("=" * 70)

total_det_obj_error = 0
for t in range(T):
    for (c, s), qty in demand[t].items():
        for wh in [sku_cdc[s]] + rdc_names:
            d_one = dist_oneway.get((wh, c), None)
            d_s = dist_sym.get((wh, c), 99999)
            t_one = time_oneway.get((wh, c), None)
            t_s = dur_sym.get((wh, c), 10000)

            if d_one is None:
                obj_det = 2.0 * proc_cost.get(wh, 0) * qty
                obj_rob = 1.45e-4 * d_s * qty + calculate_loss_cost(t_s) * qty + 2.0 * proc_cost.get(wh, 0) * qty
                diff = obj_det - obj_rob
                total_det_obj_error += diff
                if abs(diff) > 0.01:
                    print(f"  t={t}, {wh}->{c}({s}): qty={qty:.2f}, dist缺失! 对称dist={d_s}")
                    print(f"    确定性obj={obj_det:.4f}, 鲁棒obj={obj_rob:.4f}, 差={diff:.4f}")

print(f"  确定性模型因dist缺失导致的目标系数总误差: {total_det_obj_error:.4f}")

# === 检查G: 两个模型约束数量的精确对比 ===
print("\n" + "=" * 70)
print("检查G: 两个模型约束数量精确对比")
print("=" * 70)

n_demand_per_t = len(demand[0])
n_u_per_t = 0
for (c, s) in demand[0]:
    eligible = [sku_cdc[s]] + rdc_names
    n_u_per_t += len(eligible)

n_u_rdc_per_t = 0
for (c, s) in demand[0]:
    n_u_rdc_per_t += len(rdc_names)

print(f"  每周期需求对数: {n_demand_per_t}")
print(f"  每周期u变量数: {n_u_per_t}")
print(f"  每周期RDC u变量数: {n_u_rdc_per_t}")

det_constraints = {
    'monotonic': (T - 1) * len(rdc_names),
    'open_new': len(rdc_names) * 2 + len(rdc_names) * (T - 1) * 3,
    'smart_system': len(rdc_names) + len(cdc_names),
    'single_source': T * n_demand_per_t,
    'service_open': T * n_u_per_t,
    'flow_balance': T * len(rdc_names) * 2,
    'capacity': T * (len(rdc_names) + len(cdc_names)),
    'timeliness_individual': T * n_u_per_t,
    'timeliness_overall': T,
    'w_constraint': T * (len(rdc_names) + len(cdc_names)) * 2,
}

robust_constraints = {
    'monotonic': (T - 1) * len(rdc_names),
    'open_new': len(rdc_names) * T,
    'smart_system': len(rdc_names),
    'single_source': T * n_demand_per_t,
    'service_open_rdc': T * n_u_rdc_per_t,
    'flow_balance': T * len(rdc_names) * 2,
    'rdc_capacity': T * len(rdc_names),
    'cdc_capacity': T * len(cdc_names),
    'timeliness_v': T * n_demand_per_t,
    'timeliness_overall': T,
    'w_constraint': T * len(rdc_names) * 2,
}

print("\n  确定性模型约束:")
det_total = 0
for name, count in det_constraints.items():
    print(f"    {name}: {count}")
    det_total += count
print(f"    总计: {det_total}")

print("\n  鲁棒模型约束 (Γ=0%):")
rob_total = 0
for name, count in robust_constraints.items():
    print(f"    {name}: {count}")
    rob_total += count
print(f"    总计: {rob_total}")

print(f"\n  差异: {det_total - rob_total}")

# === 检查H: 时效约束的差异分析 ===
print("\n" + "=" * 70)
print("检查H: 时效约束差异分析")
print("=" * 70)

# 确定性模型: 对每个(wh, c, s), 如果travel_time<=600: u<=v; 如果>600: v+u<=1
# 鲁棒模型: 对每个(c, s): v <= sum(u for fast_wh)
# 差异: 确定性模型强制 v=1 当分配到快速仓库时

n_fast = 0
n_slow = 0
for wh in all_wh_names:
    for c in customer_cities:
        tt = dur_sym.get((wh, c), 10000)
        if tt <= 600:
            n_fast += 1
        else:
            n_slow += 1

print(f"  快速仓库-客户对 (time<=600): {n_fast}")
print(f"  慢速仓库-客户对 (time>600): {n_slow}")
print(f"  确定性模型时效约束数: {T * n_u_per_t} (每个u变量一个)")
print(f"  鲁棒模型时效约束数: {T * n_demand_per_t} (每个需求对一个)")
print(f"  差异: 确定性多 {T * n_u_per_t - T * n_demand_per_t} 个约束")

# === 关键检查: 确定性模型中time_matrix缺失导致的loss_cost=0 ===
print("\n" + "=" * 70)
print("关键检查: 确定性模型中time_matrix缺失导致的loss_cost差异")
print("=" * 70)

total_loss_diff_u = 0
total_loss_diff_f = 0
for t in range(T):
    for (c, s), qty in demand[t].items():
        for wh in [sku_cdc[s]] + rdc_names:
            l_det_val = loss_det.get((wh, c), 0.0)
            l_rob_val = loss_robust.get((wh, c), 0.0)
            diff = (l_det_val - l_rob_val) * qty
            if abs(diff) > 0.001:
                total_loss_diff_u += diff

for cdc in cdc_names:
    s = cdc_sku[cdc]
    for rdc in rdc_names:
        l_det_val = loss_det.get((cdc, rdc), 0.0)
        l_rob_val = loss_robust.get((cdc, rdc), 0.0)
        diff = (l_det_val - l_rob_val)
        if abs(diff) > 0.001:
            total_loss_diff_f += diff * T
            print(f"  f变量loss差异: {cdc}->{rdc}: 确定性={l_det_val:.4f}, 鲁棒={l_rob_val:.4f}, 差={diff:.4f}")

print(f"  u变量loss成本总差异 (7天): {total_loss_diff_u:.4f}")
print(f"  f变量loss成本总差异 (7天): {total_loss_diff_f:.4f}")
