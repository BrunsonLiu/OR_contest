# 实验草案：顾客确认拣货的小实例证据

本文对应论文第五节的实验设计，只覆盖已经跑过并留证的小实例。它不是最终实验章节：没有真实回复数据，没有可扩展算法比较，也没有统计显著性。

## 1. 设计原则

- 同一信息：所有策略看到相同的回复时延分布、拒绝概率、窗口和截止。
- 同一行动：规则也允许跳过缺货点、选择等待时长；不能靠删掉基线的行动制造差距。
- 同一预算：精确 DP 与小实例规则都在同一状态空间/时间范围内计算，不比较不同信息集。
- 分开报告：机制是否有决策后果、策略是否有价值、算法是否更好，三件事不混在一起。

## 2. 实验与结果

| 编号 | 实验 | 规模 | 对照 | 结果 | 支持什么 |
| --- | --- | --- | --- | --- | --- |
| E1 | `confirm-instance-20261027b` | 504 个线状确定性实例 | 完整机制 vs 替代已预批准、窗口放宽 | 320 个实例可交付价值不同；预批准计划在 432 个实例上违约；独立枚举 504/504 一致 | 机制有决策后果，不是把等待写成常数 |
| E2 | `confirm-policy-20261027` | 162 个随机实例 | 完整 DP vs 逐点等待、走完再回 | 31 个实例完整更好，最大差 0.24；差异集中在拒绝概率 0.2 | 随机回复下简单规则不是最优 |
| E3 | `confirm-scale-20261027` | 48 个实例，商品数 1—4 | 同上 | 26 个有差异，最大 0.9；不随商品数单调 | 商品数本身不是差距来源 |
| E4 | `confirm-multi-20261027b` | 12 个双缺货实例 | 同上 | 4 个有差异，最大 0.5 | 并发请求本身没有放大差距 |
| E5 | `confirm-grid-20261027` | 16 个二维实例 | 完整 DP vs 逐点等待、走完再回、阈值规则族（含跳过权，同批调参） | 4 个有差异，最大 1.0 | 公平基线下仍有约 25% 的价值空间 |

E1 的独立核对是访问顺序枚举；E2 的跨模型核对是把点质量分布代回 E1 的 504 行，0 不符，并检查规则不高于 DP、窗口单调。E3—E5 只有完整性校验和单元测试，没有独立数值核对。

## 3. 解释边界

- 实例是线状或 4×4 网格，商品数 1—4，缺货点 1—2；不能外推到真实门店。
- 回复时延独立同分布、拒绝独立；没有顾客选择相关性、多商品共享请求或篮子效应。
- 规则未做参数训练；E5 的阈值族在同一批实例上取最好值，对基线有利，因此 4/16 是保守估计。
- 精确 DP 只在小状态空间可算；没有可扩展算法，也没有和商业求解器的比较。
- 没有真实回复/返拣日志；结果只能作条件性解释。

## 4. 尚未做的实验

1. 时点规则：访问缺货点后等 \(k\) 分钟再走、按近邻/远邻顺序，取最好 \(k\) 与顺序，检验命题 2。
2. 绕路梯度：系统改变替代品偏离路线的程度，检验命题 3（差距是否随绕路成本增加）。
3. 更多并发请求：3—5 个缺货点，精确 DP 不可算时用完美信息上界和模拟，检验状态聚合/rollout 的必要性。
4. 可扩展算法：状态聚合、rollout 或分支定界，与规则、精确 DP 在同预算下比较；没有稳定收益就不写算法贡献。
5. 真实或半真实数据：回复时延分布、窗口规则、未回复默认动作；没有就只作条件性结论。

## 5. 复现命令

```powershell
python run.py confirm-instance --experiment confirm-instance-v1 --purpose "机制检查"
python tools/verify_confirm_instances.py results/experiments/confirm-instance-v1/confirm_instance/instances.csv --report results/experiments/confirm-instance-v1/validation/instance_check.json
python run.py confirm-policy --experiment confirm-policy-v1 --purpose "随机策略比较"
python tools/verify_confirm_policy.py results/experiments/confirm-policy-v1/confirm_policy/policies.csv results/experiments/confirm-instance-v1/confirm_instance/instances.csv --report results/experiments/confirm-policy-v1/validation/policy_check.json
python run.py confirm-scale --experiment confirm-scale-v1 --purpose "商品数扩展"
python run.py confirm-multi --experiment confirm-multi-v1 --purpose "两个缺货点"
python run.py confirm-grid --experiment confirm-grid-v1 --purpose "二维公平跳过权"
```

验收：`python tools/check_experiment.py <run.json> --require-success`；提交前跑 `tools/check_repository.py`、`tools/check_line_endings.py`、`python -m unittest discover -s tests -v`。

## 6. 失败与撤回条件

- 若给基线加上同样的跳过、等待时长和顺序选择后，完整策略不再有稳定优势，撤回算法主张。
- 若二维差距不能随绕路成本或请求数增加而复现，撤回“几何/并发是困难来源”的解释。
- 若真实数据表明回复时延近似确定或替代很少发生，整个问题的实践价值下降，需重新评估选题。
