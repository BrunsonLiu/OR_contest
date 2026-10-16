"""Standard-library provenance capture and verification for isolated experiments."""
from datetime import datetime, timezone
from contextlib import contextmanager
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile


@contextmanager
def experiment_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    path = root/".experiment.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(str(os.getpid()))
    try:
        yield
    finally:
        path.unlink()


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_record(path, record):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def output_inventory(root):
    return {path.relative_to(root).as_posix(): fingerprint(path)
            for path in sorted(root.rglob("*")) if path.is_file()
            and "_runs" not in path.relative_to(root).parts and path.name != ".experiment.lock"}


def capture(root, result_root, run_folder, forecast, args):
    def git(*arguments):
        process = subprocess.run(["git", *arguments], cwd=root, capture_output=True)
        return process.stdout.decode("utf-8", errors="replace").strip() if process.returncode == 0 else None

    inputs = {}
    snapshot = run_folder / "snapshot.zip"
    with zipfile.ZipFile(snapshot, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        sources = [root/"run.py"]
        sources += sorted((root/"src").rglob("*.py"))
        sources += sorted(path for folder in ("data/raw", "requirements")
                          for path in (root/folder).rglob("*") if path.is_file())
        for path in sources:
            name = path.relative_to(root).as_posix()
            content = path.read_bytes()
            bundle.writestr(name, content)
            inputs[name] = hashlib.sha256(content).hexdigest()
        if forecast.is_file():
            content = forecast.read_bytes()
            bundle.writestr("inputs/forecast.csv", content)
            inputs["inputs/forecast.csv"] = hashlib.sha256(content).hexdigest()
        # Existing tabular results can be inputs to later plotting/comparison tasks.
        for path in sorted(result_root.rglob("*")):
            if path.is_file() and path.suffix.lower() in (".csv", ".json") and "_runs" not in path.relative_to(result_root).parts:
                name = "inputs/prior_results/" + path.relative_to(result_root).as_posix()
                content = path.read_bytes()
                bundle.writestr(name, content)
                inputs[name] = hashlib.sha256(content).hexdigest()
    return {
        "schema_version": 2, "purpose": args.purpose.strip(),
        "command": [sys.executable, str(root/"run.py"), *sys.argv[1:]],
        "arguments": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "git": {"commit": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
                "status": git("status", "--porcelain"),
                "note": "The snapshot is authoritative for dirty or untracked source; Git commit alone is insufficient."},
        "environment": {"platform": platform.platform(), "executable": sys.executable,
                        "packages": sorted({f"{item.metadata['Name']}=={item.version}" for item in importlib.metadata.distributions()})},
        "snapshot": {"file": "snapshot.zip", "sha256": fingerprint(snapshot), "members": inputs},
        "outputs_before": output_inventory(result_root), "status": "running",
    }


def finalize(record, result_root, run_folder, source_root):
    after = output_inventory(result_root)
    before = record["outputs_before"]
    record["artifacts"] = [{"path": name, "sha256": digest,
                            "change": "modified" if name in before else "created"}
                           for name, digest in after.items() if before.get(name) != digest]
    record["removed_outputs"] = sorted(set(before)-set(after))
    record["changed_source_or_inputs"] = [name for name, digest in record["snapshot"]["members"].items()
                                         if not name.startswith("inputs/")
                                         and (not (source_root/name).is_file() or fingerprint(source_root/name) != digest)]
    forecast = Path(record["forecast_file"])
    if record.get("forecast_sha256") and (not forecast.is_file() or fingerprint(forecast) != record["forecast_sha256"]):
        record["changed_source_or_inputs"].append("inputs/forecast.csv")
    log = run_folder/"output.log"
    compressed = run_folder/"output.log.gz"
    # Preserve the complete log in a Git-friendly file; raw *.log remain ignored.
    with compressed.open("wb") as target:
        target.write(gzip.compress(log.read_bytes(), mtime=0))
    record["log"] = {"file": compressed.name, "sha256": fingerprint(compressed)}
    evidence = run_folder/"solver_metrics.jsonl"
    if evidence.is_file():
        record["solver_evidence"] = {"file": evidence.name, "sha256": fingerprint(evidence)}
    record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()


def verify_record(manifest, require_success=False):
    record = json.loads(manifest.read_text(encoding="utf-8"))
    if record.get("schema_version") != 2:
        raise ValueError("旧实验缺少完整工程记录；不能追认为通过新标准")
    if record["status"] == "running" or "finished_at_utc" not in record:
        raise ValueError("实验尚未完成或异常中断，需检查进程与日志")
    if require_success and record["status"] != "completed":
        raise ValueError(f"实验未完整成功: {record['status']}")
    folder = manifest.parent
    root = folder.parent.parent

    def check_file(base, name, digest):
        path = (base/name).resolve()
        if not path.is_relative_to(base.resolve()) or not path.is_file() or fingerprint(path) != digest:
            raise ValueError(f"文件缺失、越界或指纹不一致: {name}")
        return path

    snapshot = record["snapshot"]
    archive = check_file(folder, snapshot["file"], snapshot["sha256"])
    with zipfile.ZipFile(archive) as bundle:
        if set(bundle.namelist()) != set(snapshot["members"]):
            raise ValueError("快照内容清单不一致")
        if not snapshot["members"]:
            # A record that bundles no source/input is not verified evidence;
            # an empty snapshot must not read as an integrity pass.
            raise ValueError("快照没有成员文件，不能把零项证据判为通过")
        for name, digest in snapshot["members"].items():
            if hashlib.sha256(bundle.read(name)).hexdigest() != digest:
                raise ValueError(f"快照输入损坏: {name}")
    check_file(folder, record["log"]["file"], record["log"]["sha256"])
    for item in record["artifacts"]:
        check_file(root, item["path"], item["sha256"])
    if "solver_evidence" in record:
        item = record["solver_evidence"]
        check_file(folder, item["file"], item["sha256"])
    return {"status": record["status"], "purpose": record["purpose"],
            "snapshot_files": len(snapshot["members"]), "artifacts": len(record["artifacts"]),
            "integrity": "verified", "scientific_validation": "Requires task-specific model/data checks."}
