import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from src.experiment_tracking import experiment_lock, verify_record
from src.runtime import ROOT


class ExperimentTrackingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)/"project"
        (self.root/"src").mkdir(parents=True)
        (self.root/"data/raw").mkdir(parents=True)
        (self.root/"data/raw/input.csv").write_text("value\n7\n", encoding="utf-8")
        shutil.copyfile(ROOT/"run.py", self.root/"run.py")
        shutil.copyfile(ROOT/"src/experiment_tracking.py", self.root/"src/experiment_tracking.py")

    def run_probe(self, source, *options, purpose=True):
        (self.root/"src/probe.py").write_text(source, encoding="utf-8")
        command = [sys.executable, str(self.root/"run.py"), "--script", "src/probe.py"]
        if purpose:
            command += ["--purpose", "Exercise engineering contract"]
        return subprocess.run(command+list(options), cwd=self.temporary.name, capture_output=True,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8", "OR_SOLVER_GAP": "0.77"})

    def manifest(self):
        return next((self.root/"results/experiments").glob("*/_runs/probe/run.json"))

    def test_snapshot_log_auto_directory_and_tamper_detection(self):
        source = "import os\nfrom pathlib import Path\nassert 'OR_SOLVER_GAP' not in os.environ\nprint('complete log')\n(Path(os.environ['OR_RESULTS_ROOT'])/'answer.txt').write_text('7')\n"
        process = self.run_probe(source)
        self.assertEqual(process.returncode, 0, process.stdout+process.stderr)
        manifest = self.manifest()
        result = verify_record(manifest, require_success=True)
        self.assertEqual(result["artifacts"], 1)
        record = json.loads(manifest.read_text(encoding="utf-8"))
        with zipfile.ZipFile(manifest.parent/"snapshot.zip") as bundle:
            self.assertEqual(bundle.read("src/probe.py"), (self.root/"src/probe.py").read_bytes())
            self.assertEqual(bundle.read("data/raw/input.csv"), (self.root/"data/raw/input.csv").read_bytes())
        self.assertIn(b"complete log", gzip.decompress((manifest.parent/"output.log.gz").read_bytes()))
        (manifest.parent.parent.parent/"answer.txt").write_text("tampered")
        with self.assertRaises(ValueError):
            verify_record(manifest)
        self.assertEqual(record["status"], "completed")

    def test_failure_and_timeout_are_complete_auditable_records(self):
        for source, options, expected in (("raise RuntimeError('deliberate failure')", (), "failed"),
                                           ("import time\ntime.sleep(10)", ("--timeout", "0.05"), "timeout")):
            with self.subTest(expected=expected):
                process = self.run_probe(source, *options)
                self.assertNotEqual(process.returncode, 0)
                manifests = list((self.root/"results/experiments").glob("*/_runs/probe/run.json"))
                manifest = next(path for path in manifests if json.loads(path.read_text(encoding="utf-8"))["status"] == expected)
                self.assertEqual(verify_record(manifest)["status"], expected)
                with self.assertRaises(ValueError):
                    verify_record(manifest, require_success=True)

    def test_purpose_is_required_without_creating_an_experiment(self):
        process = self.run_probe("print('must not run')", purpose=False)
        self.assertEqual(process.returncode, 2)
        self.assertFalse((self.root/"results").exists())

    def test_input_changes_during_execution_are_not_success(self):
        process = self.run_probe("from pathlib import Path\nPath('data/raw/input.csv').write_text('changed')\n")
        self.assertEqual(process.returncode, 3)
        record = json.loads(self.manifest().read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "source_or_inputs_changed")
        self.assertIn("data/raw/input.csv", record["changed_source_or_inputs"])

    def test_lock_excludes_concurrent_writers_and_is_released(self):
        root = self.root/"results/experiments/shared"
        with experiment_lock(root):
            with self.assertRaises(FileExistsError):
                with experiment_lock(root):
                    self.fail("Concurrent writer admitted")
        self.assertFalse((root/".experiment.lock").exists())

    def test_old_or_incomplete_records_are_not_certified(self):
        path = self.root/"run.json"
        for record in ({"status": "completed"}, {"schema_version": 2, "status": "running"}):
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_record(path)

    def test_script_solver_without_evidence_cannot_report_success(self):
        folder = self.root/"src/solvers/question1"
        folder.mkdir(parents=True)
        (folder/"solver.py").write_text("print('no solver evidence')", encoding="utf-8")
        process = subprocess.run([sys.executable, str(self.root/"run.py"), "--script", "src/solvers/question1/solver.py",
                                  "--purpose", "Detect missing solver evidence"], cwd=self.temporary.name, capture_output=True)
        self.assertEqual(process.returncode, 2)
        manifest = next((self.root/"results/experiments").glob("*/_runs/solver/run.json"))
        self.assertEqual(verify_record(manifest)["status"], "no_feasible_solution")

    def test_empty_snapshot_is_not_certified_as_verified(self):
        # A manifest describing an empty snapshot must not pass integrity.
        process = self.run_probe("print('ok')")
        self.assertEqual(process.returncode, 0, process.stdout+process.stderr)
        manifest = self.manifest()
        record = json.loads(manifest.read_text(encoding="utf-8"))
        with zipfile.ZipFile(manifest.parent/"snapshot.zip", "w") as bundle:
            pass
        # Recompute the archive hash for the emptied zip so only the member list is at issue.
        import hashlib
        digest = hashlib.sha256((manifest.parent/"snapshot.zip").read_bytes()).hexdigest()
        record["snapshot"] = {"file": "snapshot.zip", "sha256": digest, "members": {}}
        manifest.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_record(manifest)

    def test_historical_output_roots_are_protected(self):
        process = self.run_probe("print('must not run')", "--output-dir", str(self.root/"results/question1"))
        self.assertEqual(process.returncode, 2)
        self.assertFalse((self.root/"results/question1").exists())
