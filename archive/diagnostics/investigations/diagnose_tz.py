# -*- coding: utf-8 -*-
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import sys, io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd, json, os

BASE = str(_REPO_ROOT)
INPUT = os.path.join(BASE, 'data/raw')

df_customer = pd.read_csv(os.path.join(INPUT, 'df_customer.csv'))
df_order = pd.read_csv(os.path.join(INPUT, 'df_order.csv'))

# 检查tai-zhou-shi的需求
print('=== tai-zhou-shi 需求检查 ===')
tz_im = df_order[(df_order['Name']=='tai-zhou-shi') & (df_order['SKU']=='im')]
tz_dm = df_order[(df_order['Name']=='tai-zhou-shi') & (df_order['SKU']=='dm')]
print(f'  df_order中 im: {tz_im["qty"].values if len(tz_im)>0 else "不存在"}')
print(f'  df_order中 dm: {tz_dm["qty"].values if len(tz_dm)>0 else "不存在"}')

# 检查df_customer中是否有tai-zhou-shi
print(f'\n  df_customer中有tai-zhou-shi: {"tai-zhou-shi" in df_customer["Name"].tolist()}')
if "tai-zhou-shi" in df_customer["Name"].tolist():
    print(f'  Location: {df_customer[df_customer["Name"]=="tai-zhou-shi"]["Location"].values[0]}')

# 检查预测数据
forecast_file = os.path.join(BASE, 'results/question3', '订单需求量预测结果文件_sota.csv')
if os.path.exists(forecast_file):
    df_forecast = pd.read_csv(forecast_file)
    tz_forecast = df_forecast[df_forecast['Customer']=='tai-zhou-shi']
    print(f'\n  预测数据中tai-zhou-shi:')
    if len(tz_forecast) > 0:
        for _, row in tz_forecast.iterrows():
            sku = row['SKU']
            vals = [row[c] for c in df_forecast.columns if c not in ['Customer', 'SKU']]
            print(f'    {sku}: {vals}')
    else:
        print(f'    不存在')
else:
    print(f'\n  预测文件不存在: {forecast_file}')

# 检查df_matrix中是否有tai-zhou相关的数据
df_matrix = pd.read_csv(os.path.join(INPUT, 'df_matrix.csv'))
tz_matrix = df_matrix[df_matrix['From'].str.contains('tai-zhou') | df_matrix['To'].str.contains('tai-zhou')]
print(f'\n  df_matrix中tai-zhou相关记录: {len(tz_matrix)}')
if len(tz_matrix) > 0:
    print(tz_matrix.head())

# 检查df_loc中是否有tai-zhou
df_loc = pd.read_csv(os.path.join(INPUT, 'df_loc.csv'))
tz_loc = df_loc[df_loc['Location'].str.contains('tai-zhou')]
print(f'\n  df_loc中tai-zhou: {len(tz_loc)}')
if len(tz_loc) > 0:
    print(tz_loc)

# 检查df_list中是否有tai-zhou
df_list = pd.read_csv(os.path.join(INPUT, 'df_list.csv'))
tz_list = df_list[df_list.iloc[:,0].str.contains('tai-zhou', na=False)]
print(f'\n  df_list中tai-zhou: {len(tz_list)}')
if len(tz_list) > 0:
    print(tz_list)

# 检查df_customer中所有城市名
print(f'\n=== 所有客户城市 ===')
customers = df_customer['Name'].tolist()
print(f'  总数: {len(customers)}')
print(f'  前10: {customers[:10]}')

# 检查df_matrix中所有From/To
from_set = set(df_matrix['From'].tolist())
to_set = set(df_matrix['To'].tolist())
all_locs = from_set | to_set
print(f'\n  df_matrix中的位置数: {len(all_locs)}')

# 检查哪些客户城市不在df_matrix中
missing_cities = []
for c in customers:
    if c not in all_locs:
        missing_cities.append(c)
print(f'\n  不在df_matrix中的客户城市: {missing_cities}')

# 检查tai-zhou-shi在df_customer中的Location
if "tai-zhou-shi" in customers:
    loc = df_customer[df_customer['Name']=='tai-zhou-shi']['Location'].values[0]
    print(f'\n  tai-zhou-shi的Location: {loc}')
    # 检查Location是否在df_matrix中
    print(f'  Location在df_matrix中: {loc in all_locs}')
    # 检查是否有其他城市名包含tai-zhou
    tz_in_matrix = [l for l in all_locs if 'tai-zhou' in l.lower()]
    print(f'  df_matrix中包含tai-zhou的位置: {tz_in_matrix}')

# 关键检查: 确定性模型中tai-zhou-shi的u变量obj系数
print(f'\n=== 确定性模型中tai-zhou-shi的u变量 ===')
dist = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
time_matrix = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}

def calc_loss(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

loss_cost_matrix = {(f, t): calc_loss(time_matrix[(f, t)]) for f, t in time_matrix.keys()}

if os.path.exists(forecast_file):
    df_forecast = pd.read_csv(forecast_file)
    periods = df_forecast.columns[2:]
    for t_idx, period in enumerate(periods[:1]):
        for _, row in df_forecast.iterrows():
            store = row['Customer']
            sku = row['SKU']
            qty = row[period]
            if store == 'tai-zhou-shi':
                print(f'  期{t_idx}: {store}({sku}), qty={qty}')
                # 检查所有候选仓库的obj系数
                cdc_names = ['gang-kou-CDC', 'nei-lu-CDC']
                rdc_names = ['cheng-du-DC', 'dong-guan-DC', 'guang-zhou-DC', 'nan-jing-DC',
                            'qing-dao-DC', 'shang-hai-DC', 'shen-zhen-DC', 'tian-jin-DC',
                            'xi-an-DC', 'chang-sha-DC', 'zheng-zhou-DC', 'hang-zhou-DC',
                            'wu-han-DC', 'da-lian-DC', 'ha-er-bin-DC', 'bei-jing-DC',
                            'ning-bo-DC', 'chong-qing-DC']
                port_cdc = 'gang-kou-CDC'
                inland_cdc = 'nei-lu-CDC'
                eligible = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
                for wh in eligible:
                    d = dist.get((wh, store), 0)
                    t_val = time_matrix.get((wh, store), float('inf'))
                    l = loss_cost_matrix.get((wh, store), 0.0)
                    trans = 1.45e-4 * d * qty
                    loss = l * qty
                    print(f'    {wh}: dist={d}, time={t_val}, loss/ton={l:.4f}, trans_cost={trans:.4f}, loss_cost={loss:.4f}')

# 检查鲁棒模型中tai-zhou-shi的v变量
print(f'\n=== 鲁棒模型中tai-zhou-shi的v变量 ===')
print(f'  由于没有u变量, v变量无约束, 可被设为1')
print(f'  这会虚增时效满足率!')
