# -*- coding: utf-8 -*-
"""
诊断脚本：对比确定性模型和鲁棒模型的约束差异，定位3倍差距根源
重点检查：跨SKU分配bug（鲁棒模型允许im需求由inland_cdc服务）
"""
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

cdc_names = list(df_wh[df_wh['Type'] == 'CDC']['Name'])
rdc_names = list(df_wh[df_wh['Type'] == 'RDC']['Name'])
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
customer_cities = list(df_customer['Name'])

dist_matrix = {}
dur_matrix = {}
for _, row in df_matrix.iterrows():
    o, d = row['From'], row['To']
    dist_matrix[(o, d)] = row['Distance']
    dist_matrix[(d, o)] = row['Distance']
    dur_matrix[(o, d)] = row['Duration']
    dur_matrix[(d, o)] = row['Duration']

LOSS_THRESHOLD = 500.0
def calc_loss(minutes):
    if minutes <= LOSS_THRESHOLD:
        return 0.0
    return 0.2 * (minutes - LOSS_THRESHOLD) ** 2 / 10000.0

print("=" * 80)
print("诊断：确定性模型 vs 鲁棒模型 约束差异分析")
print("=" * 80)

# ====== Bug 1: 跨SKU分配 ======
print("\n" + "=" * 80)
print("BUG 1: 鲁棒模型允许跨SKU分配（im需求可由inland_cdc服务，dm需求可由port_cdc服务）")
print("=" * 80)

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)

demand_nominal = {}
for t_idx, date_col in enumerate(forecast_dates):
    demand_nominal[t_idx] = {}
    for _, row in df_forecast.iterrows():
        city = row['Customer']
        sku = row['SKU']
        qty = float(row[date_col])
        demand_nominal[t_idx][(city, sku)] = qty

total_im_demand = sum(sum(qty for (c, s), qty in demand_nominal[t].items() if s == 'im') for t in range(T))
total_dm_demand = sum(sum(qty for (c, s), qty in demand_nominal[t].items() if s == 'dm') for t in range(T))
print(f"  7天总im需求: {total_im_demand:.1f} 吨")
print(f"  7天总dm需求: {total_dm_demand:.1f} 吨")

# 确定性模型的u变量：im只能由port_cdc+RDC服务
# 鲁棒模型的u变量：im可以由port_cdc+inland_cdc+RDC服务
cross_assign_saving_im = 0
cross_assign_saving_dm = 0
im_cities_far_from_port = []
dm_cities_far_from_inland = []

for c in customer_cities:
    for s in ['im', 'dm']:
        if (c, s) not in demand_nominal[0]:
            continue
        total_qty = sum(demand_nominal[t].get((c, s), 0) for t in range(T))
        if total_qty < 0.01:
            continue

        if s == 'im':
            port_dur = dur_matrix.get((port_cdc, c), 99999)
            inland_dur = dur_matrix.get((inland_cdc, c), 99999)
            port_loss = calc_loss(port_dur)
            inland_loss = calc_loss(inland_dur)
            saving = (port_loss - inland_loss) * total_qty
            if saving > 0 and inland_dur < port_dur:
                cross_assign_saving_im += saving
                if port_loss > 1.0:
                    im_cities_far_from_port.append({
                        'city': c, 'qty': total_qty,
                        'port_dur': port_dur, 'inland_dur': inland_dur,
                        'port_loss': port_loss, 'inland_loss': inland_loss,
                        'saving': saving
                    })
        else:
            inland_dur = dur_matrix.get((inland_cdc, c), 99999)
            port_dur = dur_matrix.get((port_cdc, c), 99999)
            inland_loss = calc_loss(inland_dur)
            port_loss = calc_loss(port_dur)
            saving = (inland_loss - port_loss) * total_qty
            if saving > 0 and port_dur < inland_dur:
                cross_assign_saving_dm += saving
                if inland_loss > 1.0:
                    dm_cities_far_from_inland.append({
                        'city': c, 'qty': total_qty,
                        'inland_dur': inland_dur, 'port_dur': port_dur,
                        'inland_loss': inland_loss, 'port_loss': port_loss,
                        'saving': saving
                    })

print(f"\n  im需求跨分配到inland_cdc的理论节省: {cross_assign_saving_im:.1f} 万元")
print(f"  dm需求跨分配到port_cdc的理论节省: {cross_assign_saving_dm:.1f} 万元")
print(f"  跨分配总理论节省: {cross_assign_saving_im + cross_assign_saving_dm:.1f} 万元")
print(f"  实际损耗差距: {219875.88 - 69077.84:.1f} 万元")

