# 运行指南

所有新求解、训练、回测和绘图通过 `run.py` 启动，必须填写 `--purpose`。完整要求见 [工程标准](ENGINEERING.md)。`python run.py --list` 只列任务，不运行模型。下文命令中的 `--experiment` 名称均为示意值，不是仓库中已存在的实验；实际运行请替换为自己本次的名称。

## 环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements/lock-py312-windows.txt
python tools/check_repository.py
python -m unittest discover -s tests -v
```

版本锁已在 Windows/Python 3.12 验证。完整模型需要超出 CPLEX Community Edition 限制的许可；仅安装依赖不能保证可运行完整模型。PNG 地图需要 `requirements/visualization.txt` 中的可选依赖和底图资源，独立环境地图复现仍待完成。

不安装 CPLEX 时，本机可运行的任务限于预测与分析，求解类任务会因 `import cplex` 失败：

| 可运行（无需 CPLEX） | 需要 CPLEX 许可 | 其它 |
| --- | --- | --- |
| `q3`、`q3-city`、`q3-methods`、`q3-backtest`、`dfl-readiness`、`analyze-features`、`confirm-instance` | `q1`、`q2-time`、`q2-subsidy`、`q2-loss`、`q4-no-loss`、`q4-loss`、`q4-robust` | `plot-comparison` 读取既有 CPLEX 输出；地图脚本另需 `cartopy` 与底图 |

## 任务与隔离

每次默认创建 `results/experiments/时间-标识/`，也可用 `--experiment 名称` 或 `--output-dir 路径` 指定。以下输出都相对于该实验根目录，不再默认写入历史结果。

| 任务 | 内容 | 输出子目录 |
| --- | --- | --- |
| `q1` | 基础仓网 | `question1/` |
| `q2-time`、`q2-subsidy`、`q2-loss` | 时效、补贴、损耗 | `question2/` |
| `q3`、`q3-city`、`q3-methods` | 预测与方法比较 | `question3/` |
| `q3-backtest` | 滚动回测 | `question3/backtests/` |
| `dfl-readiness` | DFL 时间案例盘点（不训练、不求解） | `analysis/dfl_readiness.json` |
| `q4-no-loss` | 多日无损耗 | `question4/problem4_noloss/output_result/` |
| `q4-loss` | 多日有损耗 | `question4/problem4_loss_v2/output_result/` |
| `q4-robust` | 鲁棒优化 | `question4/problem4_robust/` |
| `analyze-features` | 特征分析 | `question3/data_feature_analysis/` |
| `confirm-instance` | 顾客确认机制的小实例精确 DP（不是门店策略） | `confirm_instance/` |
| `confirm-policy` | 随机回复/拒绝下完整 DP 与两个规则的比较（不是门店策略） | `confirm_policy/` |
| `confirm-scale` | 商品数 1—4 的精确 DP 与两个规则比较（不是门店策略） | `confirm_scale/` |
| `confirm-multi` | 两个缺货点/并发请求的精确 DP 与两个规则比较（不是门店策略） | `confirm_multi/` |
| `confirm-grid` | 二维布局、带跳过权的精确 DP 与规则比较（不是门店策略） | `confirm_grid/` |
| `confirm-grid-rules` | 二维等待/顺序/停止规则族与精确 DP 比较（不是门店策略） | `confirm_grid_rules/` |
| `assortment-check` | 两仓八 SKU 的选品—确认成本最小检查（条件性） | `assortment_check/` |
| `confirm-shared` | 两订单争一件替代的精确 DP 与规则族比较（不是门店策略） | `confirm_shared/` |
| `lrp-check` | 最小冷链 LRP：直达、顺序、联合路线化（合成实例） | `lrp_check/` |
| `lrp-localsearch` | 同一局部搜索下顺序修复解与联合插入解的对照（合成实例） | `lrp_localsearch/` |
| `live-check` | 活鲜恢复—出运最小判别（2 批 1 池位，示意参数） | `live_check/` |
| `live-scale` | 活鲜 4 批规模检验（含边际贪心） | `live_scale/` |
| `live-scale6` | 活鲜 6 批指标策略检验 | `live_scale/` |
| `mlor-check` | 年龄感知 vs 年龄盲的 MLOR 最小判别（2 仓 3 店） | `mlor_check/` |
| `mlor-scale` | 3 仓 8 店的插入式年龄感知/盲对比 | `mlor_scale/` |
| `mlor-dp` | 8 店 3 仓精确子集 DP | `mlor_dp/` |
| `mlor-dp12` | 12 店 3 仓精确子集 DP | `mlor_dp/` |
| `mlor-alns` | 20 店年龄感知破坏—修复 ALNS | `mlor_alns/` |
| `mlor-validate` | 12 店 ALNS 对精确 DP 的验证 | `mlor_validate/` |
| `mlor-ablation` | 12 店 ALNS 硬可行消融 | `mlor_ablation/` |
| `mlor-sensitivity` | 8 店拒收惩罚敏感性 | `mlor_sensitivity/` |
| `mlor-figures` | 惩罚敏感性与 ALNS 消融两幅图 | `mlor_figures/` |
| `mlor-bound` | 20 店集合划分 LP 下界 | `mlor_bound/` |
| `mlor-mechanism` | 年龄×MLOR 的 2×2 机制消融 | `mlor_mechanism/` |
| `mlor-case` | 赛题真实仓网示意（3 RDC、12 城市） | `mlor_case/` |
| `mlor-tuning` | 12 店 ALNS 参数敏感性 | `mlor_tuning/` |
| `mlor-tune20` | 20 店破坏规模对比 | `mlor_tune20/` |
| `mlor-alns-large` | 20 店推荐参数（破坏 4—6）主结果 | `mlor_alns_large/` |
| `mlor-network` | 8/12 店开仓与分配差异 | `mlor_network/` |
| `mlor-policy` | 三种实用策略基线 | `mlor_policy/` |
| `mlor-dp12-ext` | 12 店精确 DP：种子 10—14 | `mlor_dp/` |
| `mlor-dp12-ext2` | 12 店精确 DP：种子 15—19 | `mlor_dp/` |
| `mlor-holdout` | 开发 0—4、测试 5—14（开发太易，未用） | `mlor_holdout/` |
| `mlor-holdout2` | 开发 5—9、测试 10—19 的 holdout 调参 | `mlor_holdout2/` |
| `plot-comparison` | 成本与求解质量比较 | `question4/problem4_robust/` |

```powershell
python run.py q1 --experiment baseline-v1 --purpose "验证基础仓网约束与成本分解" --solver-time-limit 60 --timeout 90
python run.py q3 --experiment forecast-v1 --purpose "验证基线时间留出误差并生成未来预测"
python run.py q4-loss --experiment loss-v1 --purpose "验证指定预测输入下的损耗模型" --forecast-file results/experiments/forecast-v1/question3/订单需求量预测结果文件.csv --solver-time-limit 60 --timeout 90
```

问题四未指定 `--forecast-file` 时仍使用历史 SOTA。预测格式检查日期、204 个门店/SKU、唯一性、有限非负需求。选择结果目录不会自动更换预测输入。

DFL 适用性盘点示例：`python run.py dfl-readiness --experiment dfl-readiness-v1 --purpose "核算网络级周/日案例，验收训练标签不跨留出边界"`。该任务仅检查现有历史表及日历，固定采用至少 7 天历史、最后 7 天留出的诊断协议，分别列出周/日目标案例；它不证明 DFL 有效，也不能把已用于回测的末周称为未接触测试集。采用条件见[方法说明](methodology/problem4_robust_methodology.md#7-dfl-的适用性与采用条件2026-10-22)。

顾客确认机制检查示例：`python run.py confirm-instance --experiment confirm-instance-v1 --purpose "检验回复生成任务与确认窗口是否改变可交付集合"`。该任务只跑线状小实例上的精确 DP，比较完整机制与“替代已预批准”“窗口放宽”两个冻结对照；不是门店策略，也不含真实回复数据。独立枚举核对：`python tools/verify_confirm_instances.py results/experiments/<名称>/confirm_instance/instances.csv --report results/experiments/<名称>/validation/instance_check.json`。

顾客确认策略比较示例：`python run.py confirm-policy --experiment confirm-policy-v1 --purpose "随机回复与拒绝下比较完整 DP 与自挂起、继续拣货规则"`。它在线状小实例上算期望可交付价值，不训练、不声称门店效果。跨模型核对：`python tools/verify_confirm_policy.py results/experiments/<名称>/confirm_policy/policies.csv results/experiments/<实例名称>/confirm_instance/instances.csv --report results/experiments/<名称>/validation/policy_check.json`。

商品数扩展示例：`python run.py confirm-scale --experiment confirm-scale-v1 --purpose "检查商品数增加时完整策略与两个规则的差距"`。期限按各实例最后货架位置收紧；仍是精确 DP，不是可扩展算法。

两个缺货点示例：`python run.py confirm-multi --experiment confirm-multi-v1 --purpose "检查两个并发待回复请求下完整策略与两个规则的差距"`。六个节点的线状精确 DP，不是门店策略。

二维布局示例：`python run.py confirm-grid --experiment confirm-grid-v1 --purpose "给所有规则同样的跳过缺货点权利后，比较完整 DP 与阈值规则"`。4×4 网格、替代品偏离路线；阈值规则族在同批实例上取最好值，对基线有利。

二维规则族示例：`python run.py confirm-grid-rules --experiment confirm-grid-rules-v1 --purpose "加入等待时长、顺序和替代前停止选项后，完整 DP 是否仍高于规则族"`。规则族在同批实例上取最好组合。

选品—确认最小检查示例：`python run.py assortment-check --experiment assortment-check-v1 --purpose "确认成本变化是否改变最优仓库与选品宽度"`。两仓八 SKU 的解析枚举，条件性机制检查，不是网络设计结论。

共享替代示例：`python run.py confirm-shared --experiment confirm-shared-v1 --purpose "两个订单争一件替代时，规则族是否被完整 DP 追平"`。四节点精确 DP，规则族含访问子集、顺序、等待和分配。

最小 LRP 示例：`python run.py lrp-check --experiment lrp-check-v1 --purpose "路线化是否改变开仓/分配，95% 预算是否被选择性使用"`。合成四店实例，只作机制检查，不是赛题结论。

局部搜索对照示例：`python run.py lrp-localsearch --experiment lrp-localsearch-v1 --purpose "同一局部搜索下顺序修复解与联合插入解是否仍有稳定差距"`。合成十二店实例，不是赛题结论。

活鲜判别示例：`python run.py live-check --experiment live-check-v1 --purpose "恢复优先级是否不同于先到、状态最差和 EDD"`。2 批 1 池位示意实例，不是现场结论。

MLOR 判别示例：`python run.py mlor-check --experiment mlor-check-v1 --purpose "年龄盲是否会把高 MLOR 店派给老仓，执行时剩余不足"`。2 仓 3 店示意实例，不是现场结论。

MLOR 精确 DP 示例：`python run.py mlor-dp --experiment mlor-dp-v1 --purpose "8 店 3 仓下年龄感知与年龄盲的实际成本对比"`。合成实例，不是现场结论。

MLOR 12 店 DP 示例：`python run.py mlor-dp12 --experiment mlor-dp12-v1 --purpose "12 店 3 仓下年龄感知与年龄盲的实际成本对比"`。合成实例，约 19 秒/实例。

MLOR ALNS 示例：`python run.py mlor-alns --experiment mlor-alns-v1 --purpose "20 店年龄感知 ALNS 能否改进贪心初解"`。合成实例，不是最优性结论。

MLOR 验证示例：`python run.py mlor-validate --experiment mlor-validate-v1 --purpose "12 店 ALNS 离精确 DP 多远"`。依赖 `mlor-dp12-20261028` 的结果文件。

MLOR 消融示例：`python run.py mlor-ablation --experiment mlor-ablation-v1 --purpose "12 店硬可行 ALNS 的部件消融"`。依赖 `mlor-dp12-20261028` 的结果文件。

MLOR 敏感性示例：`python run.py mlor-sensitivity --experiment mlor-sensitivity-v1 --purpose "拒收惩罚从 0 到 800 时年龄感知的价值"`。8 店精确 DP，条件性结论。

MLOR 出图示例：`python run.py mlor-figures --experiment mlor-figures-v1 --purpose "惩罚敏感性与 ALNS 消融两幅图"`。依赖两个实验的 summary.json。

MLOR 下界示例：`python run.py mlor-bound --experiment mlor-bound-v1 --purpose "20 店集合划分 LP 下界与 ALNS 的差距"`。5 个种子约 9 秒。

MLOR 机制示例：`python run.py mlor-mechanism --experiment mlor-mechanism-v1 --purpose "年龄×MLOR 的 2×2 机制消融"`。8 店精确 DP，约 2 秒。

MLOR 真实仓网示意：`python run.py mlor-case --experiment mlor-case-v1 --purpose "3 个赛题 RDC、12 城市、赛题费率的年龄感知对比"`。单位需求，示意。

MLOR 参数敏感性：`python run.py mlor-tuning --experiment mlor-tuning-v1 --purpose "12 店 ALNS 迭代与破坏规模"`。依赖 `mlor-dp12-20261028`。

MLOR 20 店破坏规模：`python run.py mlor-tune20 --experiment mlor-tune20-v1 --purpose "默认 2-4 与 4-6 的成本对比"`。无精确基准。

MLOR 20 店主结果（推荐参数）：`python run.py mlor-alns-large --experiment mlor-alns-large-v1 --purpose "破坏 4-6 对贪心初解的主结果"`。无精确基准。

MLOR 网络设计差异：`python run.py mlor-network --experiment mlor-network-v1 --purpose "8/12 店开仓与分配差异"`。精确 DP，约 78 秒。

同实验同任务拒绝覆盖，同实验禁止并发写入。不同任务仅在输出路径不冲突时共享结果，不同模型方案使用新实验名称。归档脚本不能直接作为新实验运行。源码或原始输入运行中发生变化时，实验标记异常。

## 记录与验收

`_runs/任务/` 保存运行清单、源码/输入快照、完整压缩日志和逐次求解证据。进程启动前记录 running，结束后写终态；失败与超时也保留。

```powershell
python tools/check_experiment.py results/experiments/baseline-v1/_runs/q1/run.json --require-success --report results/experiments/baseline-v1/validation/integrity.json
python tools/audit_results.py results/experiments/baseline-v1 --report results/experiments/baseline-v1/validation/model_checks.json
```

第一条验证证据完整性，第二条独立核算模型结果。完整性不等于数学正确性。旧实验没有 v2 快照和日志时，不能追认为新标准。限时可行解、部分预算点无解和已证明不可行需区分，详看 `solver_metrics.jsonl` 的状态、界与 gap。

`audit_results.py` 支持问题二损耗模型：新结果还应包含 `仓库决策文件_运输损耗_cplex.csv`，据此独立核算开仓、采购和处理折扣。运输总额已包含损耗，单列损耗不再次计入总成本。缺少决策的旧结果会标注限制并以退出码 2 表示证据不完整；未找到支持的结果返回失败，不能以“0 个检查项”宣称通过。缺少 `_runs/q2-loss/solver_metrics.jsonl`（无法把导出总成本对到真实求解）或问题四部分每日文件缺失，同样标注限制并以退出码 2 表示，不再逐项静默跳过。运行清单缺少 `forecast_sha256` 时，无法核对预测输入，要求用 `--forecast-file` 显式提供，否则报错退出。审计报告保存检查命令、时间、校验器和原始输入指纹。

## 回测与绘图

```powershell
python run.py q3-backtest --experiment rolling-v1 --purpose "比较固定方法的滚动 RMSE 与排名稳定性" --timeout 900
python tools/verify_backtest_results.py results/experiments/rolling-v1/question3/backtests --expected-methods SeasonalNaive,LastValue,pooled_time,pooled_city,RandomForest,GradientBoosting,SVR,MLP,LightGBM --report results/experiments/rolling-v1/validation/backtest.json
python run.py --script src/visualization/visualize_problem1_images.py --experiment baseline-v1 --purpose "使用该实验 CSV 生成交付 PNG，核对图表数据源"
```

回测默认最少训练 7 天、步长 3 天、预测 7 天，尾部补齐窗口。窗口重叠，不是独立重复。城市模型按 SKU 跨城市联合训练，未来期无真实值时不宣称实际精度。

验收时必须用 `--expected-methods` 固定实际要求的方法集合，防止依赖缺失导致方法被静默跳过；该参数为必填，缺省即报错退出，不会退化成自我参照的“清单与自身一致”。工具核对完整方法/窗口网格、准确时间边界、RMSE、事件数和排名，并保存检查命令与输入/校验器指纹；报告以 `method_set_asserted` 标明是否真正断言了方法集合。禁止用 `python -O` 跳过断言。

只交付必要 PNG，HTML 入口被拒绝。地图可运行 `visualize_problem1_map.py`，超时路线可运行 `visualize_problem1_overtime.py`，同样需要实验目的。

有损耗每日成本图、路线开关图及 `plot-comparison` 默认读取 v2；仅这些图可用 `--loss-version legacy` 显式选择历史数据，不会回退读取其他实验。比较图须具备同实验的确定性和鲁棒输入。

## 专项工具范围

补贴双方案验收使用 `python tools/audit_subsidy_results.py results/experiments/实验名称 --report results/experiments/实验名称/validation/model_checks.json`。需要 `q2-subsidy` 导出的两组 `subsidy_scenarios/` 数据与两次求解证据；缺少无补贴对照不能验收。该工具独立重算运输、处置、开仓、采购、补贴、企业和社会成本，并核对对比表。当前公式为 `7*max(开仓总数-10,0)`，包括 CDC，业务解释改变时须新建实验。

- `tools/audit_question1_workbooks.py`：只读历史 Excel 和固定实验，检查字段、数量和地图证据，不改写工作簿；见 [说明](audits/2026-10-15/QUESTION1_FIELDS_AND_MAPS.md)。
- `tools/audit_timeliness_semantics.py`：固定历史 SOTA，比较末段与 CDC 起算累计时间；自定义预测暂不在该工具范围。
- `tools/verify_small_robust_model.py`：真实 CPLEX 小模型核查，可用于 Community Edition，完整模型另需许可。

专项检查输出保存在对应实验的 `validation/`，与检查命令及输入一起保留。它们不作为科学实验替代统一入口。
