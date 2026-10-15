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

dist_matrix = {}
dur_matrix = {}
for _, row in df_matrix.iterrows():
    origin = row['From']
    dest = row['To']
    dist_matrix[(origin, dest)] = row['Distance']
    dist_matrix[(dest, origin)] = row['Distance']
    dur_matrix[(origin, dest)] = row['Duration']
    dur_matrix[(dest, origin)] = row['Duration']

travel_time_matrix = dur_matrix

def calculate_loss_cost(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

loss_cost_matrix = {}
for wh_name in all_wh_names:
    for c_city in customer_cities:
        travel_time = dur_matrix.get((wh_name, c_city), 10000)
        loss_cost_matrix[(wh_name, c_city)] = calculate_loss_cost(travel_time)
for cdc in cdc_names:
    for rdc in rdc_names:
        travel_time = dur_matrix.get((cdc, rdc), 10000)
        loss_cost_matrix[(cdc, rdc)] = calculate_loss_cost(travel_time)

TIMELINESS_THRESHOLD = 600
TIMELINESS_RATIO = 0.95
SMART_COST = 1.5

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand_nominal = {t: {} for t in range(T)}
for _, row in df_forecast.iterrows():
    city = row['Customer']
    sku = row['SKU']
    for t_idx, date_col in enumerate(forecast_dates):
        qty = float(row[date_col])
        demand_nominal[t_idx][(city, sku)] = qty

all_demand_keys_period = {}
for t in range(T):
    all_demand_keys_period[t] = list(demand_nominal[t].keys())

print("Building robust model at Gamma=0%...")
problem = cplex.Cplex()
problem.objective.set_sense(problem.objective.sense.minimize)

var_indices = {}
var_count = 0

def add_var(name, vtype, lb, ub, obj):
    global var_count
    if vtype == 'B':
        problem.variables.add(obj=[obj], lb=[lb], ub=[ub], types=[problem.variables.type.binary], names=[name])
    else:
        problem.variables.add(obj=[obj], lb=[lb], ub=[ub], types=[problem.variables.type.continuous], names=[name])
    var_indices[name] = var_count
    var_count += 1
    return var_count - 1

for t in range(T):
    for wh in rdc_names:
        add_var(f'y_{t}_{wh}', 'B', 0, 1, 0)

for t in range(T):
    for wh in rdc_names:
        add_var(f'open_new_{t}_{wh}', 'B', 0, 1, open_cost.get(wh, 0.0))

for wh in rdc_names:
    add_var(f'z_{wh}', 'B', 0, 1, SMART_COST)

for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand_nominal[t]:
                continue
            eligible_whs = [sku_cdc[s]] + rdc_names
            for wh in eligible_whs:
                dist_km = dist_matrix.get((wh, c), 99999)
                if dist_km > 5000:
                    continue
                add_var(f'u_{t}_{wh}_{c}_{s}', 'B', 0, 1, 0)

for t in range(T):
    for cdc in cdc_names:
        s = cdc_sku[cdc]
        for rdc in rdc_names:
            dist_km = dist_matrix.get((cdc, rdc), 99999)
            if dist_km > 5000:
                continue
            add_var(f'f_{t}_{cdc}_{rdc}_{s}', 'C', 0, 100000, 0)

for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand_nominal[t]:
                continue
            add_var(f'v_{t}_{c}_{s}', 'B', 0, 1, 0)

for t in range(T):
    for wh in rdc_names:
        add_var(f'w_{t}_{wh}', 'C', 0, 100000, 0)

print(f"Variables: {var_count}")

constraint_count = 0

def add_constraint(indices, coeffs, sense, rhs):
    global constraint_count
    problem.linear_constraints.add(
        lin_expr=[cplex.SparsePair(ind=[int(i) for i in indices], val=[float(c) for c in coeffs])],
        senses=[sense], rhs=[float(rhs)]
    )
    constraint_count += 1

# (1) Monotonic
for wh in rdc_names:
    for t in range(1, T):
        add_constraint([var_indices[f'y_{t}_{wh}'], var_indices[f'y_{t-1}_{wh}']], [1, -1], 'G', 0)

# (2) Open new
for wh in rdc_names:
    add_constraint([var_indices[f'open_new_0_{wh}'], var_indices[f'y_0_{wh}']], [1, -1], 'E', 0)
    for t in range(1, T):
        add_constraint([var_indices[f'open_new_{t}_{wh}'], var_indices[f'y_{t}_{wh}'], var_indices[f'y_{t-1}_{wh}']], [1, -1, 1], 'E', 0)

# (3) Single source
for t in range(T):
    for c in customer_cities:
        for s in skus:
            indices = []
            coeffs = []
            for wh in all_wh_names:
                var_name = f'u_{t}_{wh}_{c}_{s}'
                if var_name in var_indices:
                    indices.append(var_indices[var_name])
                    coeffs.append(1)
            if indices:
                add_constraint(indices, coeffs, 'E', 1)

# (4) Service-open (RDC only)
for t in range(T):
    for wh in rdc_names:
        idx_y = var_indices[f'y_{t}_{wh}']
        for c in customer_cities:
            for s in skus:
                var_name = f'u_{t}_{wh}_{c}_{s}'
                if var_name in var_indices:
                    add_constraint([var_indices[var_name], idx_y], [1, -1], 'L', 0)

# (5) Flow balance
for t in range(T):
    for rdc in rdc_names:
        for s in skus:
            if s not in cdc_sku.values():
                continue
            cdc_name = sku_cdc[s]
            f_var = f'f_{t}_{cdc_name}_{rdc}_{s}'
            if f_var not in var_indices:
                continue
            indices = [var_indices[f_var]]
            coeffs = [-1.0]
            for c in customer_cities:
                u_var = f'u_{t}_{rdc}_{c}_{s}'
                if u_var in var_indices and (c, s) in demand_nominal[t]:
                    qty = demand_nominal[t][(c, s)]
                    indices.append(var_indices[u_var])
                    coeffs.append(qty)
            if len(indices) > 1:
                add_constraint(indices, coeffs, 'E', 0)

# (6) RDC capacity (at Gamma=0%, no robust terms)
for t in range(T):
    for wh in rdc_names:
        idx_y = var_indices[f'y_{t}_{wh}']
        cap_wh = cap.get(wh, 5000)
        indices_lhs = []
        coeffs_lhs = []
        for s in skus:
            for c in customer_cities:
                u_var = f'u_{t}_{wh}_{c}_{s}'
                if u_var not in var_indices or (c, s) not in demand_nominal[t]:
                    continue
                qty_nominal = demand_nominal[t][(c, s)]
                indices_lhs.append(var_indices[u_var])
                coeffs_lhs.append(qty_nominal)
        if indices_lhs:
            all_indices = indices_lhs + [idx_y]
            all_coeffs = coeffs_lhs + [-cap_wh]
            add_constraint(all_indices, all_coeffs, 'L', 0)

# (8) CDC capacity
for t in range(T):
    for cdc in cdc_names:
        s = cdc_sku[cdc]
        cap_cdc = cap.get(cdc, 100000)
        indices_cdc = []
        coeffs_cdc = []
        for c in customer_cities:
            u_var = f'u_{t}_{cdc}_{c}_{s}'
            if u_var in var_indices and (c, s) in demand_nominal[t]:
                qty = demand_nominal[t][(c, s)]
                indices_cdc.append(var_indices[u_var])
                coeffs_cdc.append(qty)
        for rdc in rdc_names:
            f_var = f'f_{t}_{cdc}_{rdc}_{s}'
            if f_var in var_indices:
                indices_cdc.append(var_indices[f_var])
                coeffs_cdc.append(1.0)
        if indices_cdc:
            add_constraint(indices_cdc, coeffs_cdc, 'L', cap_cdc)

# (9) Timeliness v constraint
for t in range(T):
    for c in customer_cities:
        for s in skus:
            v_var = f'v_{t}_{c}_{s}'
            if v_var not in var_indices or (c, s) not in demand_nominal[t]:
                continue
            indices_v = [var_indices[v_var]]
            coeffs_v = [1.0]
            u_found = False
            for wh in all_wh_names:
                u_var = f'u_{t}_{wh}_{c}_{s}'
                travel_time = travel_time_matrix.get((wh, c), 99999)
                if u_var in var_indices and travel_time <= TIMELINESS_THRESHOLD:
                    indices_v.append(var_indices[u_var])
                    coeffs_v.append(-1.0)
                    u_found = True
            if u_found:
                add_constraint(indices_v, coeffs_v, 'L', 0)

# (10) Timeliness overall
for t in range(T):
    total_demand_t = sum(demand_nominal[t][(c, s)] for c, s in all_demand_keys_period[t])
    required_tonnage = TIMELINESS_RATIO * total_demand_t
    indices_time = []
    coeffs_time = []
    for c, s in all_demand_keys_period[t]:
        v_var = f'v_{t}_{c}_{s}'
        qty = demand_nominal[t][(c, s)]
        if v_var in var_indices:
            indices_time.append(var_indices[v_var])
            coeffs_time.append(qty)
    if indices_time:
        add_constraint(indices_time, coeffs_time, 'G', required_tonnage)

# (11) Smart system z
for wh in rdc_names:
    idx_z = var_indices[f'z_{wh}']
    indices_zy = [idx_z]
    coeffs_zy = [1]
    for t in range(T):
        idx_yt = var_indices[f'y_{t}_{wh}']
        indices_zy.append(idx_yt)
        coeffs_zy.append(-1)
    add_constraint(indices_zy, coeffs_zy, 'L', 0)

# (12) w constraint
for t in range(T):
    for wh in rdc_names:
        w_var = f'w_{t}_{wh}'
        if w_var not in var_indices:
            continue
        indices_w = [var_indices[w_var]]
        coeffs_w = [1.0]
        for c in customer_cities:
            for s in skus:
                u_var = f'u_{t}_{wh}_{c}_{s}'
                if u_var in var_indices and (c, s) in demand_nominal[t]:
                    indices_w.append(var_indices[u_var])
                    coeffs_w.append(-demand_nominal[t][(c, s)])
        add_constraint(indices_w, coeffs_w, 'L', 0)
        idx_z = var_indices[f'z_{wh}']
        add_constraint([var_indices[w_var], idx_z], [1, -cap.get(wh, 100000)], 'L', 0)

print(f"Constraints: {constraint_count}")

# Set objective coefficients
obj_contributions = {}
for t in range(T):
    for wh in all_wh_names:
        for c in customer_cities:
            for s in skus:
                u_var = f'u_{t}_{wh}_{c}_{s}'
                if u_var not in var_indices or (c, s) not in demand_nominal[t]:
                    continue
                qty = demand_nominal[t][(c, s)]
                dist_val = dist_matrix.get((wh, c), 99999)
                trans_cost = 1.45e-4 * dist_val * qty
                loss_cost = loss_cost_matrix.get((wh, c), 0.0) * qty
                proc_val = 2.0 * proc_cost.get(wh, 0.0) * qty
                obj_val = trans_cost + loss_cost + proc_val
                obj_contributions[u_var] = obj_contributions.get(u_var, 0) + obj_val

    for cdc in cdc_names:
        s = cdc_sku[cdc]
        for rdc in rdc_names:
            f_var = f'f_{t}_{cdc}_{rdc}_{s}'
            if f_var not in var_indices:
                continue
            dist_val = dist_matrix.get((cdc, rdc), 99999)
            trans_cost = 0.9e-4 * dist_val
            loss_cost = loss_cost_matrix.get((cdc, rdc), 0.0)
            proc_val = 2.0 * proc_cost.get(cdc, 0.0)
            obj_val = trans_cost + loss_cost + proc_val
            obj_contributions[f_var] = obj_contributions.get(f_var, 0) + obj_val

    for wh in rdc_names:
        w_var = f'w_{t}_{wh}'
        if w_var in var_indices:
            obj_contributions[w_var] = obj_contributions.get(w_var, 0) - 0.8 * proc_cost.get(wh, 0.0)

for var_name, coeff in obj_contributions.items():
    if var_name in var_indices:
        problem.objective.set_linear(var_indices[var_name], coeff)

# Solve LP relaxation first
print("\nSolving LP relaxation...")
problem_lp = problem
problem_lp.set_problem_name("robust_gamma_0_LP")
for v in range(var_count):
    vtype = problem_lp.variables.get_types(v)
    if vtype == problem_lp.variables.type.binary:
        problem_lp.variables.set_types(v, problem_lp.variables.type.continuous)

problem_lp.parameters.timelimit.set(60)
problem_lp.solve()
lp_obj = problem_lp.solution.get_objective_value()
print(f"LP relaxation objective: {lp_obj:.4f}")
print(f"Deterministic LP relaxation: 232543.4257")
print(f"LP gap: {lp_obj - 232543.4257:.4f}")

# Now solve as MIP
print("\nSolving MIP...")
problem2 = cplex.Cplex()
problem2.objective.set_sense(problem2.objective.sense.minimize)
problem2.parameters.timelimit.set(120)
problem2.parameters.mip.tolerances.mipgap.set(0.005)
problem2.parameters.threads.set(4)

# Re-read the original model and solve
import importlib.util
spec = importlib.util.spec_from_file_location("robust", os.path.join(BASE_DIR, 'src/solvers/question4/solve_problem4_robust.py'))
robust_mod = importlib.util.module_from_spec(spec)

# Instead, let's just solve the problem we already built
# But we modified the variable types for LP. Let me rebuild.
print("Rebuilding model for MIP solve...")
