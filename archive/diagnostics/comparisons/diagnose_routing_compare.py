from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import numpy as np
import cplex
import os, sys, io, json

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = str(_REPO_ROOT)
INPUT_DIR = os.path.join(BASE_DIR, 'data/raw')

df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))
df_wh = pd.read_csv(os.path.join(INPUT_DIR, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_demand = pd.read_csv(os.path.join(BASE_DIR, 'results/question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
customer_cities = list(df_customer['Name'])
all_wh = cdc_names + rdc_names

cap = {}
open_cost = {}
proc_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    open_cost[row['Name']] = row['Opening_fee']
    proc_cost[row['Name']] = row['Processing_fee']

dist = {}
dur = {}
for _, row in df_matrix.iterrows():
    dist[(row['From'], row['To'])] = row['Distance']
    dist[(row['To'], row['From'])] = row['Distance']
    dur[(row['From'], row['To'])] = row['Duration']
    dur[(row['To'], row['From'])] = row['Duration']

def calc_loss(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

loss_cost = {(f, t): calc_loss(dur[(f, t)]) for f, t in dur.keys()}

periods = df_demand.columns[2:]
T = len(periods)
demand = {}
for t_idx, period in enumerate(periods):
    demand[t_idx] = {}
    for _, row in df_demand.iterrows():
        demand[t_idx][(row['Customer'], row['SKU'])] = row[period]

print("Loading deterministic model solution...")
det_results_dir = os.path.join(BASE_DIR, 'results/question4')
det_routing = {}
det_obj = None

problem = cplex.Cplex()
problem.objective.set_sense(problem.objective.sense.minimize)
problem.parameters.mip.tolerances.mipgap.set(0.005)
problem.parameters.timelimit.set(1800)
problem.set_log_stream(None)
problem.set_error_stream(None)
problem.set_warning_stream(None)
problem.set_results_stream(None)

vi = {}
vc = 0

for t in range(T):
    for wh in all_wh:
        lb = 1.0 if wh in cdc_names else 0.0
        problem.variables.add(obj=[0], lb=[lb], ub=[1], types=['B'], names=[f'y_{t}_{wh}'])
        vi[f'y_{t}_{wh}'] = vc; vc += 1

for wh in all_wh:
    problem.variables.add(obj=[1.5], lb=[0], ub=[1], types=['B'], names=[f'z_{wh}'])
    vi[f'z_{wh}'] = vc; vc += 1

for t in range(T):
    for (store, sku), qty in demand[t].items():
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            d = dist.get((wh, store), 0)
            tc = 1.45e-4 * d * qty
            lc = loss_cost.get((wh, store), 0) * qty
            pc = 2.0 * proc_cost.get(wh, 0) * qty
            problem.variables.add(obj=[tc+lc+pc], lb=[0], ub=[1], types=['B'], names=[f'u_{t}_{wh}_{store}_{sku}'])
            vi[f'u_{t}_{wh}_{store}_{sku}'] = vc; vc += 1

for t in range(T):
    for cdc in cdc_names:
        for rdc in rdc_names:
            for sku in ['im', 'dm']:
                if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                    d = dist.get((cdc, rdc), 0)
                    tc = 0.9e-4 * d
                    lc = loss_cost.get((cdc, rdc), 0)
                    pc = 2.0 * proc_cost.get(cdc, 0)
                    problem.variables.add(obj=[tc+lc+pc], lb=[0], ub=[100000], types=['C'], names=[f'f_{t}_{cdc}_{rdc}_{sku}'])
                    vi[f'f_{t}_{cdc}_{rdc}_{sku}'] = vc; vc += 1

for t in range(T):
    for (store, sku), _ in demand[t].items():
        problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[f'v_{t}_{store}_{sku}'])
        vi[f'v_{t}_{store}_{sku}'] = vc; vc += 1

for t in range(T):
    for wh in all_wh:
        problem.variables.add(obj=[-0.8*proc_cost.get(wh,0)], lb=[0], ub=[100000], types=['C'], names=[f'w_{t}_{wh}'])
        vi[f'w_{t}_{wh}'] = vc; vc += 1

for t in range(T):
    for wh in rdc_names:
        problem.variables.add(obj=[open_cost.get(wh,0)], lb=[0], ub=[1], types=['B'], names=[f'on_{t}_{wh}'])
        vi[f'on_{t}_{wh}'] = vc; vc += 1

print(f"Det model: {vc} variables")

# Constraints (simplified - just the essential ones)
# Monotonic
for wh in rdc_names:
    for t in range(1, T):
        problem.linear_constraints.add(lin_expr=[[[vi[f'y_{t}_{wh}'], vi[f'y_{t-1}_{wh}']], [1, -1]]], senses=['G'], rhs=[0])

# Single source
for t in range(T):
    for (store, sku), _ in demand[t].items():
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        idx = [vi[f'u_{t}_{wh}_{store}_{sku}'] for wh in eligible if f'u_{t}_{wh}_{store}_{sku}' in vi]
        if idx:
            problem.linear_constraints.add(lin_expr=[[idx, [1]*len(idx)]], senses=['E'], rhs=[1])

# u <= y
for t in range(T):
    for (store, sku), _ in demand[t].items():
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            uk = f'u_{t}_{wh}_{store}_{sku}'
            yk = f'y_{t}_{wh}'
            if uk in vi and yk in vi:
                problem.linear_constraints.add(lin_expr=[[[vi[uk], vi[yk]], [1, -1]]], senses=['L'], rhs=[0])

# Flow balance
for t in range(T):
    for rdc in rdc_names:
        for sku in ['im', 'dm']:
            cdc = port_cdc if sku == 'im' else inland_cdc
            fk = f'f_{t}_{cdc}_{rdc}_{sku}'
            idx = []
            val = []
            for (store, s), qty in demand[t].items():
                if s == sku:
                    uk = f'u_{t}_{rdc}_{store}_{sku}'
                    if uk in vi:
                        idx.append(vi[uk]); val.append(qty)
            if fk in vi:
                idx.append(vi[fk]); val.append(-1.0)
            if idx:
                problem.linear_constraints.add(lin_expr=[[idx, val]], senses=['E'], rhs=[0])

# Capacity
for t in range(T):
    for wh in all_wh:
        yk = f'y_{t}_{wh}'
        idx = [vi[yk]]
        val = [-cap.get(wh, 0)]
        for (store, sku), qty in demand[t].items():
            uk = f'u_{t}_{wh}_{store}_{sku}'
            if uk in vi:
                idx.append(vi[uk]); val.append(qty)
        if wh in cdc_names:
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (sku == 'im' and wh == port_cdc) or (sku == 'dm' and wh == inland_cdc):
                        fk = f'f_{t}_{wh}_{rdc}_{sku}'
                        if fk in vi:
                            idx.append(vi[fk]); val.append(1.0)
        problem.linear_constraints.add(lin_expr=[[idx, val]], senses=['L'], rhs=[0])

# Timeliness
for t in range(T):
    for (store, sku), _ in demand[t].items():
        vk = f'v_{t}_{store}_{sku}'
        if vk not in vi: continue
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            uk = f'u_{t}_{wh}_{store}_{sku}'
            if uk in vi:
                tt = dur.get((wh, store), 99999)
                if tt <= 600:
                    problem.linear_constraints.add(lin_expr=[[[vi[vk], vi[uk]], [-1, 1]]], senses=['L'], rhs=[0])
                else:
                    problem.linear_constraints.add(lin_expr=[[[vi[vk], vi[uk]], [1, 1]]], senses=['L'], rhs=[1])

    total_d = sum(qty for (store, sku), qty in demand[t].items())
    idx = [vi[f'v_{t}_{store}_{sku}'] for (store, sku), qty in demand[t].items() if f'v_{t}_{store}_{sku}' in vi]
    val = [qty for (store, sku), qty in demand[t].items() if f'v_{t}_{store}_{sku}' in vi]
    if idx:
        problem.linear_constraints.add(lin_expr=[[idx, val]], senses=['G'], rhs=[0.95*total_d])

# z <= sum(y)
for wh in all_wh:
    idx = [vi[f'z_{wh}']] + [vi[f'y_{t}_{wh}'] for t in range(T)]
    val = [1] + [-1]*T
    problem.linear_constraints.add(lin_expr=[[idx, val]], senses=['L'], rhs=[0])

# w constraints
for t in range(T):
    for wh in all_wh:
        wk = f'w_{t}_{wh}'
        zk = f'z_{wh}'
        idx1 = [vi[wk]]
        val1 = [1.0]
        for (store, sku), qty in demand[t].items():
            uk = f'u_{t}_{wh}_{store}_{sku}'
            if uk in vi:
                idx1.append(vi[uk]); val1.append(-qty)
        if wh in cdc_names:
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (sku == 'im' and wh == port_cdc) or (sku == 'dm' and wh == inland_cdc):
                        fk = f'f_{t}_{wh}_{rdc}_{sku}'
                        if fk in vi:
                            idx1.append(vi[fk]); val1.append(-1.0)
        problem.linear_constraints.add(lin_expr=[[idx1, val1]], senses=['L'], rhs=[0])
        problem.linear_constraints.add(lin_expr=[[[vi[wk], vi[zk]], [1, -cap.get(wh, 100000)]]], senses=['L'], rhs=[0])

# Opening logic
for wh in rdc_names:
    problem.linear_constraints.add(lin_expr=[[[vi[f'on_0_{wh}'], vi[f'y_0_{wh}']], [1, -1]]], senses=['L'], rhs=[0])
    problem.linear_constraints.add(lin_expr=[[[vi[f'on_0_{wh}'], vi[f'y_0_{wh}']], [-1, 1]]], senses=['L'], rhs=[0])
    for t in range(1, T):
        problem.linear_constraints.add(lin_expr=[[[vi[f'on_{t}_{wh}'], vi[f'y_{t}_{wh}']], [1, -1]]], senses=['L'], rhs=[0])
        problem.linear_constraints.add(lin_expr=[[[vi[f'on_{t}_{wh}'], vi[f'y_{t-1}_{wh}']], [1, 1]]], senses=['L'], rhs=[1])
        problem.linear_constraints.add(lin_expr=[[[vi[f'on_{t}_{wh}'], vi[f'y_{t}_{wh}'], vi[f'y_{t-1}_{wh}']], [-1, 1, -1]]], senses=['L'], rhs=[0])

print("Solving deterministic model...")
problem.solve()
det_obj = problem.solution.get_objective_value()
det_sol = problem.solution.get_values()
print(f"Det objective: {det_obj:.2f}")

# Extract routing
det_routing = {}
for t in range(T):
    for (store, sku), qty in demand[t].items():
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            uk = f'u_{t}_{wh}_{store}_{sku}'
            if uk in vi and det_sol[vi[uk]] > 0.5:
                det_routing[(t, store, sku)] = wh

# Extract transfer
det_transfer = {}
for t in range(T):
    for cdc in cdc_names:
        for rdc in rdc_names:
            for sku in ['im', 'dm']:
                if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                    fk = f'f_{t}_{cdc}_{rdc}_{sku}'
                    if fk in vi:
                        fqty = det_sol[vi[fk]]
                        if fqty > 0.01:
                            det_transfer[(t, cdc, rdc, sku)] = fqty

del problem

print("\n" + "=" * 80)
print("Now building robust model (Gamma=0%)...")
print("=" * 80)

sys.path.insert(0, BASE_DIR)
from src.solvers.question4.solve_problem4_robust import build_and_solve_robust

robust_result = build_and_solve_robust(0.0)

print(f"\nRobust objective (Gamma=0%): {robust_result['objective']:.2f}")
print(f"Det objective: {det_obj:.2f}")
print(f"Gap: {det_obj - robust_result['objective']:.2f} ({(det_obj - robust_result['objective'])/det_obj*100:.2f}%)")

print("\n" + "=" * 80)
print("Cost breakdown comparison")
print("=" * 80)
print(f"{'Item':<25} {'Det':>12} {'Robust':>12} {'Diff':>12}")
print("-" * 65)

det_loss = sum(loss_cost.get((det_routing.get((t,store,sku), ''), store), 0) * qty 
               for t in range(T) for (store, sku), qty in demand[t].items() if (t,store,sku) in det_routing)
det_trans_c = sum(1.45e-4 * dist.get((det_routing[(t,store,sku)], store), 0) * qty
                  for t in range(T) for (store, sku), qty in demand[t].items() if (t,store,sku) in det_routing)
det_trans_w = sum(0.9e-4 * dist.get((cdc, rdc), 0) * fqty 
                  for (t, cdc, rdc, sku), fqty in det_transfer.items())

print(f"{'Loss':<25} {det_loss:>12.2f} {robust_result['loss_cost']:>12.2f} {det_loss-robust_result['loss_cost']:>12.2f}")
print(f"{'Transport (cust)':<25} {det_trans_c:>12.2f} {robust_result['transport_cost_customer']:>12.2f} {det_trans_c-robust_result['transport_cost_customer']:>12.2f}")
print(f"{'Transport (wh)':<25} {det_trans_w:>12.2f} {robust_result['transport_cost_warehouse']:>12.2f} {det_trans_w-robust_result['transport_cost_warehouse']:>12.2f}")
