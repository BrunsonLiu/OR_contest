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
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))

cdc_names = list(df_wh[df_wh['Type'] == 'CDC']['Name'])
rdc_names = list(df_wh[df_wh['Type'] == 'RDC']['Name'])
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
customer_cities = list(df_customer['Name'])

cap = {}
proc_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost[row['Name']] = row['Processing_fee']

dist_det = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
dist_rob = {}
for _, row in df_matrix.iterrows():
    dist_rob[(row['From'], row['To'])] = row['Distance']
    dist_rob[(row['To'], row['From'])] = row['Distance']

dur_det = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}
dur_rob = {}
for _, row in df_matrix.iterrows():
    dur_rob[(row['From'], row['To'])] = row['Duration']
    dur_rob[(row['To'], row['From'])] = row['Duration']

sku_cdc = {'im': port_cdc, 'dm': inland_cdc}
cdc_sku = {port_cdc: 'im', inland_cdc: 'dm'}

LOSS_THRESHOLD = 500.0
def calc_loss(minutes):
    if minutes <= LOSS_THRESHOLD:
        return 0.0
    return 0.2 * (minutes - LOSS_THRESHOLD) ** 2 / 10000.0

print("=" * 80)
print("diagnose: det vs robust structure diff")
print("=" * 80)

print("\n[1] f vars comparison")
det_f = set()
rob_f = set()
for cdc in cdc_names:
    s = cdc_sku[cdc]
    for rdc in rdc_names:
        det_f.add(f'f_{cdc}_{rdc}_{s}')
        d = dist_rob.get((cdc, rdc), 99999)
        if d <= 5000:
            rob_f.add(f'f_{cdc}_{rdc}_{s}')
det_only_f = det_f - rob_f
print(f"  det: {len(det_f)}, rob: {len(rob_f)}, det_only: {len(det_only_f)}")
if det_only_f:
    print("  *** det-only f vars (missing in robust!): ***")
    for v in sorted(det_only_f):
        parts = v.split('_')
        cdc_n = '_'.join(parts[1:-2])
        rdc_n = '_'.join(parts[-2:-1])
        s = parts[-1]
        d_rob = dist_rob.get((cdc_n, rdc_n), 'MISSING')
        d_det = dist_det.get((cdc_n, rdc_n), dist_det.get((rdc_n, cdc_n), 'MISSING'))
        print(f"    {v}: dist_rob={d_rob}, dist_det={d_det}")

print("\n[2] u vars comparison")
det_u = set()
rob_u = set()
for s in ['im', 'dm']:
    eligible = [sku_cdc[s]] + rdc_names
    for wh in eligible:
        for c in customer_cities:
            det_u.add(f'u_{wh}_{c}_{s}')
            d = dist_rob.get((wh, c), 99999)
            if d <= 5000:
                rob_u.add(f'u_{wh}_{c}_{s}')
det_only_u = det_u - rob_u
print(f"  det: {len(det_u)}, rob: {len(rob_u)}, det_only: {len(det_only_u)}")
if det_only_u:
    print("  *** det-only u vars: ***")
    for v in sorted(det_only_u):
        parts = v.split('_')
        wh = '_'.join(parts[1:-2])
        c = '_'.join(parts[-2:-1])
        d_rob = dist_rob.get((wh, c), 'MISSING')
        print(f"    {v}: dist_rob={d_rob}")

print("\n[3] distance matrix symmetry")
asym = 0
missing_rev = 0
for (f, t), d in dist_det.items():
    rev = dist_det.get((t, f), None)
    if rev is None:
        missing_rev += 1
    elif abs(rev - d) > 1:
        asym += 1
print(f"  asymmetric: {asym}, missing_reverse: {missing_rev}")

print("\n[4] CDC->RDC loss cost diff")
for cdc in cdc_names:
    for rdc in rdc_names:
        dur_d = dur_det.get((cdc, rdc), None)
        dur_d_rev = dur_det.get((rdc, cdc), None)
        dur_r = dur_rob.get((cdc, rdc), None)
        l_det = calc_loss(dur_d) if dur_d else calc_loss(dur_d_rev) if dur_d_rev else -1
        l_rob = calc_loss(dur_r) if dur_r else -1
        if abs(l_det - l_rob) > 0.001:
            print(f"  DIFF! {cdc}->{rdc}: dur_det={dur_d}(rev={dur_d_rev}), dur_rob={dur_r}, loss_det={l_det:.4f}, loss_rob={l_rob:.4f}")

