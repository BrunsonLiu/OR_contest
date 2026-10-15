"""
直接对比: verify_optimal.py 的解 vs 鲁棒模型的解
找出 140877 vs 79807 的 61070 差距在哪
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import cplex
import pandas as pd
import numpy as np
import time
import json

BASE = str(_REPO_ROOT)

df_wh = pd.read_csv(f'{BASE}/data/raw/df_wh.csv')
df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
df_proc = pd.read_csv(f'{BASE}/data/raw/df_proc.csv')
df_forecast = pd.read_csv(f'{BASE}/results/question3/订单需求量预测结果文件_sota.csv')

dist = {}; dur = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

proc_cost = {}; cap = {}; open_cost = {}
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']
    cap[row['Name']] = row['Capacity']
    open_cost[row['Name']] = row['Opening_fee']

def loss_per_ton(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)

demand = {}
for t_idx, dc in enumerate(forecast_dates):
    demand[t_idx] = {}
    for _, row in df_forecast.iterrows():
        demand[t_idx][(row['Customer'], row['SKU'])] = float(row[dc])

rob_rdcs = ['bei-jing-DC', 'chang-sha-DC', 'chong-qing-DC', 'da-lian-DC',
            'guang-zhou-DC', 'ha-er-bin-DC', 'nan-jing-DC', 'ning-bo-DC',
            'qing-dao-DC', 'tian-jin-DC', 'wu-han-DC', 'xi-an-DC', 'zheng-zhou-DC']

# 用鲁棒模型的方式构建（w是连续变量）
problem = cplex.Cplex()
problem.set_log_stream(None)
problem.set_warning_stream(None)
problem.set_results_stream(None)
problem.objective.set_sense(problem.objective.sense.minimize)
problem.parameters.mip.tolerances.mipgap.set(0.005)
problem.parameters.timelimit.set(600)

vc = 0
vi = {}

# y + open_new
for t in range(T):
    for wh in rob_rdcs:
        vn = f'y_{t}_{wh}'
        problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[vn])
        vi[vn] = vc; vc += 1
        vn = f'open_new_{t}_{wh}'
        problem.variables.add(obj=[open_cost.get(wh,0)], lb=[0], ub=[1], types=['B'], names=[vn])
        vi[vn] = vc; vc += 1

# z (智能采购决策)
for wh in rob_rdcs:
    vn = f'z_{wh}'
    problem.variables.add(obj=[1.5], lb=[0], ub=[1], types=['B'], names=[vn])
    vi[vn] = vc; vc += 1

# w (连续: 智能系统处理量)
for t in range(T):
    for wh in rob_rdcs:
        vn = f'w_{t}_{wh}'
        problem.variables.add(obj=[-0.8*proc_cost.get(wh,0)], lb=[0], ub=[100000], types=['C'], names=[vn])
        vi[vn] = vc; vc += 1

# u
for t in range(T):
    for (c, sku), qty in demand[t].items():
        eligible = [port_cdc] + rob_rdcs if sku == 'im' else [inland_cdc] + rob_rdcs
        for wh in eligible:
            vn = f'u_{t}_{wh}_{c}_{sku}'
            d = dist.get((wh,c),0)
            l = loss_per_ton(dur.get((wh,c),0))
            p = 2.0 * proc_cost.get(wh,0)
            obj = 1.45e-4*d*qty + l*qty + p*qty
            problem.variables.add(obj=[obj], lb=[0], ub=[1], types=['B'], names=[vn])
            vi[vn] = vc; vc += 1

# f
for t in range(T):
    for cdc in cdc_names:
        for rdc in rob_rdcs:
            for sku in ['im','dm']:
                if (sku=='im' and cdc==port_cdc) or (sku=='dm' and cdc==inland_cdc):
                    vn = f'f_{t}_{cdc}_{rdc}_{sku}'
                    d = dist.get((cdc,rdc),0)
                    l = loss_per_ton(dur.get((cdc,rdc),0))
                    p = 2.0 * proc_cost.get(cdc,0)
                    obj = 0.9e-4*d + l + p
                    problem.variables.add(obj=[obj], lb=[0], ub=[cplex.infinity], types=['C'], names=[vn])
                    vi[vn] = vc; vc += 1

# v
for t in range(T):
    for (c, sku), _ in demand[t].items():
        vn = f'v_{t}_{c}_{sku}'
        problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[vn])
        vi[vn] = vc; vc += 1

# 约束 (同verify_optimal + 鲁棒模型的w约束)
# 1. 单源
for t in range(T):
    for (c, sku), _ in demand[t].items():
        eligible = [port_cdc] + rob_rdcs if sku == 'im' else [inland_cdc] + rob_rdcs
        indices = [vi[f'u_{t}_{wh}_{c}_{sku}'] for wh in eligible if f'u_{t}_{wh}_{c}_{sku}' in vi]
        if indices:
            problem.linear_constraints.add(lin_expr=[[indices,[1]*len(indices)]], senses=['E'], rhs=[1])

# 2. u <= y
for t in range(T):
    for (c, sku), _ in demand[t].items():
        eligible = [port_cdc] + rob_rdcs if sku == 'im' else [inland_cdc] + rob_rdcs
        for wh in eligible:
            uv = f'u_{t}_{wh}_{c}_{sku}'
            if uv in vi and wh in rob_rdcs:
                yv = f'y_{t}_{wh}'
                if yv in vi:
                    problem.linear_constraints.add(lin_expr=[[[vi[uv],vi[yv]],[1,-1]]], senses=['L'], rhs=[0])

# 3. 流量平衡
for t in range(T):
    for rdc in rob_rdcs:
        for sku in ['im','dm']:
            cdc = port_cdc if sku=='im' else inland_cdc
            fv = f'f_{t}_{cdc}_{rdc}_{sku}'
            indices = []; values = []
            for (c,s),qty in demand[t].items():
                if s==sku:
                    uv = f'u_{t}_{rdc}_{c}_{sku}'
                    if uv in vi:
                        indices.append(vi[uv]); values.append(qty)
            if fv in vi:
                indices.append(vi[fv]); values.append(-1)
            if indices:
                problem.linear_constraints.add(lin_expr=[[indices,values]], senses=['E'], rhs=[0])

# 4. 容量
for t in range(T):
    for wh in rob_rdcs:
        indices = [vi[f'y_{t}_{wh}']]; values = [-cap.get(wh,5000)]
        for (c,sku),qty in demand[t].items():
            uv = f'u_{t}_{wh}_{c}_{sku}'
            if uv in vi:
                indices.append(vi[uv]); values.append(qty)
        if len(indices)>1:
            problem.linear_constraints.add(lin_expr=[[indices,values]], senses=['L'], rhs=[0])

# 5. 时效
for t in range(T):
    for (c,sku),_ in demand[t].items():
        vv = f'v_{t}_{c}_{sku}'
        if vv not in vi: continue
        eligible = [port_cdc]+rob_rdcs if sku=='im' else [inland_cdc]+rob_rdcs
        for wh in eligible:
            uv = f'u_{t}_{wh}_{c}_{sku}'
            if uv in vi:
                travel = dur.get((wh,c),99999)
                if travel > 600:
                    problem.linear_constraints.add(lin_expr=[[[vi[vv],vi[uv]],[1,-1]]], senses=['G'], rhs=[0])
    total_d = sum(qty for (_,sku),qty in demand[t].items())
    iv = [vi[f'v_{t}_{c}_{sku}'] for (c,sku) in demand[t] if f'v_{t}_{c}_{sku}' in vi]
    dv = [demand[t][(c,sku)] for (c,sku) in demand[t] if f'v_{t}_{c}_{sku}' in vi]
    if iv:
        problem.linear_constraints.add(lin_expr=[[iv,dv]], senses=['G'], rhs=[0.95*total_d])

# 6. 仅开不关
for t in range(1,T):
    for wh in rob_rdcs:
        yc = f'y_{t}_{wh}'; yp = f'y_{t-1}_{wh}'
        if yc in vi and yp in vi:
            problem.linear_constraints.add(lin_expr=[[[vi[yc],vi[yp]],[1,-1]]], senses=['G'], rhs=[0])

# 7. open_new = y - y_prev
for t in range(T):
    for wh in rob_rdcs:
        yv = f'y_{t}_{wh}'; onv = f'open_new_{t}_{wh}'
        if yv in vi and onv in vi:
            if t==0:
                problem.linear_constraints.add(lin_expr=[[[vi[onv],vi[yv]],[1,-1]]], senses=['E'], rhs=[0])
            else:
                yp = f'y_{t-1}_{wh}'
                if yp in vi:
                    problem.linear_constraints.add(lin_expr=[[[vi[onv],vi[yv],vi[yp]],[1,-1,1]]], senses=['E'], rhs=[0])

# 8. z约束
for wh in rob_rdcs:
    if f'z_{wh}' in vi:
        iz = vi[f'z_{wh}']
        for t in range(T):
            wv = f'w_{t}_{wh}'
            if wv in vi:
                # w ≤ z × cap
                problem.linear_constraints.add(lin_expr=[[[vi[wv],iz],[1,-cap.get(wh,100000)]]], senses=['L'], rhs=[0])
                # w ≤ 出库量
                iw = [vi[wv]]; cw = [1.0]
                for (c,sku),qty in demand[t].items():
                    uv = f'u_{t}_{wh}_{c}_{sku}'
                    if uv in vi:
                        iw.append(vi[uv]); cw.append(-qty)
                problem.linear_constraints.add(lin_expr=[[iw,cw]], senses=['L'], rhs=[0])

        # z ≤ Σ y_t
        izy = [vi[f'z_{wh}']]; czy = [1.0]
        for t in range(T):
            yv = f'y_{t}_{wh}'
            if yv in vi:
                izy.append(vi[yv]); czy.append(-1)
        problem.linear_constraints.add(lin_expr=[[izy,czy]], senses=['L'], rhs=[0])

print(f"变量: {vc}")
problem.solve()
status = problem.solution.get_status()
obj = problem.solution.get_objective_value()
print(f"状态: {status}, 目标值: {obj:.2f}")
print(f"鲁棒模型Γ=0%: 79807.10")
print(f"差距: {obj - 79807.10:.2f}")

# 提取成本分解
total_trans_cust = 0; total_trans_wh = 0; total_loss = 0; total_proc = 0
total_open = 0; total_smart = 0; total_discount = 0

for t in range(T):
    for (c,sku),qty in demand[t].items():
        eligible = [port_cdc]+rob_rdcs if sku=='im' else [inland_cdc]+rob_rdcs
        for wh in eligible:
            uv = f'u_{t}_{wh}_{c}_{sku}'
            if uv in vi and problem.solution.get_values(vi[uv]) > 0.5:
                d = dist.get((wh,c),0)
                t_min = dur.get((wh,c),0)
                total_trans_cust += 1.45e-4*d*qty
                total_loss += loss_per_ton(t_min)*qty
                total_proc += 2.0*proc_cost.get(wh,0)*qty

    for cdc in cdc_names:
        for rdc in rob_rdcs:
            for sku in ['im','dm']:
                if (sku=='im' and cdc==port_cdc) or (sku=='dm' and cdc==inland_cdc):
                    fv = f'f_{t}_{cdc}_{rdc}_{sku}'
                    if fv in vi:
                        fqty = problem.solution.get_values(vi[fv])
                        if fqty > 0.01:
                            d = dist.get((cdc,rdc),0)
                            t_min = dur.get((cdc,rdc),0)
                            total_trans_wh += 0.9e-4*d*fqty
                            total_loss += loss_per_ton(t_min)*fqty
                            total_proc += 2.0*proc_cost.get(cdc,0)*fqty

    for wh in rob_rdcs:
        wv = f'w_{t}_{wh}'
        if wv in vi:
            wval = problem.solution.get_values(vi[wv])
            total_discount += 0.8*proc_cost.get(wh,0)*wval

        onv = f'open_new_{t}_{wh}'
        if onv in vi:
            if problem.solution.get_values(vi[onv]) > 0.5:
                total_open += open_cost.get(wh,0)

    for wh in rob_rdcs:
        zv = f'z_{wh}'
        if zv in vi:
            if problem.solution.get_values(vi[zv]) > 0.5:
                total_smart += 1.5

print(f"\n成本分解:")
print(f"  运输(门): {total_trans_cust:.2f}")
print(f"  运输(仓): {total_trans_wh:.2f}")
print(f"  处置费:   {total_proc:.2f}")
print(f"  损耗:     {total_loss:.2f}")
print(f"  开仓费:   {total_open:.2f}")
print(f"  智能费:   {total_smart:.2f}")
print(f"  智能折扣: -{total_discount:.2f}")
print(f"  合计:     {total_trans_cust+total_trans_wh+total_proc+total_loss+total_open+total_smart-total_discount:.2f}")
