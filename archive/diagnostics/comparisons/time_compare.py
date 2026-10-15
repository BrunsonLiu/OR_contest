"""精确测量两个模型的求解时间"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import time
import cplex
import pandas as pd
import numpy as np

BASE = str(_REPO_ROOT)

# 读数据
df_wh = pd.read_csv(f'{BASE}/data/raw/df_wh.csv')
df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
df_proc = pd.read_csv(f'{BASE}/data/raw/df_proc.csv')
df_forecast = pd.read_csv(f'{BASE}/results/question3/订单需求量预测结果文件_sota.csv')

dist = {}
dur = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

cap = {}; open_cost = {}; proc_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    open_cost[row['Name']] = row['Opening_fee']
    proc_cost[row['Name']] = row['Processing_fee']

def loss_per_ton(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000

loss_cost_matrix = {}
for (f, t), d in dur.items():
    loss_cost_matrix[(f, t)] = loss_per_ton(d)

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)

demand_multi = {}
for t_idx, period in enumerate(forecast_dates):
    demand_multi[t_idx] = {}
    for _, row in df_forecast.iterrows():
        demand_multi[t_idx][(row['Customer'], row['SKU'])] = float(row[period])

# ========== 确定性模型 (1天) ==========
print("=" * 70)
print("确定性模型: 1天求解时间")
print("=" * 70)

t0 = time.time()
problem = cplex.Cplex()
problem.set_log_stream(None)
problem.set_warning_stream(None)
problem.set_results_stream(None)
problem.objective.set_sense(problem.objective.sense.minimize)
problem.parameters.mip.tolerances.mipgap.set(0.005)
problem.parameters.timelimit.set(1800)

var_count = 0
var_indices = {}

# y variables
for wh in rdc_names:
    var_name = f'y_0_{wh}'
    problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[var_name])
    var_indices[var_name] = var_count; var_count += 1

# open_new variables
for wh in rdc_names:
    var_name = f'open_new_0_{wh}'
    problem.variables.add(obj=[open_cost.get(wh,0)], lb=[0], ub=[1], types=['B'], names=[var_name])
    var_indices[var_name] = var_count; var_count += 1

# w variables (smart)
for wh in rdc_names:
    var_name = f'w_0_{wh}'
    problem.variables.add(obj=[1.5 - 0.8*proc_cost.get(wh,0)], lb=[0], ub=[1], types=['B'], names=[var_name])
    var_indices[var_name] = var_count; var_count += 1

# u variables
t = 0
for (store, sku), qty in demand_multi[t].items():
    eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
    for wh in eligible_whs:
        var_name = f'u_{t}_{wh}_{store}_{sku}'
        d_val = dist.get((wh, store), 0)
        l_val = loss_cost_matrix.get((wh, store), 0.0)
        p_val = 2.0 * proc_cost.get(wh, 0.0)
        obj = 1.45e-4 * d_val * qty + l_val * qty + p_val * qty
        problem.variables.add(obj=[obj], lb=[0], ub=[1], types=['B'], names=[var_name])
        var_indices[var_name] = var_count; var_count += 1

# f variables
for cdc in cdc_names:
    for rdc in rdc_names:
        for sku in ['im', 'dm']:
            if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                var_name = f'f_{t}_{cdc}_{rdc}_{sku}'
                d_val = dist.get((cdc, rdc), 0)
                l_val = loss_cost_matrix.get((cdc, rdc), 0.0)
                p_val = 2.0 * proc_cost.get(cdc, 0.0)
                obj = 0.9e-4 * d_val + l_val + p_val
                problem.variables.add(obj=[obj], lb=[0], ub=[cplex.infinity], types=['C'], names=[var_name])
                var_indices[var_name] = var_count; var_count += 1

# v variables
for (store, sku), _ in demand_multi[t].items():
    var_name = f'v_{t}_{store}_{sku}'
    problem.variables.add(obj=[0], lb=[0], ub=[1], types=['B'], names=[var_name])
    var_indices[var_name] = var_count; var_count += 1

build_time = time.time() - t0
print(f"  建模时间: {build_time:.1f}s")
print(f"  变量数: {var_count}")

t1 = time.time()
problem.solve()
solve_time = time.time() - t1

status = problem.solution.get_status()
obj = problem.solution.get_objective_value()
print(f"  求解时间: {solve_time:.1f}s")
print(f"  状态: {status}, 目标值: {obj:.2f}")

# 统计开了几个RDC
open_rdcs = []
for wh in rdc_names:
    y_val = problem.solution.get_values(var_indices[f'y_0_{wh}'])
    if y_val > 0.5:
        open_rdcs.append(wh)
print(f"  开仓数: {len(open_rdcs)}")
print(f"  仓库: {open_rdcs}")

# ========== 鲁棒模型 (7天联合, Gamma=0%) ==========
print("\n" + "=" * 70)
print("鲁棒模型: 7天联合求解时间 (Gamma=0%)")
print("=" * 70)

# 直接import主脚本
import sys
sys.path.insert(0, BASE)

t_start = time.time()
# 用subprocess更干净
import subprocess
result = subprocess.run(
    ['python', '-c', '''
import time, sys
sys.path.insert(0, str(__import__("pathlib").Path.cwd()))
t0 = time.time()

# 简化：只构建Gamma=0的模型
import cplex
import pandas as pd
import numpy as np

BASE = str(__import__("pathlib").Path.cwd())
df_wh = pd.read_csv(f"{BASE}/data/raw/df_wh.csv")
df_matrix = pd.read_csv(f"{BASE}/data/raw/df_matrix.csv")
df_proc = pd.read_csv(f"{BASE}/data/raw/df_proc.csv")
df_forecast = pd.read_csv(f"{BASE}/results/question3/订单需求量预测结果文件_sota.csv")

dist = {}; dur = {}
for _, r in df_matrix.iterrows():
    dist[(r["From"], r["To"])] = r["Distance"]
    dist[(r["To"], r["From"])] = r["Distance"]
    dur[(r["From"], r["To"])] = r["Duration"]
    dur[(r["To"], r["From"])] = r["Duration"]

cap = {}; open_cost = {}; proc_cost = {}
for _, row in df_proc.iterrows():
    cap[row["Name"]] = row["Capacity"]
    open_cost[row["Name"]] = row["Opening_fee"]
    proc_cost[row["Name"]] = row["Processing_fee"]

def loss_per_ton(m):
    return 0.0 if m <= 500 else 0.2*(m-500)**2/10000

loss_cost_matrix = {(f,t): loss_per_ton(d) for (f,t),d in dur.items()}

cdc_names = df_wh[df_wh["Type"]=="CDC"]["Name"].tolist()
rdc_names = df_wh[df_wh["Type"]=="RDC"]["Name"].tolist()
port_cdc = [w for w in cdc_names if "gang-kou" in w][0]
inland_cdc = [w for w in cdc_names if "nei-lu" in w][0]
customer_cities = pd.read_csv(f"{BASE}/data/raw/df_customer.csv")["Name"].tolist()

forecast_dates = [c for c in df_forecast.columns if c not in ["Customer","SKU"]]
T = len(forecast_dates)

demand = {}
for t_idx, dc in enumerate(forecast_dates):
    demand[t_idx] = {}
    for _, row in df_forecast.iterrows():
        demand[t_idx][(row["Customer"], row["SKU"])] = float(row[dc])

t_build_start = time.time()

problem = cplex.Cplex()
problem.set_log_stream(None)
problem.set_warning_stream(None)
problem.set_results_stream(None)
problem.objective.set_sense(problem.objective.sense.minimize)
problem.parameters.mip.tolerances.mipgap.set(0.005)
problem.parameters.timelimit.set(1800)

vc = 0
vi = {}

# y + open_new + w
for t in range(T):
    for wh in rdc_names:
        for prefix, oc in [("y",0),("open_new",open_cost.get(wh,0))]:
            vn = f"{prefix}_{t}_{wh}"
            problem.variables.add(obj=[oc], lb=[0], ub=[1], types=["B"], names=[vn])
            vi[vn] = vc; vc += 1
        vn = f"w_{t}_{wh}"
        problem.variables.add(obj=[1.5-0.8*proc_cost.get(wh,0)], lb=[0], ub=[1], types=["B"], names=[vn])
        vi[vn] = vc; vc += 1

# u + f + v
for t in range(T):
    for (c,s), qty in demand[t].items():
        for wh in [port_cdc]+rdc_names if s=="im" else [inland_cdc]+rdc_names:
            vn = f"u_{t}_{wh}_{c}_{s}"
            d = dist.get((wh,c),0); l = loss_cost_matrix.get((wh,c),0); p = 2*proc_cost.get(wh,0)
            problem.variables.add(obj=[1.45e-4*d*qty+l*qty+p*qty], lb=[0], ub=[1], types=["B"], names=[vn])
            vi[vn] = vc; vc += 1
        vn = f"v_{t}_{c}_{s}"
        problem.variables.add(obj=[0], lb=[0], ub=[1], types=["B"], names=[vn])
        vi[vn] = vc; vc += 1

    for cdc in cdc_names:
        for rdc in rdc_names:
            for s in ["im","dm"]:
                if (s=="im" and cdc==port_cdc) or (s=="dm" and cdc==inland_cdc):
                    vn = f"f_{t}_{cdc}_{rdc}_{s}"
                    d=dist.get((cdc,rdc),0); l=loss_cost_matrix.get((cdc,rdc),0); p=2*proc_cost.get(cdc,0)
                    problem.variables.add(obj=[0.9e-4*d+l+p], lb=[0], ub=[cplex.infinity], types=["C"], names=[vn])
                    vi[vn] = vc; vc += 1

build_time = time.time() - t_build_start
print(f"  建模时间: {build_time:.1f}s, 变量数: {vc}")

t_solve_start = time.time()
problem.solve()
solve_time = time.time() - t_solve_start

status = problem.solution.get_status()
obj = problem.solution.get_objective_value()
print(f"  求解时间: {solve_time:.1f}s")
print(f"  状态: {status}, 目标值: {obj:.2f}")

open_rdcs = set()
for t in range(T):
    for wh in rdc_names:
        if problem.solution.get_values(vi[f"y_{t}_{wh}"]) > 0.5:
            open_rdcs.add(wh)
print(f"  开仓数: {len(open_rdcs)}")
print(f"  仓库: {sorted(open_rdcs)}")
print(f"  总时间: {time.time()-t0:.1f}s")
'''],
    capture_output=True, text=True, timeout=3600
)

print(result.stdout)
if result.stderr:
    # 只打印非CPLEX日志的stderr
    for line in result.stderr.split('\n'):
        if line and 'CPXPARAM' not in line and 'Tried aggregator' not in line:
            print(f"  stderr: {line}")
