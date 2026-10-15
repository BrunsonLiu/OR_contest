from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import cplex
import os
import numpy as np
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

input_dir = os.path.join(str(_REPO_ROOT), 'data/raw')
df_customer = pd.read_csv(os.path.join(input_dir, 'df_customer.csv'))
df_wh = pd.read_csv(os.path.join(input_dir, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(input_dir, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(input_dir, 'df_proc.csv'))
df_demand_multi = pd.read_csv(os.path.join(str(_REPO_ROOT), 'results/question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
dist = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
time_matrix = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}

cap = {}; open_cost = {}; proc_cost = {}
proc_dict = {}
for _, row in df_proc.iterrows():
    proc_dict[row['Name']] = {'Capacity': row['Capacity'], 'Opening_fee': row['Opening_fee'], 'Processing_fee': row['Processing_fee']}
for _, row in df_wh.iterrows():
    wh_name = row['Name']
    wh_type = row['Type']
    if wh_type in ['RDC', 'CDC'] and wh_name in proc_dict:
        cap[wh_name] = proc_dict[wh_name]['Capacity']
        open_cost[wh_name] = proc_dict[wh_name]['Opening_fee']
        proc_cost[wh_name] = proc_dict[wh_name]['Processing_fee']

customers = df_customer['Name'].tolist()
periods = df_demand_multi.columns[2:]
T = len(periods)
demand_multi = {}
for t_idx, period in enumerate(periods):
    demand_multi[t_idx] = {}
    for _, row in df_demand_multi.iterrows():
        store = row['Customer']
        sku = row['SKU']
        qty = row[period]
        demand_multi[t_idx][(store, sku)] = qty

def calculate_loss_cost(t):
    if t <= 500:
        return 0.0
    loss_yuan = 0.2 * (t - 500) ** 2
    return loss_yuan / 10000.0

loss_cost_matrix = {(f, t): calculate_loss_cost(time_matrix[(f, t)]) for f, t in time_matrix.keys()}

problem = cplex.Cplex()
problem.objective.set_sense(problem.objective.sense.minimize)
problem.parameters.mip.tolerances.mipgap.set(0.005)
problem.parameters.timelimit.set(120)
problem.parameters.emphasis.mip.set(0)

var_indices = {}
var_count = 0

for t in range(T):
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            var_name = f'y_{t}_{wh}'
            lb = 1.0 if wh in cdc_names else 0.0
            problem.variables.add(obj=[0.0], lb=[lb], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
            var_indices[var_name] = var_count
            var_count += 1

for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:
        var_name = f'z_{wh}'
        problem.variables.add(obj=[1.5], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
        var_indices[var_name] = var_count
        var_count += 1

for t in range(T):
    for (store, sku), qty in demand_multi[t].items():
        eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible_whs:
            var_name = f'u_{t}_{wh}_{store}_{sku}'
            dist_val = dist.get((wh, store), 0)
            trans_cost = 1.45e-4 * dist_val * qty
            loss_cost = loss_cost_matrix.get((wh, store), 0.0) * qty
            proc_cost_val = 2.0 * proc_cost.get(wh, 0.0) * qty
            obj = trans_cost + loss_cost + proc_cost_val
            problem.variables.add(obj=[obj], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
            var_indices[var_name] = var_count
            var_count += 1

for t in range(T):
    for cdc in cdc_names:
        for rdc in rdc_names:
            for sku in ['im', 'dm']:
                if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                    var_name = f'f_{t}_{cdc}_{rdc}_{sku}'
                    dist_val = dist.get((cdc, rdc), 0)
                    trans_cost = 0.9e-4 * dist_val
                    loss_cost = loss_cost_matrix.get((cdc, rdc), 0.0)
                    proc_cost_cdc = 2.0 * proc_cost.get(cdc, 0.0)
                    obj = trans_cost + loss_cost + proc_cost_cdc
                    problem.variables.add(obj=[obj], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
                    var_indices[var_name] = var_count
                    var_count += 1

for t in range(T):
    for (store, sku), _ in demand_multi[t].items():
        var_name = f'v_{t}_{store}_{sku}'
        problem.variables.add(obj=[0.0], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
        var_indices[var_name] = var_count
        var_count += 1

for t in range(T):
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            var_name = f'w_{t}_{wh}'
            obj = -0.8 * proc_cost.get(wh, 0.0)
            problem.variables.add(obj=[obj], lb=[0.0], ub=[cplex.infinity], types=[problem.variables.type.continuous], names=[var_name])
            var_indices[var_name] = var_count
            var_count += 1

for t in range(T):
    for wh in rdc_names:
        var_name = f'open_new_{t}_{wh}'
        obj = open_cost.get(wh, 0.0)
        problem.variables.add(obj=[obj], lb=[0.0], ub=[1.0], types=[problem.variables.type.binary], names=[var_name])
        var_indices[var_name] = var_count
        var_count += 1

print(f"Variables: {var_count}")

constraint_count = 0

for wh in rdc_names:
    for t in range(1, T):
        var_y_t = f'y_{t}_{wh}'
        var_y_t_1 = f'y_{t-1}_{wh}'
        if var_y_t in var_indices and var_y_t_1 in var_indices:
            row = [[var_indices[var_y_t], var_indices[var_y_t_1]], [1.0, -1.0]]
            problem.linear_constraints.add(lin_expr=[row], senses=['G'], rhs=[0.0])
            constraint_count += 1

for wh in rdc_names:
    var_y = f'y_0_{wh}'
    var_open_new = f'open_new_0_{wh}'
    row = [[var_open_new, var_y], [1.0, -1.0]]
    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0])
    constraint_count += 1
    row = [[var_open_new, var_y], [-1.0, 1.0]]
    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0])
    constraint_count += 1
    for t in range(1, T):
        var_y_t = f'y_{t}_{wh}'
        var_y_t_1 = f'y_{t-1}_{wh}'
        var_open_new_t = f'open_new_{t}_{wh}'
        row1 = [[var_open_new_t, var_y_t], [1.0, -1.0]]
        problem.linear_constraints.add(lin_expr=[row1], senses=['L'], rhs=[0.0])
        constraint_count += 1
        row2 = [[var_open_new_t, var_y_t_1], [1.0, 1.0]]
        problem.linear_constraints.add(lin_expr=[row2], senses=['L'], rhs=[1.0])
        constraint_count += 1
        row3 = [[var_open_new_t, var_y_t, var_y_t_1], [-1.0, 1.0, -1.0]]
        problem.linear_constraints.add(lin_expr=[row3], senses=['L'], rhs=[0.0])
        constraint_count += 1

for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:
        var_z = f'z_{wh}'
        indices = [var_indices[var_z]] + [var_indices[f'y_{t}_{wh}'] for t in range(T)]
        values = [1.0] + [-1.0 for t in range(T)]
        problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['L'], rhs=[0.0])
        constraint_count += 1

for t in range(T):
    for (store, sku), _ in demand_multi[t].items():
        eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        indices = []
        values = []
        for wh in eligible_whs:
            var_name = f'u_{t}_{wh}_{store}_{sku}'
            if var_name in var_indices:
                indices.append(var_indices[var_name])
                values.append(1.0)
        if indices:
            problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['E'], rhs=[1.0])
            constraint_count += 1
    
    for (store, sku), _ in demand_multi[t].items():
        eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible_whs:
            var_u = f'u_{t}_{wh}_{store}_{sku}'
            var_y = f'y_{t}_{wh}'
            if var_u in var_indices and var_y in var_indices:
                row = [[var_indices[var_u], var_indices[var_y]], [1.0, -1.0]]
                problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0])
                constraint_count += 1
    
    for rdc in rdc_names:
        for sku in ['im', 'dm']:
            cdc = port_cdc if sku == 'im' else inland_cdc
            var_f = f'f_{t}_{cdc}_{rdc}_{sku}'
            indices = []
            values = []
            for (store, s), qty in demand_multi[t].items():
                if s == sku:
                    var_u = f'u_{t}_{rdc}_{store}_{sku}'
                    if var_u in var_indices:
                        indices.append(var_indices[var_u])
                        values.append(qty)
            if var_f in var_indices:
                indices.append(var_indices[var_f])
                values.append(-1.0)
            if indices:
                problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['E'], rhs=[0.0])
                constraint_count += 1
    
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type not in ['RDC', 'CDC']:
            continue
        var_y = f'y_{t}_{wh}'
        indices = [var_indices[var_y]]
        values = [-cap.get(wh, 0.0)]
        for (store, sku), qty in demand_multi[t].items():
            var_u = f'u_{t}_{wh}_{store}_{sku}'
            if var_u in var_indices:
                indices.append(var_indices[var_u])
                values.append(qty)
        if wh in cdc_names:
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (sku == 'im' and wh == port_cdc) or (sku == 'dm' and wh == inland_cdc):
                        var_f = f'f_{t}_{wh}_{rdc}_{sku}'
                        if var_f in var_indices:
                            indices.append(var_indices[var_f])
                            values.append(1.0)
        if indices:
            problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['L'], rhs=[0.0])
            constraint_count += 1
    
    time_limit = 600
    for (store, sku), _ in demand_multi[t].items():
        var_v = f'v_{t}_{store}_{sku}'
        eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible_whs:
            var_u = f'u_{t}_{wh}_{store}_{sku}'
            if var_u in var_indices and var_v in var_indices:
                travel_time = time_matrix.get((wh, store), float('inf'))
                if travel_time <= time_limit:
                    row = [[var_indices[var_v], var_indices[var_u]], [-1.0, 1.0]]
                    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[0.0])
                    constraint_count += 1
                else:
                    row = [[var_indices[var_v], var_indices[var_u]], [1.0, 1.0]]
                    problem.linear_constraints.add(lin_expr=[row], senses=['L'], rhs=[1.0])
                    constraint_count += 1
    
    total_seafood_demand_t = sum(qty for (store, sku), qty in demand_multi[t].items() if sku in ['im', 'dm'])
    indices = []
    values = []
    for (store, sku), qty in demand_multi[t].items():
        if sku in ['im', 'dm']:
            var_v = f'v_{t}_{store}_{sku}'
            if var_v in var_indices:
                indices.append(var_indices[var_v])
                values.append(qty)
    if indices:
        problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['G'], rhs=[0.95 * total_seafood_demand_t])
        constraint_count += 1
    
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            var_w = f'w_{t}_{wh}'
            var_z = f'z_{wh}'
            indices1 = [var_indices[var_w]]
            values1 = [1.0]
            for (store, sku), qty in demand_multi[t].items():
                var_u = f'u_{t}_{wh}_{store}_{sku}'
                if var_u in var_indices:
                    indices1.append(var_indices[var_u])
                    values1.append(-qty)
            if wh in cdc_names:
                for rdc in rdc_names:
                    for sku in ['im', 'dm']:
                        if (sku == 'im' and wh == port_cdc) or (sku == 'dm' and wh == inland_cdc):
                            var_f = f'f_{t}_{wh}_{rdc}_{sku}'
                            if var_f in var_indices:
                                indices1.append(var_indices[var_f])
                                values1.append(-1.0)
            problem.linear_constraints.add(lin_expr=[[indices1, values1]], senses=['L'], rhs=[0.0])
            constraint_count += 1
            indices2 = [var_indices[var_w], var_indices[var_z]]
            values2 = [1.0, -cap.get(wh, 100000)]
            problem.linear_constraints.add(lin_expr=[[indices2, values2]], senses=['L'], rhs=[0.0])
            constraint_count += 1

print(f"Constraints: {constraint_count}")
print("Solving with 120s time limit...")
problem.solve()

status = problem.solution.get_status()
status_str = problem.solution.get_status_string()
obj_val = problem.solution.get_objective_value()

try:
    mip_gap = problem.solution.MIP.get_mip_gap()
    print(f"MIP gap: {mip_gap:.6f} ({mip_gap*100:.4f}%)")
except:
    try:
        mip_gap = problem.solution.quality.get_int_quality()
        print(f"Quality: {mip_gap}")
    except:
        print("Could not get MIP gap")

best_bound = 0
try:
    best_bound = problem.solution.MIP.get_best_objective()
    print(f"Best bound: {best_bound:.4f}")
    print(f"Gap: {(obj_val - best_bound) / max(abs(best_bound), 1e-10) * 100:.4f}%")
except:
    try:
        best_bound = problem.properties.solution.get_best_objective_value()
        print(f"Best bound: {best_bound:.4f}")
    except:
        print("Could not get best bound")

print(f"Status: {status} ({status_str})")
print(f"Objective: {obj_val:.4f}")
print(f"Previous deterministic result: 233949.68")
print(f"Robust Gamma=0% result: 225122.56")