print("\n[5] RDC->customer loss cost diff")
diff_cnt = 0
for rdc in rdc_names:
    for c in customer_cities:
        dur_d = dur_det.get((rdc, c), None)
        dur_d_rev = dur_det.get((c, rdc), None)
        dur_r = dur_rob.get((rdc, c), None)
        l_det = calc_loss(dur_d) if dur_d else calc_loss(dur_d_rev) if dur_d_rev else -1
        l_rob = calc_loss(dur_r) if dur_r else -1
        if isinstance(l_det, float) and isinstance(l_rob, float) and abs(l_det - l_rob) > 0.001:
            diff_cnt += 1
            if diff_cnt <= 5:
                print(f"  DIFF! {rdc}->{c}: dur_det={dur_d}(rev={dur_d_rev}), dur_rob={dur_r}, loss_det={l_det:.4f}, loss_rob={l_rob:.4f}")
print(f"  total RDC->cust loss diffs: {diff_cnt}")

print("\n[6] CDC->customer loss cost diff")
diff_cnt = 0
for cdc in cdc_names:
    for c in customer_cities:
        dur_d = dur_det.get((cdc, c), None)
        dur_d_rev = dur_det.get((c, cdc), None)
        dur_r = dur_rob.get((cdc, c), None)
        l_det = calc_loss(dur_d) if dur_d else calc_loss(dur_d_rev) if dur_d_rev else -1
        l_rob = calc_loss(dur_r) if dur_r else -1
        if isinstance(l_det, float) and isinstance(l_rob, float) and abs(l_det - l_rob) > 0.001:
            diff_cnt += 1
            if diff_cnt <= 5:
                print(f"  DIFF! {cdc}->{c}: dur_det={dur_d}(rev={dur_d_rev}), dur_rob={dur_r}, loss_det={l_det:.4f}, loss_rob={l_rob:.4f}")
print(f"  total CDC->cust loss diffs: {diff_cnt}")

print("\n[7] w/z/y vars comparison")
det_w = set(f'w_{wh}' for wh in list(cdc_names) + rdc_names)
rob_w = set(f'w_{wh}' for wh in rdc_names)
det_z = set(f'z_{wh}' for wh in list(cdc_names) + rdc_names)
rob_z = set(f'z_{wh}' for wh in rdc_names)
det_y = set(f'y_{wh}' for wh in list(cdc_names) + rdc_names)
rob_y = set(f'y_{wh}' for wh in rdc_names)
print(f"  w vars: det={len(det_w)}(CDC+RDC), rob={len(rob_w)}(RDC only), det_only={sorted(det_w-rob_w)}")
print(f"  z vars: det={len(det_z)}(CDC+RDC), rob={len(rob_z)}(RDC only), det_only={sorted(det_z-rob_z)}")
print(f"  y vars: det={len(det_y)}(CDC+RDC), rob={len(rob_y)}(RDC only), det_only={sorted(det_y-rob_y)}")

print("\n[8] CDC capacity constraint diff")
print("  det: cap*y - sum(u*qty) - sum(f) >= 0  (y=1 for CDC)")
print("  rob: cap - sum(u*qty) - sum(f) >= 0     (no y var, CDC always open)")
print("  => EQUIVALENT for CDC (y=1)")

print("\n[9] Flow balance constraint diff")
print("  det: sum(u*qty) - f = 0  for each (rdc, sku)")
print("  rob: -f + sum(u*qty) = 0  for each (rdc, sku) where f_var exists")
print("  *** KEY: if f_var missing in robust, flow balance NOT added! ***")
if det_only_f:
    print(f"  *** {len(det_only_f)} f vars missing → flow balance skipped for those (rdc,sku) pairs! ***")
    for v in sorted(det_only_f):
        parts = v.split('_')
        rdc_n = '_'.join(parts[-2:-1])
        s = parts[-1]
        print(f"    → RDC {rdc_n} SKU {s}: no flow balance constraint!")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"  f vars diff: {len(det_only_f)} (robust missing)")
print(f"  u vars diff: {len(det_only_u)} (robust missing)")
print(f"  w/z/y: robust missing CDC vars (but CDC always open, impact on discount only)")
if det_only_f:
    print(f"  *** CRITICAL: {len(det_only_f)} missing f vars → missing flow balance → RDC can serve without transfer! ***")
