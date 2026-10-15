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
├── requirements/           # 基础与可选绘图依赖
└── tools/                  # 仓库结构与路径检查
```

- [题目](docs/problem/题目.md)
- [论文](docs/paper/数据驱动的生鲜商品仓网配送优化.pdf)
- [运行指南](docs/RUNNING.md)
- [结果导航](results/README.md)
- [已知问题](docs/KNOWN_ISSUES.md)
- [后续待办清单](docs/TODO.md)
- [整理与验证记录](docs/maintenance/VALIDATION.md)

## 快速开始

在项目根目录安装依赖并查看任务：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements/base.txt
python run.py --list
```

```powershell
python run.py q1
python run.py q3
python run.py q4-robust
```

运行求解会更新相应结果；需要保留的实验请先备份。问题四默认使用已保存的 SOTA 预测，而非自动使用刚生成的基线预测。CPLEX 完整模型需要相应许可。

## 文件放置约定

- 求解代码按题号放入 `src/solvers/questionN/`；分析和绘图分别放入各自目录。
- 原始输入统一放在 `data/raw/`，不要混入输出文件。
- 新结果写入 `results/questionN/`；不同模型版本使用独立子目录。
- 已有问题四实验版本保留原有内部结构，版本含义见结果导航。
- 历史诊断归档到 `archive/diagnostics/`，未完成脚本单独放在 `incomplete/`。
- 论文、赛题和方法说明分别归入 `docs/` 对应子目录。

检查结构与路径：`python tools/check_repository.py`。后续工作按 [待办清单](docs/TODO.md) 的优先级推进。
