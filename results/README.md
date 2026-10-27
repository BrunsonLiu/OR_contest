# 结果导航

## 当前通过验收的 v2 记录

| 实验 | 已验收范围 | 验证文件 |
| --- | --- | --- |
| `engineering-v2-20261015` | 问题一工程链路及该次解的数值核算，不代表全题最终实验完成 | `validation/integrity.json`、`validation/model_checks.json` |
| `final-forecast-20261015` | 固定九方法、四窗口回测，36 份预测完整性、RMSE 与排名核查 | `validation/integrity.json`、`validation/backtest.json` |
| `final-q2-loss-20261015` | 声明末段时效假设下的问题二损耗模型；需求、流量、容量、233 条损耗明细、采购折扣与成本核对 | `validation/integrity.json`、`validation/model_checks.json` |
| `final-q2-subsidy-20261022` | 修复补贴开关后，有/无补贴两套完整策略及企业、社会成本独立核算；沿用现有补贴解释 | `validation/integrity.json`、`validation/model_checks.json` |

正式回测只使用 23 天历史，窗口重叠；不据此宣称普遍最优方法。MLP 未收敛提示保留在压缩日志中。问题二时效扫描、问题四和论文验收仍需对应证据；旧目录不追认为 v2。

`acceptance-q2-loss-20261015` 是补齐仓库采购决策前的本轮运行，完整记录保留，但折扣分配缺少决策证据，不列为完整数值验收。其后的 `final-q2-loss-20261015` 补齐导出并重新求解，未覆盖前一实验。

数据文件和既有结果按内容校验，搬动前后完全一致。新运行的输出按题号归档。

| 目录 | 内容 |
| --- | --- |
| `question1/` | 基础仓网结果及图片 |
| `question2/` | 时效、补贴和损耗分析 |
| `question3/` | 预测、模型比较与特征分析 |
| `question4/problem4_noloss/` | 多日无损耗实验 |
| `question4/problem4_loss/` | 历史有损耗实验，须显式选择 legacy；生成参数未知 |
| `question4/problem4_loss_v2/` | 有损耗求解和绘图的默认目录；目录内既有文件仍为历史结果 |
| `question4/problem4_robust/` | 历史鲁棒优化目录；`robust_results.json` 等旧结论已作废，仅作追溯，见下方说明。当前鲁棒结果见 `experiments/robust-discount-20261015/` |

## 新审计实验

- `experiments/engineering-v2-20261015/`：工程标准 v2 的真实问题一验收，包含输入源码快照、完整压缩日志、实际求解参数、产物指纹及独立数值检查；后续实验按 [工程标准](../docs/ENGINEERING.md) 执行。

- `experiments/confirm-instance-20261027b/`：顾客确认候选的机制检查，504 个线状小实例的精确 DP。完整机制与“替代已预批准”“窗口放宽”两个冻结对照在 320 个实例上不同；`instances.csv` 504 行经独立访问顺序枚举核对 0 不符。它只说明机制会改变可交付集合，不是门店策略，也没有算法比较。`confirm-instance-20261027` 的 summary 指标命名有误，仅作冒烟记录，不引用。

- `experiments/confirm-policy-20261027/`：随机回复与拒绝分支下的策略比较，162 个实例。完整 DP 在 31 个实例上高于较好的可执行规则，最大差 0.24；差异集中在拒绝概率 0.2 的情形。跨模型核对（点质量代回 504 行确定性实例、规则不高于 DP、窗口单调）均 0 违反。不是门店策略，也不是算法比较。

- `experiments/confirm-scale-20261027/`：商品数 1—4 的扩展检查，48 个实例。完整 DP 在 26 个上高于较好的规则，最大差 0.9；差距不随商品数单调增大（n=3 最高，n=4 回落）。仍是精确 DP，不是可扩展算法。

- `experiments/confirm-multi-20261027b/`：两个缺货点、两个并发请求的线状精确 DP，12 个实例。完整 DP 只在 4 个上高于较好规则，最大差 0.5；“走完再回”规则接近完整策略，差距未比单缺货点明显放大。不是可扩展算法。

- `experiments/confirm-grid-20261027/`：4×4 网格、替代品偏离路线，所有规则都有跳过缺货点的权利；阈值规则族在同一批实例取最好值（对基线有利）。16 个实例中完整 DP 在 4 个上高于最强规则，最大差 1.0。这是目前唯一在公平基线下仍保留差距的设置，但频率仍低。

