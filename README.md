# 生鲜商品仓网配送优化

仓库选址、时效与补贴、运输损耗、需求预测和多日鲁棒优化的竞赛项目。

## 目录导航

```text
or__contest/
├── run.py                  # 统一运行入口
├── src/
│   ├── solvers/            # question1～question4：四道题的求解代码
│   ├── analysis/           # 订单与预测特征分析
│   └── visualization/      # 地图、配送路径与成本绘图
├── data/raw/               # 原始输入数据
├── results/                # question1～question4：各题结果
├── docs/
│   ├── problem/            # 赛题
│   ├── paper/              # 论文与 AI 工具使用说明
│   ├── methodology/        # 鲁棒优化方法说明
│   └── maintenance/        # 整理清单与验证记录
├── archive/diagnostics/    # 历史排查：检查、对比、调查、未完成脚本
├── requirements/           # 基础、可选绘图依赖和版本锁
├── tests/                  # 预测、输入契约与入口回归检查
└── tools/                  # 仓库结构与路径检查
```

- [题目](docs/problem/题目.md)
- [论文](docs/paper/数据驱动的生鲜商品仓网配送优化.pdf)
- [运行指南](docs/RUNNING.md)
- [工程与实验标准](docs/ENGINEERING.md)
- [结果导航](results/README.md)
- [已知问题](docs/KNOWN_ISSUES.md)
- [后续待办清单](docs/TODO.md)
- [历史代码检查与修复报告](docs/audits/2026-10-15/REPORT.md)
- [第二轮：鲁棒时效与容量约束](docs/audits/2026-10-15/ROBUST_CONSTRAINTS.md)
- [第三轮：折扣与最坏净成本](docs/audits/2026-10-15/ROBUST_OBJECTIVE.md)
- [整理与验证记录](docs/maintenance/VALIDATION.md)

## 快速开始

Windows / Python 3.12 可在项目根目录安装验证过的依赖并查看任务：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements/lock-py312-windows.txt
python run.py --list
```

```powershell
python run.py q1 --experiment baseline-v1 --purpose "核对基础模型约束与成本"
python run.py q3 --experiment forecast-v1 --purpose "验证基线预测误差"
python run.py q4-robust --experiment robust-v1 --purpose "验证预算集合下的成本、容量与时效"
```

执行必须填写 `--purpose`。未指定名称时自动创建独立实验目录；同任务拒绝覆盖，同实验禁止并发写入。每次保存代码与输入快照、完整日志、参数、环境和产物指纹。问题四默认使用历史 SOTA，完整模型需要相应 CPLEX 许可。

## 文件放置约定

- 求解代码按题号放入 `src/solvers/questionN/`；分析和绘图分别放入各自目录。
- 原始输入统一放在 `data/raw/`，不要混入输出文件。
- 新结果写入 `results/experiments/实验名称/questionN/`，历史 `results/questionN/` 保留追溯。
- 已有问题四实验版本保留原有内部结构，版本含义见结果导航。
- 历史诊断归档到 `archive/diagnostics/`，未完成脚本单独放在 `incomplete/`。
- 论文、赛题和方法说明分别归入 `docs/` 对应子目录。

检查结构与路径：`python tools/check_repository.py`。后续工作按 [待办清单](docs/TODO.md) 的优先级推进。

最新检查：[多窗口预测回测与时效口径核查](docs/audits/2026-10-15/ROLLING_AND_TIME.md)。

后续核查：[有损耗版本与绘图一致性](docs/audits/2026-10-15/LOSS_VERSIONS.md)。

问题一字段与地图：[核查说明](docs/audits/2026-10-15/QUESTION1_FIELDS_AND_MAPS.md)。
