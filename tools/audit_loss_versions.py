"""Inventory historical loss outputs without inventing missing run provenance."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import pandas as pd


DAYS = 7
DAILY_PREFIXES = ("仓库处置订单量文件_", "仓网业务表现文件_", "仓网供应关系文件_")
SUMMARY_NAME = "仓网业务表现文件_汇总.csv"


def audit():
    folders = {
        "legacy": ROOT/"results/question4/problem4_loss/output_result",
        "historical_v2": ROOT/"results/question4/problem4_loss_v2/output_result",
        "corrected_v2": ROOT/"results/experiments/audit-fixed-20261015/question4/problem4_loss_v2/output_result",
    }
    records = {}
    for name, folder in folders.items():
        files = {}
        for path in sorted(folder.glob("*.csv")):
            frame = pd.read_csv(path)
            files[path.name] = {"rows": len(frame), "columns": list(frame),
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        # A truncated export (fewer daily files) must not be reported as a clean
        # comparison: the file set itself is part of the evidence.
        if SUMMARY_NAME not in files:
            raise ValueError(f"{name} 缺少汇总文件 {SUMMARY_NAME}")
        for prefix in DAILY_PREFIXES:
            daily = [name for name in files if name.startswith(prefix) and name != SUMMARY_NAME]
            if len(daily) != DAYS:
                raise ValueError(f"{name} 的 {prefix} 每日文件为 {len(daily)} 个，应为 {DAYS} 个")
        summary = pd.read_csv(folder/SUMMARY_NAME)
        records[name] = {"folder": folder.relative_to(ROOT).as_posix(), "files": files,
                         "summary": summary.to_dict(orient="records")}
    first, second = records["legacy"]["files"], records["historical_v2"]["files"]
    assert set(first) == set(second), "历史版本文件集合不同，需检查完整性"
    schema_equal = all(first[name]["columns"] == second[name]["columns"] for name in first)
    return {"versions": records, "legacy_vs_historical_v2": {
        "same_file_set": True, "same_schemas": schema_equal,
        "identical_files": sum(first[name]["sha256"] == second[name]["sha256"] for name in first),
        "total_files": len(first)},
        "caveat": "Historical folders have no run manifests; their solver parameters and generating source cannot be inferred from folder names or cost differences."}


if __name__ == "__main__":
    output = ROOT/"docs/audits/2026-10-15/loss_versions.json"
    result = audit()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["legacy_vs_historical_v2"], indent=2))