- `experiments/confirm-grid-rules-20261027/`：同一批二维实例，规则族加入等待时长、近邻/远邻、替代先取/后取、替代前最多拣 m 件（m=0—3），取族内最好组合。完整 DP **0/16** 高于规则族，最大差 0；E5 的 4/16 由规则族缺少停止选项造成。算法主张因此撤回。

- `experiments/assortment-check-20261027/`：两仓八 SKU 的选品—确认成本条件性检查。确认成本 0 时近仓、选品 0；确认成本 5 时远仓、选品 8；切换在 1.5—2.0。只说明机制可改变设计，不证明文献缺口，也不是网络设计结论。

- `experiments/confirm-shared-20261027/`：两订单争一件共享替代的四节点精确 DP，12 个实例。规则族含访问子集、访问顺序、等待时长和分配策略，完整 DP **0/12** 高于规则族。A 撤回了最后一个算法假设。

- `experiments/audit-20261015/`：本轮成本修正前的运行证据，预测评估已使用新流程。
- `experiments/audit-fixed-20261015/`：修正后的四题运行结果、验证误差、旧预测重建及逐次求解状态。
- `experiments/audit-cleanenv-20261015/`：独立环境完整问题一的许可限制复现记录。
- 原目录下的历史结果没有被覆盖，不代表已按修正模型通过验证。

- `experiments/robust-ratio-20261015/`：第二轮时效比例与 CDC 容量修正后的预算扫描，包含真实状态和 gap。

- `experiments/robust-discount-20261015/`：第三轮净成本保护修正后的 0%/5% 预算结果，保存逐日配送策略、系统采购和可独立复核的最坏净成本。

## 已保存文件

`experiments/q1-mapping-final-20261015/`：问题一字段核查后的最终绘图实验，使用修正 CSV，交付 10 张 PNG；HTML 已按用户要求移除，既有运行记录保留追溯，见 [核查报告](../docs/audits/2026-10-15/QUESTION1_FIELDS_AND_MAPS.md)。

版本核查与选择方式见 [第五轮报告](../docs/audits/2026-10-15/LOSS_VERSIONS.md)。`experiments/rolling-20261015/` 保存第四轮四窗口预测回测结果。

### question1

- [Q1-result1.xlsx](question1/Q1-result1.xlsx)
- [Q1-result2.xlsx](question1/Q1-result2.xlsx)
- [Q1-result3.xlsx](question1/Q1-result3.xlsx)
- [Q3-result.xlsx](question1/Q3-result.xlsx)：实际为问题三的历史预测交付表，保留旧位置，不是问题一输入。
- [问题1_仓库分布_地图.png](question1/问题1_仓库分布_地图.png)
- [问题1_所有备选仓库位置.png](question1/问题1_所有备选仓库位置.png)
- [问题1_综合报告_地图.png](question1/问题1_综合报告_地图.png)
- [问题1_运输网络_地图.png](question1/问题1_运输网络_地图.png)
- [问题1_运输网络_超时路径.png](question1/问题1_运输网络_超时路径.png)

### question2

- [仓→仓损耗明细文件_完整版_cplex.csv](question2/仓→仓损耗明细文件_完整版_cplex.csv)
- [仓→店损耗明细文件_完整版_cplex.csv](question2/仓→店损耗明细文件_完整版_cplex.csv)
- [仓库处置订单量文件_有补贴_cplex.csv](question2/仓库处置订单量文件_有补贴_cplex.csv)
- [仓库处置订单量文件_运输损耗_cplex.csv](question2/仓库处置订单量文件_运输损耗_cplex.csv)
- [仓网业务表现文件_运输损耗_cplex.csv](question2/仓网业务表现文件_运输损耗_cplex.csv)
- [仓网供应关系文件_有补贴_cplex.csv](question2/仓网供应关系文件_有补贴_cplex.csv)
- [仓网供应关系文件_运输损耗_cplex.csv](question2/仓网供应关系文件_运输损耗_cplex.csv)
- [开仓补贴政策对比_cplex.csv](question2/开仓补贴政策对比_cplex.csv)
- [时效与成本关系分析.csv](question2/时效与成本关系分析.csv)
- [时效与成本关系分析_摘要.csv](question2/时效与成本关系分析_摘要.csv)
- [问题2_损耗成本最高的15条路径.png](question2/问题2_损耗成本最高的15条路径.png)
- [问题2_时效与成本关系分析.png](question2/问题2_时效与成本关系分析.png)
- [问题2_运输网络_损耗成本.png](question2/问题2_运输网络_损耗成本.png)

### question3

