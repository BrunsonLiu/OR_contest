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
all_wh_names = cdc_names + rdc_names
customer_cities = df_customer['Name'].tolist()
skus = ['im', 'dm']
sku_cdc = {'im': port_cdc, 'dm': inland_cdc}
cdc_sku = {port_cdc: 'im', inland_cdc: 'dm'}

cap = {}; proc_cost = {}; open_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost[row['Name']] = row['Processing_fee']
    open_cost[row['Name']] = row['Opening_fee']

# === 确定性模型的距离矩阵 (单向) ===
dist_oneway = {}
time_oneway = {}
for _, row in df_matrix.iterrows():
    dist_oneway[(row['From'], row['To'])] = row['Distance']
    time_oneway[(row['From'], row['To'])] = row['Duration']

# === 鲁棒模型的距离矩阵 (对称) ===
dist_sym = {}
dur_sym = {}
for _, row in df_matrix.iterrows():
    dist_sym[(row['From'], row['To'])] = row['Distance']
    dist_sym[(row['To'], row['From'])] = row['Distance']
    dur_sym[(row['From'], row['To'])] = row['Duration']
    dur_sym[(row['To'], row['From'])] = row['Duration']

# === 需求数据 ===
forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand = {t: {} for t in range(T)}
for _, row in df_forecast.iterrows():
    city = row['Customer']
    sku = row['SKU']
    for t_idx, date_col in enumerate(forecast_dates):
        demand[t_idx][(city, sku)] = float(row[date_col])

