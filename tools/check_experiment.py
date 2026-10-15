"""Verify a complete v2 experiment record, independently of model correctness."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.experiment_tracking import fingerprint, verify_record, write_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="具体任务的 _runs/任务/run.json")
    parser.add_argument("--require-success", action="store_true", help="要求完整成功，限时或部分解不计通过")
    parser.add_argument("--report", type=Path, help="保存本次校验的命令、时间、校验器与运行清单指纹")
    args = parser.parse_args()
    try:
        result = verify_record(args.manifest.resolve(), args.require_success)
        result.update(checked_at_utc=datetime.now(timezone.utc).isoformat(), command=[sys.executable, *sys.argv],
                      manifest_sha256=fingerprint(args.manifest),
                      verifier_sha256={"tools/check_experiment.py": fingerprint(Path(__file__)),
                                       "src/experiment_tracking.py": fingerprint(ROOT/"src/experiment_tracking.py")})
        if args.report:
            if args.report.resolve() == args.manifest.resolve():
                raise ValueError("校验报告不能覆盖原始运行清单")
            args.report.parent.mkdir(parents=True, exist_ok=True)
            write_record(args.report, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