- [city_feature_comparison.png](question3/city_feature_comparison.png)
- [data_feature_analysis/acf_by_sku.png](question3/data_feature_analysis/acf_by_sku.png)
- [data_feature_analysis/acf_representative_cities.png](question3/data_feature_analysis/acf_representative_cities.png)
- [data_feature_analysis/data_feature_analysis.png](question3/data_feature_analysis/data_feature_analysis.png)
- [data_feature_analysis/feature_analysis_results.csv](question3/data_feature_analysis/feature_analysis_results.csv)
- [multimethod_comparison.png](question3/multimethod_comparison.png)
- [SOTA_Forecast_Examples.png](question3/SOTA_Forecast_Examples.png)
- [历史订单趋势.png](question3/历史订单趋势.png)
- [多方法对比报告.md](question3/多方法对比报告.md)
- [实验对比报告_城市特征影响.md](question3/实验对比报告_城市特征影响.md)
- [订单需求量预测结果_实验一_纯时间序列.csv](question3/订单需求量预测结果_实验一_纯时间序列.csv)
- [订单需求量预测结果_实验二_加入城市特征.csv](question3/订单需求量预测结果_实验二_加入城市特征.csv)
- [订单需求量预测结果文件_sota.csv](question3/订单需求量预测结果文件_sota.csv)
- [超参数选择与多方法对比分析.md](question3/超参数选择与多方法对比分析.md)
- [预测结果_GradientBoosting.csv](question3/预测结果_GradientBoosting.csv)
- [预测结果_LightGBM.csv](question3/预测结果_LightGBM.csv)
- [预测结果_MLP.csv](question3/预测结果_MLP.csv)
- [预测结果_RandomForest.csv](question3/预测结果_RandomForest.csv)
- [预测结果_SVR.csv](question3/预测结果_SVR.csv)

### question4

- [problem4_loss/output_result/仓库处置订单量文件_2016-06-24.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-24.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-25.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-25.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-26.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-26.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-27.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-27.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-28.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-28.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-29.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-29.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-30.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-30.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-24.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-24.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-25.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-25.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-26.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-26.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-27.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-27.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-28.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-28.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-29.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-29.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-30.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-30.csv)
- [problem4_loss/output_result/仓网业务表现文件_汇总.csv](question4/problem4_loss/output_result/仓网业务表现文件_汇总.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-24.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-24.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-25.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-25.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-26.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-26.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-27.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-27.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-28.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-28.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-29.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-29.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-30.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-30.csv)
- [problem4_loss/output_result/动态路线优化可视化_问题4_有损耗.png](question4/problem4_loss/output_result/动态路线优化可视化_问题4_有损耗.png)
- [problem4_loss/output_result/每日成本变化_有损耗.png](question4/problem4_loss/output_result/每日成本变化_有损耗.png)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-24.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-24.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-25.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-25.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-26.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-26.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-27.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-27.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-28.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-28.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-29.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-29.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-30.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-30.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-24.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-24.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-25.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-25.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-26.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-26.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-27.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-27.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-28.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-28.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-29.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-29.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-30.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-30.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_汇总.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_汇总.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-24.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-24.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-25.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-25.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-26.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-26.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-27.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-27.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-28.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-28.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-29.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-29.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-30.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-30.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-24.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-24.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-25.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-25.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-26.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-26.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-27.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-27.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-28.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-28.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-29.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-29.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-30.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-30.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-24.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-24.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-25.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-25.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-26.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-26.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-27.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-27.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-28.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-28.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-29.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-29.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-30.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-30.csv)
- [problem4_noloss/output_result/仓网业务表现文件_汇总.csv](question4/problem4_noloss/output_result/仓网业务表现文件_汇总.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-24.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-24.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-25.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-25.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-26.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-26.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-27.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-27.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-28.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-28.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-29.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-29.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-30.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-30.csv)

`problem4_robust/` 为历史目录：以下 5 个文件由修正前的目标函数与旧时效口径生成，`robust_results.json` 的净成本与预算结论已作废，`first_principles_analysis.png` 把候选路线损耗率求和，不能读作每吨平均损耗。它们只作版本追溯，不作为当前结果引用；当前鲁棒结论见 `experiments/robust-discount-20261015/`。

- [problem4_robust/first_principles_analysis.png](question4/problem4_robust/first_principles_analysis.png)
- [problem4_robust/price_of_robustness.png](question4/problem4_robust/price_of_robustness.png)
- [problem4_robust/robust_results.json](question4/problem4_robust/robust_results.json)
- [problem4_robust/warehouse_comparison_map.png](question4/problem4_robust/warehouse_comparison_map.png)
- [problem4_robust/仓网业务表现文件_汇总.csv](question4/problem4_robust/仓网业务表现文件_汇总.csv)

