"""Check layout, task targets, syntax, and static project-root references."""
import ast
from pathlib import Path
import warnings

ROOT = Path(__file__).resolve().parents[1]
INCOMPLETE = ROOT / "archive/diagnostics/incomplete"


def check():
    errors = []
    for folder in ("src/solvers", "src/analysis", "src/visualization", "data/raw",
                   "results/question1", "results/question2", "results/question3",
                   "results/question4", "docs", "archive/diagnostics", "requirements"):
        if not (ROOT / folder).is_dir():
            errors.append(f"缺少目录：{folder}")
    launcher = ast.parse((ROOT / "run.py").read_text(encoding="utf-8"))
    tasks = ast.literal_eval(next(node.value for node in launcher.body if isinstance(node, ast.Assign)
                                 and any(isinstance(target, ast.Name) and target.id == "TASKS" for target in node.targets)))
    if not tasks:
        # An empty task table makes the entry-existence check assert nothing.
        errors.append("run.py 的 TASKS 为空，任务入口检查失效")
    for task, target in tasks.items():
        if not (ROOT / target).is_file():
            errors.append(f"任务 {task} 的入口不存在：{target}")
    checked = 0
    historical = []
    for folder in ("src", "archive", "tools"):
        for path in (ROOT / folder).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path.is_relative_to(INCOMPLETE):
                historical.append(path.relative_to(ROOT).as_posix())
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            except SyntaxError as exc:
                errors.append(f"语法错误：{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
                continue
            checked += 1
            for node in ast.walk(tree):
                if (folder == "src" and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("savefig", "render") and node.args
                        and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                        and not Path(node.args[0].value).is_absolute()):
                    errors.append(f"图表输出未使用实验目录：{path.relative_to(ROOT)}:{node.lineno}")
                # Source-file references must follow the directory migration.
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    value = node.value
                    if value.startswith("src/") and value.endswith(".py") and "\n" not in value:
                        if not (ROOT / value).is_file():
                            errors.append(f"源码引用不存在：{path.relative_to(ROOT)} → {value}")
                    if value.startswith("data/raw/") and "\n" not in value:
                        if not (ROOT / value).exists():
                            errors.append(f"输入引用不存在：{path.relative_to(ROOT)} → {value}")
            if folder == "src" and path.name not in ("runtime.py", "forecasting.py", "robust_support.py", "backtesting.py", "timeliness.py", "geography.py", "experiment_tracking.py", "subsidy_support.py"):
                for node in tree.body:
                    if isinstance(node, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "_REPO_ROOT"
                        for target in node.targets
                    ):
                        # Evaluate only the known root locator, never solver imports.
                        expected = 'next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())'
                        if ast.dump(node.value) != ast.dump(ast.parse(expected, mode="eval").body):
                            errors.append(f"根目录定位方式不一致：{path.relative_to(ROOT)}")
                        break
                else:
                    errors.append(f"缺少项目根目录定位：{path.relative_to(ROOT)}")
    for message in errors:
        print("FAIL", message)
    print(f"检查 {checked} 个脚本、{len(tasks)} 个任务；错误 {len(errors)} 个。")
    for path in historical:
        print(f"历史未完成脚本（不计为通过）：{path}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(check())