print(f"\n  --- im需求远离port_cdc的城市 TOP 15 ---")
im_cities_far_from_port.sort(key=lambda x: x['saving'], reverse=True)
for item in im_cities_far_from_port[:15]:
    print(f"    {item['city']:20s}: qty={item['qty']:8.1f}t, "
          f"port={item['port_dur']:5d}min(loss={item['port_loss']:.2f}), "
          f"inland={item['inland_dur']:5d}min(loss={item['inland_loss']:.2f}), "
          f"saving={item['saving']:.1f}万")

print(f"\n  --- dm需求远离inland_cdc的城市 TOP 15 ---")
dm_cities_far_from_inland.sort(key=lambda x: x['saving'], reverse=True)
for item in dm_cities_far_from_inland[:15]:
    print(f"    {item['city']:20s}: qty={item['qty']:8.1f}t, "
          f"inland={item['inland_dur']:5d}min(loss={item['inland_loss']:.2f}), "
          f"port={item['port_dur']:5d}min(loss={item['port_loss']:.2f}), "
          f"saving={item['saving']:.1f}万")

# ====== Bug 2: CDC→RDC 二次损耗 ======
print("\n" + "=" * 80)
print("BUG 1 影响：CDC→RDC二次损耗分析")
print("=" * 80)

cdc_rdc_loss_im = {}
cdc_rdc_loss_dm = {}
for rdc in rdc_names:
    port_dur = dur_matrix.get((port_cdc, rdc), 99999)
    inland_dur = dur_matrix.get((inland_cdc, rdc), 99999)
    cdc_rdc_loss_im[rdc] = calc_loss(port_dur)
    cdc_rdc_loss_dm[rdc] = calc_loss(inland_dur)

print(f"\n  --- gang-kou-CDC → RDC 损耗(im调拨段) ---")
for rdc in sorted(rdc_names, key=lambda x: cdc_rdc_loss_im[x], reverse=True)[:10]:
    dur = dur_matrix.get((port_cdc, rdc), 99999)
    print(f"    → {rdc:20s}: {dur:5d}min, loss={cdc_rdc_loss_im[rdc]:.4f}万/吨")

print(f"\n  --- nei-lu-CDC → RDC 损耗(dm调拨段) ---")
for rdc in sorted(rdc_names, key=lambda x: cdc_rdc_loss_dm[x], reverse=True)[:10]:
    dur = dur_matrix.get((inland_cdc, rdc), 99999)
    print(f"    → {rdc:20s}: {dur:5d}min, loss={cdc_rdc_loss_dm[rdc]:.4f}万/吨")

# ====== Bug 3: 确定性模型dist字典方向检查 ======
print("\n" + "=" * 80)
print("检查：确定性模型的dist字典是否缺少方向")
print("=" * 80)

dist_oneway = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
missing_count = 0
for wh in cdc_names + rdc_names:
    for c in customer_cities:
        if (wh, c) not in dist_oneway:
            missing_count += 1
            if missing_count <= 5:
                print(f"  缺少 dist[({wh}, {c})]!")
print(f"  总共缺少 (wh→city) 方向: {missing_count} 条")

missing_cdc_rdc = 0
for cdc in cdc_names:
    for rdc in rdc_names:
        if (cdc, rdc) not in dist_oneway:
            missing_cdc_rdc += 1
            print(f"  缺少 dist[({cdc}, {rdc})]!")
print(f"  总共缺少 (cdc→rdc) 方向: {missing_cdc_rdc} 条")

# ====== 关键结论 ======
print("\n" + "=" * 80)
print("关键结论")
print("=" * 80)
print(f"""
  1. 鲁棒模型的u变量创建没有限制SKU-CDC对应关系：
     - 确定性模型：im需求只能由 gang-kou-CDC + RDC 服务
     - 鲁棒模型：im需求可以由 gang-kou-CDC + nei-lu-CDC + RDC 服务（BUG！）
     
  2. 这导致鲁棒模型可以把im需求分配给nei-lu-CDC（内陆CDC），
     而nei-lu-CDC距离很多内陆城市更近，损耗大幅降低。
     
  3. 跨分配理论节省: {cross_assign_saving_im + cross_assign_saving_dm:.1f} 万元
     实际损耗差距: {219875.88 - 69077.84:.1f} 万元
     
  4. 此外，跨分配的需求不计入CDC容量约束，相当于CDC容量无限。
  
  5. 修复方案：在鲁棒模型中，u变量创建时限制：
     - im需求：只能由 gang-kou-CDC + RDC 服务
     - dm需求：只能由 nei-lu-CDC + RDC 服务
""")