def calculate_loss_cost(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

# === 检查1: 单向距离矩阵中缺失的 (wh, customer) 对 ===
print("=" * 70)
print("检查1: 单向距离矩阵中缺失的 (wh, customer) 对")
print("=" * 70)

missing_oneway = 0
missing_oneway_pairs = []
for wh in all_wh_names:
    for c in customer_cities:
        if (wh, c) not in dist_oneway:
            missing_oneway += 1
            missing_oneway_pairs.append((wh, c))

print(f"  缺失的 (wh, customer) 对: {missing_oneway}")
if missing_oneway > 0:
    for wh, c in missing_oneway_pairs[:20]:
        reverse_dist = dist_oneway.get((c, wh), 'MISSING')
        print(f"    ({wh}, {c}): 正向缺失, 反向 dist({c},{wh}) = {reverse_dist}")

# === 检查2: 确定性模型中 dist.get((wh,store),0) 返回0的对 ===
print("\n" + "=" * 70)
print("检查2: 确定性模型中距离=0的 (wh, customer) 对 (缺失→默认0)")
print("=" * 70)

zero_dist_pairs = []
for wh in all_wh_names:
    for c in customer_cities:
        d = dist_oneway.get((wh, c), 0)
        if d == 0 and (wh, c) not in dist_oneway:
            zero_dist_pairs.append((wh, c))

print(f"  距离=0(因缺失)的对数: {len(zero_dist_pairs)}")
if zero_dist_pairs:
    for wh, c in zero_dist_pairs[:20]:
        sym_d = dist_sym.get((wh, c), 'MISSING')
        print(f"    ({wh}, {c}): 确定性dist=0, 鲁棒dist={sym_d}")

# === 检查3: u变量差异 ===
print("\n" + "=" * 70)
print("检查3: u变量 (服务关系) 差异")
print("=" * 70)

det_u_vars = set()
robust_u_vars = set()

for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand[t]:
                continue
            eligible = [sku_cdc[s]] + rdc_names
            for wh in eligible:
                # 确定性模型: 无距离过滤
                det_u_vars.add(f'u_{t}_{wh}_{c}_{s}')
                # 鲁棒模型: dist > 5000km 过滤
                dist_km = dist_sym.get((wh, c), 99999)
                if dist_km <= 5000:
                    robust_u_vars.add(f'u_{t}_{wh}_{c}_{s}')

only_det = det_u_vars - robust_u_vars
only_robust = robust_u_vars - det_u_vars

print(f"  确定性模型u变量数: {len(det_u_vars)}")
print(f"  鲁棒模型u变量数: {len(robust_u_vars)}")
print(f"  仅确定性模型有: {len(only_det)}")
print(f"  仅鲁棒模型有: {len(only_robust)}")

if only_det:
    print(f"\n  仅确定性模型有的u变量 (前20个):")
    for v in sorted(only_det)[:20]:
        parts = v.split('_')
        t, wh, c, s = parts[1], parts[2], parts[3], parts[4]
        d_sym = dist_sym.get((wh, c), 99999)
        d_one = dist_oneway.get((wh, c), 'MISSING')
        print(f"    {v}: 对称dist={d_sym}, 单向dist={d_one}")

# === 检查4: f变量差异 ===
print("\n" + "=" * 70)
print("检查4: f变量 (调拨量) 差异")
print("=" * 70)

det_f_vars = set()
robust_f_vars = set()

for t in range(T):
    for cdc in cdc_names:
        s = cdc_sku[cdc]
        for rdc in rdc_names:
            det_f_vars.add(f'f_{t}_{cdc}_{rdc}_{s}')
            dist_km = dist_sym.get((cdc, rdc), 99999)
            if dist_km <= 5000:
                robust_f_vars.add(f'f_{t}_{cdc}_{rdc}_{s}')

only_det_f = det_f_vars - robust_f_vars
print(f"  确定性模型f变量数: {len(det_f_vars)}")
print(f"  鲁棒模型f变量数: {len(robust_f_vars)}")
print(f"  仅确定性模型有: {len(only_det_f)}")

if only_det_f:
    print(f"\n  仅确定性模型有的f变量:")
    for v in sorted(only_det_f):
        parts = v.split('_')
        t, cdc, rdc, s = parts[1], parts[2], parts[3], parts[4]
        d_sym = dist_sym.get((cdc, rdc), 99999)
        print(f"    {v}: dist={d_sym}")

# === 检查5: 流量平衡约束缺失 ===
print("\n" + "=" * 70)
print("检查5: 鲁棒模型中因f变量缺失而跳过的流量平衡约束")
print("=" * 70)

skipped_balance = 0
for t in range(T):
    for rdc in rdc_names:
        for s in skus:
            cdc_name = sku_cdc[s]
            f_var = f'f_{t}_{cdc_name}_{rdc}_{s}'
            if f_var not in robust_f_vars:
                has_customers = False
                for c in customer_cities:
                    u_var = f'u_{t}_{rdc}_{c}_{s}'
                    if u_var in robust_u_vars and (c, s) in demand[t]:
                        has_customers = True
                        break
                if has_customers:
                    skipped_balance += 1
                    d = dist_sym.get((cdc_name, rdc), 99999)
                    print(f"    跳过: t={t}, {cdc_name}->{rdc}, sku={s}, dist={d}")

print(f"  因f缺失而跳过的流量平衡约束: {skipped_balance}")

# === 检查6: 单源约束差异 ===
print("\n" + "=" * 70)
print("检查6: 单源约束差异 (因u变量缺失导致约束不完整)")
print("=" * 70)

incomplete_single_source = 0
for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand[t]:
                continue
            det_count = sum(1 for wh in [sku_cdc[s]] + rdc_names
                          if f'u_{t}_{wh}_{c}_{s}' in det_u_vars)
            robust_count = sum(1 for wh in [sku_cdc[s]] + rdc_names
                             if f'u_{t}_{wh}_{c}_{s}' in robust_u_vars)
            if det_count != robust_count:
                incomplete_single_source += 1
                if incomplete_single_source <= 10:
                    missing_whs = [wh for wh in [sku_cdc[s]] + rdc_names
                                 if f'u_{t}_{wh}_{c}_{s}' in det_u_vars and
                                    f'u_{t}_{wh}_{c}_{s}' not in robust_u_vars]
                    for wh in missing_whs:
                        d = dist_sym.get((wh, c), 99999)
                        print(f"    t={t}, c={c}, s={s}: 缺少wh={wh}, dist={d}")

print(f"  单源约束中u变量数不同的对数: {incomplete_single_source}")

# === 检查7: 目标函数系数差异 ===
print("\n" + "=" * 70)
print("检查7: 共同u变量的目标函数系数差异")
print("=" * 70)

common_u = det_u_vars & robust_u_vars
obj_diff_count = 0
obj_diff_total = 0
max_obj_diff = 0
max_obj_diff_var = ""

for v in common_u:
    parts = v.split('_')
    t_idx, wh, c, s = int(parts[1]), parts[2], parts[3], parts[4]
    if (c, s) not in demand[t_idx]:
        continue
    qty = demand[t_idx][(c, s)]

    # 确定性模型的目标系数
    d_one = dist_oneway.get((wh, c), 0)
    loss_one = calculate_loss_cost(time_oneway.get((wh, c), 0))
    obj_det = 1.45e-4 * d_one * qty + loss_one * qty + 2.0 * proc_cost.get(wh, 0) * qty

    # 鲁棒模型的目标系数
    d_sym = dist_sym.get((wh, c), 99999)
    loss_sym = calculate_loss_cost(dur_sym.get((wh, c), 10000))
    obj_robust = 1.45e-4 * d_sym * qty + loss_sym * qty + 2.0 * proc_cost.get(wh, 0) * qty

    diff = abs(obj_det - obj_robust)
    if diff > 0.001:
        obj_diff_count += 1
        obj_diff_total += diff
        if diff > max_obj_diff:
            max_obj_diff = diff
            max_obj_diff_var = v

print(f"  共同u变量数: {len(common_u)}")
print(f"  目标系数不同的u变量数: {obj_diff_count}")
print(f"  目标系数差异总和: {obj_diff_total:.4f}")
print(f"  最大差异: {max_obj_diff:.4f} ({max_obj_diff_var})")

# === 检查8: CDC-RDC距离 ===
print("\n" + "=" * 70)
print("检查8: CDC-RDC距离 (检查是否有 > 5000km)")
print("=" * 70)

for cdc in cdc_names:
    for rdc in rdc_names:
        d = dist_sym.get((cdc, rdc), 99999)
        d_one = dist_oneway.get((cdc, rdc), 'MISSING')
        if d > 5000 or d_one == 'MISSING':
            print(f"  {cdc} -> {rdc}: 对称dist={d}, 单向dist={d_one}")

# === 检查9: 确定性模型中缺失距离导致的0成本分配 ===
print("\n" + "=" * 70)
print("检查9: 确定性模型中因距离缺失导致的0运输成本u变量")
print("=" * 70)

zero_trans_cost_vars = 0
zero_trans_cost_total_demand = 0
for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand[t]:
                continue
            qty = demand[t][(c, s)]
            for wh in [sku_cdc[s]] + rdc_names:
                d = dist_oneway.get((wh, c), None)
                if d is None:
                    zero_trans_cost_vars += 1
                    zero_trans_cost_total_demand += qty

print(f"  距离缺失的u变量数: {zero_trans_cost_vars}")
print(f"  对应的总需求量: {zero_trans_cost_total_demand:.2f} 吨")

# === 检查10: 确定性模型中缺失时间导致的0损耗成本 ===
print("\n" + "=" * 70)
print("检查10: 确定性模型中因时间缺失导致的损耗成本差异")
print("=" * 70)

loss_diff_pairs = 0
loss_diff_total = 0
for wh in all_wh_names:
    for c in customer_cities:
        t_one = time_oneway.get((wh, c), None)
        t_sym = dur_sym.get((wh, c), 10000)
        loss_one = calculate_loss_cost(t_one) if t_one is not None else 0.0
        loss_sym = calculate_loss_cost(t_sym)
        if abs(loss_one - loss_sym) > 0.001:
            loss_diff_pairs += 1
            loss_diff_total += abs(loss_one - loss_sym)
            if loss_diff_pairs <= 10:
                print(f"  ({wh}, {c}): 确定性loss={loss_one:.4f}, 鲁棒loss={loss_sym:.4f}, "
                      f"时间: 确定性={'MISSING' if t_one is None else t_one}, 鲁棒={t_sym}")

print(f"  损耗成本不同的对数: {loss_diff_pairs}")
print(f"  损耗成本差异总和: {loss_diff_total:.4f}")

# === 关键检查: 确定性模型中缺失距离条目的影响 ===
print("\n" + "=" * 70)
print("关键检查: 确定性模型中缺失距离条目的完整影响分析")
print("=" * 70)

total_impact = 0
impact_details = []
for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand[t]:
                continue
            qty = demand[t][(c, s)]
            for wh in [sku_cdc[s]] + rdc_names:
                d_one = dist_oneway.get((wh, c), None)
                if d_one is None:
                    d_sym = dist_sym.get((wh, c), 99999)
                    t_one = time_oneway.get((wh, c), None)
                    t_sym = dur_sym.get((wh, c), 10000)

                    obj_det = 2.0 * proc_cost.get(wh, 0) * qty
                    obj_robust = 1.45e-4 * d_sym * qty + calculate_loss_cost(t_sym) * qty + 2.0 * proc_cost.get(wh, 0) * qty

                    impact = obj_robust - obj_det
                    total_impact += impact
                    impact_details.append({
                        't': t, 'wh': wh, 'c': c, 's': s,
                        'qty': qty, 'dist': d_sym, 'dur': t_sym,
                        'obj_det': obj_det, 'obj_robust': obj_robust,
                        'impact': impact
                    })

print(f"  缺失距离的u变量数: {len(impact_details)}")
print(f"  总影响 (鲁棒-确定性 目标系数差): {total_impact:.4f}")
if impact_details:
    impact_details.sort(key=lambda x: -abs(x['impact']))
    print(f"\n  影响最大的前10个:")
    for d in impact_details[:10]:
        print(f"    t={d['t']}, {d['wh']}->{d['c']}({d['s']}), qty={d['qty']:.2f}, "
              f"dist={d['dist']}, dur={d['dur']:.0f}, "
              f"确定性obj={d['obj_det']:.4f}, 鲁棒obj={d['obj_robust']:.4f}, "
              f"差={d['impact']:.4f}")

# === 检查11: z/w变量差异的影响 ===
print("\n" + "=" * 70)
print("检查11: z/w变量差异 (确定性模型有CDC的z/w, 鲁棒模型没有)")
print("=" * 70)

for cdc in cdc_names:
    print(f"  CDC: {cdc}, proc_cost={proc_cost.get(cdc, 0)}")
    print(f"    确定性模型: 有z和w变量, 可获得 -0.8*{proc_cost.get(cdc, 0):.4f} = {-0.8*proc_cost.get(cdc, 0):.4f} 折扣/吨")
    print(f"    鲁棒模型: 无z和w变量, 无折扣")

# === 最终总结 ===
print("\n" + "=" * 70)
print("最终总结: 两个模型的关键差异")
print("=" * 70)
print(f"1. 距离矩阵方向性: 确定性=单向(缺失→0), 鲁棒=对称(缺失→99999)")
print(f"2. 距离过滤: 确定性=无, 鲁棒=dist>5000km过滤")
print(f"3. 缺失距离的u变量: {len(impact_details)}个 (确定性模型中运输成本=0)")
print(f"4. z/w变量: 确定性=含CDC, 鲁棒=仅RDC")
print(f"5. 流量平衡缺失: {skipped_balance}个 (鲁棒模型因f变量缺失)")
print(f"6. 单源约束不完整: {incomplete_single_source}个")
print(f"7. 目标系数差异: {obj_diff_count}个u变量, 总差{obj_diff_total:.4f}")
