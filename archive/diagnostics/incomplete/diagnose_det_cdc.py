import pandas as pd
import numpy as np
import cplex
import os
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, 'input_data')

df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))
df_wh = pd.read_csv(os.path.join(INPUT_DIR, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_demand = pd.read_csv(os.path.join(BASE_DIR, 'output_result_question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

cap = {}
open_cost = {}
proc_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    open_cost[row['Name']] = row['Opening_fee']
    proc_cost[row['Name']] = row['Processing_fee']

dist = {}
time_matrix = {}
for _, row in df_matrix.iterrows():
    dist[(row['From'], row['To'])] = row['Distance']
    dist[(row['To'], row['From'])] = row['Distance']
    time_matrix[(row['From'], row['To'])] = row['Duration']
    time_matrix[(row['To'], row['From'])] = row['Duration']

def calc_loss(t):
    if t <= 500:
        return 0.0
    return 0.2 * (t - 500) ** 2 / 10000.0

loss_cost_matrix = {(f, t): calc_loss(time_matrix[(f, t)]) for f, t in time_matrix.keys()}

periods = df_demand.columns[2:]
T = len(periods)
demand_multi = {}
for t_idx, period in enumerate(periods):
    demand_multi[t_idx] = {}
    for _, row in df_demand.iterrows():
        demand_multi[t_idx][(row['Customer'], row['SKU'])] = row[period]

print("=" * 80)
print("DETERMINISTIC MODEL - checking CDC z/w values")
print("=" * 80)

problem = cplex.Cplex()
problem.objective.set_sense(problem.objective.sense.minimize)
problem.parameters.mip.tolerances.mipgap.set(0.005)
problem.parameters.timelimit.set(1800)
problem.set_log_stream(None)
problem.set_error_stream(None)
problem.set_warning_stream(None)
problem.set_results_stream(None)

var_indices = {}
var_count = 0

for t in range(T):
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            lb = 1.0 if wh in cdc_names else 0.0
            problem.variables.add(obj=[0], lb=[lb], ub=[1], types=['B'], names=[f'y_{t}_{wh}'])
            var_indices[f'y_{t}_{wh}'] = var_count
            var_count += 1

for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:
        problem.variables.add(obj=[1.5], lb=[0], ub=[1], types=['B'], names=[f'z_{wh}'])
        var_indices[f'z_{wh}'] = var_count
        var_count += 1

for t in range(T):
    for (store, sku), qty in demand_multi[t].items():
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            d = dist.get((wh, store), 0)
            tc = 1.45e-4 * d * qty
            lc = loss_cost_matrix.get((wh, store), 0.0) * qty
            pc = 2.0 * proc_cost.get(wh, 0) * qty
            problem.variables.add(obj=[tc+lc+pc], lb=[0], ub=[1], types=['B'], names=[f'u_{t}_{wh}_{store}_{sku}'])
            var_indices[f'u_{t}_{wh}_{store}_{sku}'] = var_count
            var_count += 1

for t in range(T):
    for cdc in cdc_names:
        for rdc in rdc_names:
            for sku in ['im', 'dm']:
                if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                    d = dist.get((cdc, rdc), 0)
                    tc = 0.9e-4 * d
                    lc = loss_cost_matrix.get((cdc, rdc), 0.0)
                    pc = 2.0 * proc_cost.get(cdc, 0)
                    problem.variables.add(obj=[tc+lc+pc], lb=[0], ub=[cplex.infinity], types=['C'], names=[f'f_{t}_{cdc}_{rdc}_{sku}'])
                    var_indices[f'f_{t}_{cdc}_{rdc}_{sku}'] = var_count
                    var_count += 1

for t in range(T):
    for (store, sku), _ in demand_multi[t].items():
        problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[f'v_{t}_{store}_{sku}'])
        var_indices[f'v_{t}_{store}_{sku}'] = var_count
        var_count += 1

for t in range(T):
    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            problem.variables.add(obj=[-0.8*proc_cost.get(wh,0)], lb=[0], ub=[cplex.infinity], types=['C'], names=[f'w_{t}_{wh}'])
            var_indices[f'w_{t}_{wh}'] = var_count
            var_count += 1

for t in range(T):
    for wh in rdc_names:
        problem.variables.add(obj=[open_cost.get(wh,0)], lb=[0], ub=[1], types=['B'], names=[f'open_new_{t}_{wh}'])
        var_indices[f'open_new_{t}_{wh}'] = var_count
        var_count += 1

print(f"Total vars: {var_count}")

constraint_count = 0

for wh in rdc_names:
    for t in range(1, T):
        problem.linear_constraints.add(lin_expr=[[[var_indices[f'y_{t}_{wh}'], var_indices[f'y_{t-1}_{wh}']], [1, -1]]], senses=['G'], rhs=[0])
        constraint_count += 1

for wh in rdc_names:
    problem.linear_constraints.add(lin_expr=[[[var_indices[f'open_new_0_{wh}'], var_indices[f'y_0_{wh}']], [1, -1]], senses=['L'], rhs=[0])
    constraint_count += 1
    problem.linear_constraints.add(lin_expr=[[[var_indices[f'open_new_0_{wh}'], var_indices[f'y_0_{wh}']], [-1, 1]], senses=['L'], rhs=[0])
    constraint_count += 1
    for t in range(1, T):
        problem.linear_constraints.add(lin_expr=[[[var_indices[f'open_new_{t}_{wh}'], var_indices[f'y_{t}_{wh}']], [1, -1]], senses=['L'], rhs=[0])
        constraint_count += 1
        problem.linear_constraints.add(lin_expr=[[[var_indices[f'open_new_{t}_{wh}'], var_indices[f'y_{t-1}_{wh}']], [1, 1]], senses=['L'], rhs=[1])
        constraint_count += 1
        problem.linear_constraints.add(lin_expr=[[[var_indices[f'open_new_{t}_{wh}'], var_indices[f'y_{t}_{wh}'], var_indices[f'y_{t-1}_{wh}']], [-1, 1, -1]], senses=['L'], rhs=[0])
        constraint_count += 1

for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:
        indices = [var_indices[f'z_{wh}']] + [var_indices[f'y_{t}_{wh}'] for t in range(T)]
        values = [1] + [-1]*T
        problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['L'], rhs=[0])
        constraint_count += 1

for t in range(T):
    for (store, sku), _ in demand_multi[t].items():
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        indices = []
        values = []
        for wh in eligible:
            vn = f'u_{t}_{wh}_{store}_{sku}'
            if vn in var_indices:
                indices.append(var_indices[vn])
                values.append(1)
        if indices:
            problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['E'], rhs=[1])
            constraint_count += 1

    for (store, sku), _ in demand_multi[t].items():
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            vn = f'u_{t}_{wh}_{store}_{sku}'
            vy = f'y_{t}_{wh}'
            if vn in var_indices and vy in var_indices:
                problem.linear_constraints.add(lin_expr=[[[var_indices[vn], var_indices[vy]], [1, -1]]], senses=['L'], rhs=[0])
                constraint_count += 1

    for rdc in rdc_names:
        for sku in ['im', 'dm']:
            cdc = port_cdc if sku == 'im' else inland_cdc
            vf = f'f_{t}_{cdc}_{rdc}_{sku}'
            indices = []
            values = []
            for (store, s), qty in demand_multi[t].items():
                if s == sku:
                    vu = f'u_{t}_{rdc}_{store}_{sku}'
                    if vu in var_indices:
                        indices.append(var_indices[vu])
                        values.append(qty)
            if vf in var_indices:
                indices.append(var_indices[vf])
                values.append(-1.0)
            if indices:
                problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['E'], rhs=[0])
                constraint_count += 1

    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type not in ['RDC', 'CDC']:
            continue
        vy = f'y_{t}_{wh}'
        indices = [var_indices[vy]]
        values = [-cap.get(wh, 0)]
        for (store, sku), qty in demand_multi[t].items():
            vu = f'u_{t}_{wh}_{store}_{sku}'
            if vu in var_indices:
                indices.append(var_indices[vu])
                values.append(qty)
        if wh in cdc_names:
            for rdc in rdc_names:
                for sku in ['im', 'dm']:
                    if (sku == 'im' and wh == port_cdc) or (sku == 'dm' and wh == inland_cdc):
                        vf = f'f_{t}_{wh}_{rdc}_{sku}'
                        if vf in var_indices:
                            indices.append(var_indices[vf])
                            values.append(1.0)
        if indices:
            problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['L'], rhs=[0])
            constraint_count += 1

    for (store, sku), _ in demand_multi[t].items():
        vv = f'v_{t}_{store}_{sku}'
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            vu = f'u_{t}_{wh}_{store}_{sku}'
            if vu in var_indices and vv in var_indices:
                tt = time_matrix.get((wh, store), float('inf'))
                if tt <= 600:
                    problem.linear_constraints.add(lin_expr=[[[var_indices[vv], var_indices[vu]], [-1, 1]]], senses=['L'], rhs=[0])
                    constraint_count += 1
                else:
                    problem.linear_constraints.add(lin_expr=[[[var_indices[vv], var_indices[vu]], [1, 1]]], senses=['L'], rhs=[1])
                    constraint_count += 1

    total_demand_t = sum(qty for (store, sku), qty in demand_multi[t].items() if sku in ['im', 'dm'])
    indices = []
    values = []
    for (store, sku), qty in demand_multi[t].items():
        if sku in ['im', 'dm']:
            vv = f'v_{t}_{store}_{sku}'
            if vv in var_indices:
                indices.append(var_indices[vv])
                values.append(qty)
    if indices:
        problem.linear_constraints.add(lin_expr=[[indices, values]], senses=['G'], rhs=[0.95*total_demand_t])
        constraint_count += 1

    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            vw = f'w_{t}_{wh}'
            vz = f'z_{wh}'
            indices1 = [var_indices[vw]]
            values1 = [1.0]
            for (store, sku), qty in demand_multi[t].items():
                vu = f'u_{t}_{wh}_{store}_{sku}'
                if vu in var_indices:
                    indices1.append(var_indices[vu])
                    values1.append(-qty)
            if wh in cdc_names:
                for rdc in rdc_names:
                    for sku in ['im', 'dm']:
                        if (sku == 'im' and wh == port_cdc) or (sku == 'dm' and wh == inland_cdc):
                            vf = f'f_{t}_{wh}_{rdc}_{sku}'
                            if vf in var_indices:
                                indices1.append(var_indices[vf])
                                values1.append(-1.0)
            problem.linear_constraints.add(lin_expr=[[indices1, values1]], senses=['L'], rhs=[0])
            constraint_count += 1
            problem.linear_constraints.add(lin_expr=[[[var_indices[vw], var_indices[vz]], [1, -cap.get(wh, 100000)]]], senses=['L'], rhs=[0])
            constraint_count += 1

print(f"Total constraints: {constraint_count}")
print("Solving...")
problem.solve()

status = problem.solution.get_status_string()
obj = problem.solution.get_objective_value()
print(f"Status: {status}")
print(f"Objective: {obj:.4f}")

sol = problem.solution.get_values()

print("\n" + "=" * 80)
print("CDC z/w values in deterministic model")
print("=" * 80)
for wh in cdc_names:
    z_key = f'z_{wh}'
    z_val = sol[var_indices[z_key]] if z_key in var_indices else 'N/A'
    print(f"  z_{wh} = {z_val}")
    for t in range(T):
        w_key = f'w_{t}_{wh}'
        w_val = sol[var_indices[w_key]] if w_key in var_indices else 'N/A'
        if isinstance(w_val, float) and w_val > 0.01:
            print(f"    w_{t}_{wh} = {w_val:.4f}, discount = {0.8*proc_cost.get(wh,0)*w_val:.4f}")

print("\nRDC z/w values:")
for wh in rdc_names:
    z_key = f'z_{wh}'
    z_val = sol[var_indices[z_key]] if z_key in var_indices else 'N/A'
    total_w = 0
    for t in range(T):
        w_key = f'w_{t}_{wh}'
        w_val = sol[var_indices[w_key]] if w_key in var_indices else 0
        total_w += w_val
    if isinstance(z_val, float) and z_val > 0.5:
        print(f"  z_{wh} = {z_val:.4f}, total_w = {total_w:.4f}")

print("\n" + "=" * 80)
print("Cost breakdown comparison")
print("=" * 80)

total_loss = 0
total_proc = 0
total_trans_cust = 0
total_trans_wh = 0
total_discount = 0
total_open = 0
total_smart = 0

for t in range(T):
    for (store, sku), qty in demand_multi[t].items():
        eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            vu = f'u_{t}_{wh}_{store}_{sku}'
            if vu in var_indices and sol[var_indices[vu]] > 0.5:
                d = dist.get((wh, store), 0)
                total_trans_cust += 1.45e-4 * d * qty
                total_loss += loss_cost_matrix.get((wh, store), 0) * qty
                total_proc += 2.0 * proc_cost.get(wh, 0) * qty

    for cdc in cdc_names:
        for rdc in rdc_names:
            for sku in ['im', 'dm']:
                if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                    vf = f'f_{t}_{cdc}_{rdc}_{sku}'
                    if vf in var_indices:
                        fqty = sol[var_indices[vf]]
                        if fqty > 0.01:
                            d = dist.get((cdc, rdc), 0)
                            total_trans_wh += 0.9e-4 * d * fqty
                            total_loss += loss_cost_matrix.get((cdc, rdc), 0) * fqty
                            total_proc += 2.0 * proc_cost.get(cdc, 0) * fqty

    for wh in df_wh['Name']:
        wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
        if wh_type in ['RDC', 'CDC']:
            vw = f'w_{t}_{wh}'
            if vw in var_indices:
                wv = sol[var_indices[vw]]
                if wv > 0.01:
                    total_discount += 0.8 * proc_cost.get(wh, 0) * wv

for wh in rdc_names:
    for t in range(T):
        von = f'open_new_{t}_{wh}'
        if von in var_indices and sol[var_indices[von]] > 0.5:
            total_open += open_cost.get(wh, 0)

for wh in df_wh['Name']:
    wh_type = df_wh[df_wh['Name'] == wh]['Type'].values[0]
    if wh_type in ['RDC', 'CDC']:
        vz = f'z_{wh}'
        if vz in var_indices and sol[var_indices[vz]] > 0.5:
            total_smart += 1.5

cdc_discount = 0
rdc_discount = 0
for wh in cdc_names:
    for t in range(T):
        vw = f'w_{t}_{wh}'
        if vw in var_indices:
            wv = sol[var_indices[vw]]
            if wv > 0.01:
                cdc_discount += 0.8 * proc_cost.get(wh, 0) * wv
for wh in rdc_names:
    for t in range(T):
        vw = f'w_{t}_{wh}'
        if vw in var_indices:
            wv = sol[var_indices[vw]]
            if wv > 0.01:
                rdc_discount += 0.8 * proc_cost.get(wh, 0) * wv

print(f"  Transport (cust): {total_trans_cust:.2f}")
print(f"  Transport (wh):   {total_trans_wh:.2f}")
print(f"  Loss:             {total_loss:.2f}")
print(f"  Proc (gross):     {total_proc:.2f}")
print(f"  Discount (total): {total_discount:.2f}")
print(f"    CDC discount:   {cdc_discount:.2f}")
print(f"    RDC discount:   {rdc_discount:.2f}")
print(f"  Proc (net):       {total_proc - total_discount:.2f}")
print(f"  Open cost:        {total_open:.2f}")
print(f"  Smart cost:       {total_smart:.2f}")
print(f"  ---")
print(f"  Sum:              {total_trans_cust + total_trans_wh + total_loss + total_proc - total_discount + total_open + total_smart:.2f}")
print(f"  CPLEX objective:  {obj:.2f}")
print(f"  Difference:       {obj - (total_trans_cust + total_trans_wh + total_loss + total_proc - total_discount + total_open + total_smart):.2f}")

print("\n" + "=" * 80)
print("Routing analysis: CDC direct service")
print("=" * 80)
cdc_direct_serve = 0
cdc_direct_loss = 0
for t in range(T):
    for (store, sku), qty in demand_multi[t].items():
        for cdc in cdc_names:
            vu = f'u_{t}_{cdc}_{store}_{sku}'
            if vu in var_indices and sol[var_indices[vu]] > 0.5:
                cdc_direct_serve += qty
                cdc_direct_loss += loss_cost_matrix.get((cdc, store), 0) * qty
print(f"  CDC direct serve: {cdc_direct_serve:.2f} tons")
print(f"  CDC direct loss:  {cdc_direct_loss:.2f} wan yuan")

rdc_serve = 0
rdc_loss = 0
for t in range(T):
    for (store, sku), qty in demand_multi[t].items():
        for rdc in rdc_names:
            vu = f'u_{t}_{rdc}_{store}_{sku}'
            if vu in var_indices and sol[var_indices[vu]] > 0.5:
                rdc_serve += qty
                rdc_loss += loss_cost_matrix.get((rdc, store), 0) * qty
print(f"  RDC serve: {rdc_serve:.2f} tons")
print(f"  RDC loss:  {rdc_loss:.2f} wan yuan")

print("\n" + "=" * 80)
print("CDC->RDC transfer analysis")
print("=" * 80)
transfer_loss = 0
transfer_qty = 0
for t in range(T):
    for cdc in cdc_names:
        for rdc in rdc_names:
            for sku in ['im', 'dm']:
                if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                    vf = f'f_{t}_{cdc}_{rdc}_{sku}'
                    if vf in var_indices:
                        fqty = sol[var_indices[vf]]
                        if fqty > 0.01:
                            transfer_qty += fqty
                            transfer_loss += loss_cost_matrix.get((cdc, rdc), 0) * fqty
print(f"  Total transfer: {transfer_qty:.2f} tons")
print(f"  Transfer loss:  {transfer_loss:.2f} wan yuan")
print(f"  Total loss = CDC direct + RDC->cust + CDC->RDC = {cdc_direct_loss + rdc_loss + transfer_loss:.2f}")
