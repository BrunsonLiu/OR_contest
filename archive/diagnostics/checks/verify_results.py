from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import json, math

with open(r'results/question4\problem4_robust\robust_results.json', 'r', encoding='utf-8') as f:
    results = json.load(f)

r0 = results[0]
print('=== Gamma = 0% 详细分析 ===')
print('总成本: {:.4f}'.format(r0['total_cost']))
print('  运输(门): {:.4f}'.format(r0['transport_cost_customer']))
print('  运输(仓): {:.4f}'.format(r0['transport_cost_warehouse']))
print('  处置: {:.4f}'.format(r0['proc_cost_actual']))
print('  损耗: {:.4f}'.format(r0['loss_cost']))
print('  开仓: {:.4f}'.format(r0['open_cost']))
print('  智能: {:.4f}'.format(r0['smart_cost']))

print('\n仓库列表({}个):'.format(r0['num_open']))
for wh in r0['open_warehouses']:
    print('  ' + wh)

print('\n每日开仓:')
for d_key, wh_list in r0['open_by_day'].items():
    print('  第{}天: {}个'.format(d_key, len(wh_list)))

print('\n每日费用 (前3天):')
for dc in r0['daily_costs'][:3]:
    d = dc['day']
    print('  Day {}: 总={:.2f}, 运门={:.2f}, 运仓={:.2f}, 处置={:.2f}, 损耗={:.2f}'.format(
        d, dc['total_daily'], dc['transport_cust'], dc['transport_wh'], dc['proc'], dc['loss']))

total_daily = sum(dc['total_daily'] for dc in r0['daily_costs'])
print('\n每日费用合计: {:.2f}'.format(total_daily))
print('一次性费用(开仓+智能): {:.2f}'.format(r0['open_cost'] + r0['smart_cost']))
print('总计: {:.2f}'.format(total_daily + r0['open_cost'] + r0['smart_cost']))

tc = r0['transport_cost_customer'] + r0['transport_cost_warehouse'] + r0['proc_cost_actual'] + r0['loss_cost'] + r0['open_cost'] + r0['smart_cost']
print('\n算术验证: 各项之和 = {:.4f}, 报告total = {:.4f}, 差异 = {:.6f}'.format(tc, r0['total_cost'], tc - r0['total_cost']))

# 百分比分析
t = r0['total_cost']
print('\n=== 成本占比 ===')
print('运输(门): {:.1f}%'.format(r0['transport_cost_customer']/t*100))
print('运输(仓): {:.1f}%'.format(r0['transport_cost_warehouse']/t*100))
print('处置: {:.1f}%'.format(r0['proc_cost_actual']/t*100))
print('损耗: {:.1f}%'.format(r0['loss_cost']/t*100))
print('开仓: {:.1f}%'.format(r0['open_cost']/t*100))
print('智能: {:.1f}%'.format(r0['smart_cost']/t*100))

# 全部Gamma对比
print('\n=== 全部Gamma对比 ===')
header = '{:>8s} {:>12s} {:>12s} {:>12s} {:>8s}'.format('Gamma', '总成本', '损耗', '运门+仓', '开仓数')
print(header)
print('-' * 60)
for r in results:
    if r.get('status') == 'INFEASIBLE':
        print('{:>7.0%}  INFEASIBLE'.format(r['gamma']))
        continue
    print('{:>7.0%}  {:>12.4f}  {:>12.4f}  {:>12.4f}  {:>8d}'.format(
        r['gamma'], r['total_cost'], r['loss_cost'],
        r['transport_cost_customer'] + r['transport_cost_warehouse'],
        r.get('num_open', 0)))