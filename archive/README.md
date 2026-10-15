# 历史脚本归档

`diagnostics/` 下的分类：

- `checks/`：约束、结果与最优性检查。
- `comparisons/`：模型、路线与求解时间对比。
- `investigations/`：根因分析与多轮差异排查，版本后缀保留。
- `incomplete/`：存在语法错误的原始脚本，仅保留历史记录。

使用 `python run.py --script archive/diagnostics/分类/文件名.py` 运行。历史脚本可能触发求解或写出图片，请先阅读其内容。源码路径已适配新目录，但涉及源码行号的诊断仍需人工核对。

`local_artifacts/` 保留整理前的 Python 缓存与系统元数据，供需要时追溯，不参与求解或检查。
