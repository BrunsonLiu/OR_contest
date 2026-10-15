"""
直接对比: 用鲁棒模型的CPLEX解，手动算成本
找出 141072 vs 79807 的差距来源
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import cplex, pandas as pd, numpy as np, json, time

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

def loss_per_ton(m):
    return 0.0 if m <= 500 else 0.2*(m-500)**2/10000

cdc_names = df_wh[df_wh['Type']=='CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type']=='RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
customer_cities = pd.read_csv(f'{BASE}/data/raw/df_customer.csv')['Name'].tolist()

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer','SKU']]
T = len(forecast_dates)

demand = {}
for t, dc in enumerate(forecast_dates):
    demand[t] = {}
    for _, row in df_forecast.iterrows():
        demand[t][(row['Customer'], row['SKU'])] = float(row[dc])

# ===== 检查1: RDC名字是否匹配 df_proc =====
print("=" * 70)
print("检查1: RDC名字匹配")
print("=" * 70)
for wh in rdc_names:
    c = cap.get(wh, 'MISSING')
    p = proc_cost.get(wh, 'MISSING')
    o = open_cost.get(wh, 'MISSING')
    if c == 'MISSING':
        print(f"  ❌ {wh}: cap=MISSING!")
    if p == 'MISSING':
        print(f"  ❌ {wh}: proc=MISSING!")
    if o == 'MISSING':
        print(f"  ❌ {wh}: open=MISSING!")

print(f"  全部匹配: {all(wh in cap for wh in rdc_names)}")

# ===== 检查2: dist/dur 缺失对 =====
print("\n" + "=" * 70)
print("检查2: dist/dur 缺失对数量")
print("=" * 70)
all_wh = cdc_names + rdc_names
missing_dist = 0
missing_dur = 0
for wh in all_wh:
    for c in customer_cities:
        if (wh, c) not in dist:
            missing_dist += 1
        if (wh, c) not in dur:
            missing_dur += 1
print(f"  缺失dist对: {missing_dist}")
print(f"  缺失dur对: {missing_dur}")

# ===== 检查3: 用鲁棒模型完全相同的逻辑构建 =====
print("\n" + "=" * 70)
print("检查3: 完全复制鲁棒模型逻辑 (Gamma=0)")
print("=" * 70)

cdc_sku = {'gang-kou-CDC': 'im', 'nei-lu-CDC': 'dm'}
sku_cdc = {'im': 'gang-kou-CDC', 'dm': 'nei-lu-CDC'}
skus = ['im', 'dm']

problem = cplex.Cplex()
problem.set_log_stream(None)
problem.set_warning_stream(None)
problem.set_results_stream(None)
problem.objective.set_sense(problem.objective.sense.minimize)
problem.parameters.mip.tolerances.mipgap.set(0.005)
problem.parameters.timelimit.set(600)

vc = 0
vi = {}

# y
for t in range(T):
    for wh in rdc_names:
        vn = f'y_{t}_{wh}'
        problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[vn])
        vi[vn] = vc; vc += 1

# open_new
for t in range(T):
    for wh in rdc_names:
        vn = f'open_new_{t}_{wh}'
        problem.variables.add(obj=[open_cost.get(wh,0)], lb=[0], ub=[1], types=['B'], names=[vn])
        vi[vn] = vc; vc += 1

# z
for wh in rdc_names:
    vn = f'z_{wh}'
    problem.variables.add(obj=[1.5], lb=[0], ub=[1], types=['B'], names=[vn])
    vi[vn] = vc; vc += 1

# w (连续)
for t in range(T):
    for wh in rdc_names:
        vn = f'w_{t}_{wh}'
        problem.variables.add(obj=[0], lb=[0], ub=[100000], types=['C'], names=[vn])
        vi[vn] = vc; vc += 1

# u (与鲁棒模型完全相同: all_wh_names, 无SKU限制, dist>5000过滤)
for t in range(T):
    for wh in all_wh:
        for c in customer_cities:
            for s in skus:
                if (c, s) not in demand[t]:
                    continue
                d_km = dist.get((wh, c), 99999)
                if d_km > 5000:
                    continue
                vn = f'u_{t}_{wh}_{c}_{s}'
                problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[vn])
                vi[vn] = vc; vc += 1

# f
for t in range(T):
    for cdc in cdc_names:
        s = cdc_sku[cdc]
        for rdc in rdc_names:
            d_km = dist.get((cdc, rdc), 99999)
            if d_km > 5000:
                continue
            vn = f'f_{t}_{cdc}_{rdc}_{s}'
            problem.variables.add(obj=[0], lb=[0], ub=[cplex.infinity], types=['C'], names=[vn])
            vi[vn] = vc; vc += 1

# v
for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand[t]:
                continue
            vn = f'v_{t}_{c}_{s}'
            problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[vn])
            vi[vn] = vc; vc += 1

print(f"  变量数: {vc}")

# ===== 约束 =====
# 1. 单源
for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand[t]:
                continue
            indices = []
            for wh in all_wh:
                uv = f'u_{t}_{wh}_{c}_{s}'
                if uv in vi:
                    indices.append(vi[uv])
            if indices:
                problem.linear_constraints.add(lin_expr=[[indices,[1]*len(indices)]], senses=['E'], rhs=[1])

# 2. u <= y (仅RDC)
for t in range(T):
    for wh in rdc_names:
        for c in customer_cities:
            for s in skus:
                uv = f'u_{t}_{wh}_{c}_{s}'
                yv = f'y_{t}_{wh}'
                if uv in vi and yv in vi:
                    problem.linear_constraints.add(lin_expr=[[[vi[uv],vi[yv]],[1,-1]]], senses=['L'], rhs=[0])

# 3. 流量平衡 (与鲁棒模型相同)
for t in range(T):
    for rdc in rdc_names:
        for s in skus:
            cdc = sku_cdc[s]
            fv = f'f_{t}_{cdc}_{rdc}_{s}'
            indices = []; values = []
            for c in customer_cities:
                uv = f'u_{t}_{rdc}_{c}_{s}'
                if uv in vi and (c, s) in demand[t]:
                    indices.append(vi[uv])
                    values.append(demand[t][(c, s)])
            if fv in vi:
                indices.append(vi[fv])
                values.append(-1)
            if indices:
                problem.linear_constraints.add(lin_expr=[[indices,values]], senses=['E'], rhs=[0])

# 4. 容量 (合并im+dm, 与鲁棒模型相同)
for t in range(T):
    for wh in rdc_names:
        indices = [vi[f'y_{t}_{wh}']]
        values = [-cap.get(wh, 5000)]
        for c in customer_cities:
            for s in skus:
                uv = f'u_{t}_{wh}_{c}_{s}'
                if uv in vi and (c, s) in demand[t]:
                    indices.append(vi[uv])
                    values.append(demand[t][(c, s)])
        if len(indices) > 1:
            problem.linear_constraints.add(lin_expr=[[indices,values]], senses=['L'], rhs=[0])

# 5. 时效
for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand[t]:
                continue
            vv = f'v_{t}_{c}_{s}'
            if vv not in vi:
                continue
            for wh in all_wh:
                uv = f'u_{t}_{wh}_{c}_{s}'
                if uv in vi:
                    travel = dur.get((wh, c), 99999)
                    if travel > 600:
                        problem.linear_constraints.add(lin_expr=[[[vi[vv],vi[uv]],[1,-1]]], senses=['G'], rhs=[0])
    
    total_d = sum(demand[t].values())
    iv = [vi[f'v_{t}_{c}_{s}'] for (c,s) in demand[t] if f'v_{t}_{c}_{s}' in vi]
    dv = [demand[t][(c,s)] for (c,s) in demand[t] if f'v_{t}_{c}_{s}' in vi]
    if iv:
        problem.linear_constraints.add(lin_expr=[[iv,dv]], senses=['G'], rhs=[0.95*total_d])

# 6. 仅开不关
for t in range(1, T):
    for wh in rdc_names:
        yc = f'y_{t}_{wh}'; yp = f'y_{t-1}_{wh}'
        if yc in vi and yp in vi:
            problem.linear_constraints.add(lin_expr=[[[vi[yc],vi[yp]],[1,-1]]], senses=['G'], rhs=[0])

# 7. open_new
for t in range(T):
    for wh in rdc_names:
        yv = f'y_{t}_{wh}'; onv = f'open_new_{t}_{wh}'
        if yv not in vi or onv not in vi:
            continue
        if t == 0:
            problem.linear_constraints.add(lin_expr=[[[vi[onv],vi[yv]],[1,-1]]], senses=['E'], rhs=[0])
        else:
            yp = f'y_{t-1}_{wh}'
            if yp in vi:
                problem.linear_constraints.add(lin_expr=[[[vi[onv],vi[yv],vi[yp]],[1,-1,1]]], senses=['E'], rhs=[0])

# 8. z约束
for wh in rdc_names:
    if f'z_{wh}' not in vi:
        continue
    iz = vi[f'z_{wh}']
    for t in range(T):
        wv = f'w_{t}_{wh}'
        if wv in vi:
            problem.linear_constraints.add(lin_expr=[[[vi[wv],iz],[1,-cap.get(wh,100000)]]], senses=['L'], rhs=[0])
            iw = [vi[wv]]; cw = [1.0]
            for c in customer_cities:
                for s in skus:
                    uv = f'u_{t}_{wh}_{c}_{s}'
                    if uv in vi and (c, s) in demand[t]:
                        iw.append(vi[uv]); cw.append(-demand[t][(c,s)])
            problem.linear_constraints.add(lin_expr=[[iw,cw]], senses=['L'], rhs=[0])
    izy = [iz]; czy = [1.0]
    for t in range(T):
        yv = f'y_{t}_{wh}'
        if yv in vi:
            izy.append(vi[yv]); czy.append(-1)
    problem.linear_constraints.add(lin_expr=[[izy,czy]], senses=['L'], rhs=[0])

# ===== 设置目标系数 (与鲁棒模型完全相同) =====
obj_contributions = {}

for t in range(T):
    for wh in all_wh:
        for c in customer_cities:
            for s in skus:
                uv = f'u_{t}_{wh}_{c}_{s}'
                if uv not in vi or (c, s) not in demand[t]:
                    continue
                qty = demand[t][(c, s)]
                d_val = dist.get((wh, c), 99999)
                l_val = loss_per_ton(dur.get((wh, c), 10000))
                p_val = 2.0 * proc_cost.get(wh, 0.0)
                obj_val = 1.45e-4 * d_val * qty + l_val * qty + p_val * qty
                obj_contributions[uv] = obj_contributions.get(uv, 0) + obj_val

    for cdc in cdc_names:
        s = cdc_sku[cdc]
        for rdc in rdc_names:
            fv = f'f_{t}_{cdc}_{rdc}_{s}'
            if fv not in vi:
                continue
            d_val = dist.get((cdc, rdc), 99999)
            l_val = loss_per_ton(dur.get((cdc, rdc), 10000))
            p_val = 2.0 * proc_cost.get(cdc, 0.0)
            obj_val = 0.9e-4 * d_val + l_val + p_val
            obj_contributions[fv] = obj_contributions.get(fv, 0) + obj_val

    for wh in rdc_names:
        wv = f'w_{t}_{wh}'
        if wv in vi:
            obj_contributions[wv] = obj_contributions.get(wv, 0) - 0.8 * proc_cost.get(wh, 0.0)

for vn, coeff in obj_contributions.items():
    if vn in vi:
        problem.objective.set_linear(vi[vn], coeff)

print(f"  目标系数已设置: {len(obj_contributions)} 个变量")

t0 = time.time()
problem.solve()
solve_time = time.time() - t0

status = problem.solution.get_status()
obj = problem.solution.get_objective_value()

open_rdcs = set()
for t in range(T):
    for wh in rdc_names:
        if problem.solution.get_values(vi[f'y_{t}_{wh}']) > 0.5:
            open_rdcs.add(wh)

print(f"\n  求解时间: {solve_time:.1f}s")
print(f"  状态: {status}")
print(f"  目标值: {obj:.2f}")
print(f"  开仓数: {len(open_rdcs)}")
print(f"  仓库: {sorted(open_rdcs)}")
print(f"\n  鲁棒模型Γ=0%: 79807.10")
print(f"  差距: {obj - 79807.10:.2f}")
