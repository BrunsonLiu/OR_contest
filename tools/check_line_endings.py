"""Assert byte-fingerprinted inputs survive any core.autocrlf setting.

Recorded SHA256 values (``run.json`` ``forecast_sha256``, ``rolling_backtest.json``
``history_sha256`` and the independent audit in ``tools/audit_results.py``) were
produced from CRLF worktree bytes on the Windows build host. ``.gitattributes``
forces ``eol=crlf`` for the fingerprinted input classes so those exact bytes are
reproduced on Linux, macOS and CI checkouts alike.

This check fails if a tracked fingerprinted input is left dependent on the
checkout's ``core.autocrlf`` setting, or if a committed record's hash no longer
matches the bytes on disk. It is the regression guard for the off-Windows
fingerprint mismatch.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

FORECAST_MARKER = "results/question3/"
# .gitattributes uses gitattributes wildmatch, where `*` does not cross `/`:
# `results/question3/*.csv` is direct children only. Mirror that here instead of
# using a git pathspec, whose `*` would also match nested directories.
def is_fingerprinted_input(name):
    if name.startswith("data/raw/"):
        return True
    return (name.startswith("results/question3/") and name.endswith(".csv")
            and name.count("/") == 2)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tracked_eol():
    process = subprocess.run(["git", "ls-files", "--eol", "-z"], cwd=ROOT, capture_output=True)
    process.check_returncode()
    entries = {}
    for entry in process.stdout.decode("utf-8").split("\0"):
        if not entry:
            continue
        meta, _, name = entry.partition("\t")
        entries[name] = meta.split()
    return entries


def check_attributes(errors):
    """Every fingerprinted input must be forced to CRLF, not merely autocrlf'd."""
    seen = 0
    for name, fields in tracked_eol().items():
        if not is_fingerprinted_input(name):
            continue
        seen += 1
        index, worktree = fields[0], fields[1]
        attribute = fields[2] if len(fields) > 2 else "attr/(none)"
        value = fields[3] if len(fields) > 3 else ""
        if attribute != "attr/text" or value != "eol=crlf":
            errors.append(f"输入未固定 CRLF 属性：{name} → {attribute} {value}".rstrip())
        if index != "i/lf":
            errors.append(f"仓库规范形态应为 LF 索引：{name} → {index}")
        if worktree != "w/crlf":
            errors.append(f"工作区应为 CRLF：{name} → {worktree}")
    if not seen:
        errors.append("未找到任何受指纹保护的输入，属性规则可能失效")


def check_history_fingerprints(errors):
    """Committed backtests must hash the same df_past_order bytes we check out."""
    raw = ROOT / "data/raw/df_past_order.csv"
    if not raw.is_file():
        errors.append("缺少输入 data/raw/df_past_order.csv")
        return
    actual = digest(raw)
    for report_path in sorted(ROOT.glob("results/experiments/*/question3/backtests/rolling_backtest.json")):
        recorded = json.loads(report_path.read_text(encoding="utf-8")).get("history_sha256")
        if recorded and recorded != actual:
            errors.append(f"历史指纹不符：{report_path.relative_to(ROOT).as_posix()}\n"
                          f"    记录 {recorded}\n    实际 {actual}")


def check_forecast_fingerprints(errors):
    """Committed run manifests must hash the same forecast bytes we check out."""
    checked = set()
    for manifest in sorted(ROOT.glob("results/experiments/*/_runs/*/run.json")):
        record = json.loads(manifest.read_text(encoding="utf-8"))
        recorded, name = record.get("forecast_sha256"), record.get("forecast_file") or ""
        name = name.replace("\\", "/")
        marker = name.find(FORECAST_MARKER)
        if not recorded or marker < 0:
            continue
        relative = name[marker:]
        if relative in checked:
            continue
        checked.add(relative)
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"记录引用的预测输入缺失：{relative}")
        elif digest(path) != recorded:
            errors.append(f"预测指纹不符：{relative}\n    记录 {recorded}\n    实际 {digest(path)}")


def check():
    errors = []
    check_attributes(errors)
    check_history_fingerprints(errors)
    check_forecast_fingerprints(errors)
    for message in errors:
        print("FAIL", message)
    print(f"换行与指纹检查完成；错误 {len(errors)} 个。")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(check())
