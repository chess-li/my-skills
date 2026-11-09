import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "run_evidence.py"


class RunEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.input = self.root / "source.txt"
        self.input.write_text("before\n", encoding="utf-8")
        self.evidence = self.root / "results" / "run.json"

    def tearDown(self):
        self.temp.cleanup()

    def run_command(self, command, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "run", "--root", str(self.root), "--output", str(self.evidence), *args, "--", *command],
            capture_output=True,
            text=True,
            check=False,
        )

    def record(self):
        return json.loads(self.evidence.read_text(encoding="utf-8"))

    def test_successful_run_records_argv_criteria_output_and_current_input(self):
        result = self.run_command(
            [sys.executable, "-c", "print('hello')"], "--criterion", "AC-1"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.record()
        self.assertEqual(record["runResult"], "passed")
        self.assertEqual(record["inputFreshness"], "current")
        self.assertEqual(record["criteria"], ["AC-1"])
        self.assertEqual(record["command"]["argv"][-2:], ["-c", "print('hello')"])
        self.assertEqual(record["stdout"], "hello\n")
        self.assertTrue(record["startedAtUtc"])
        self.assertTrue(record["endedAtUtc"])

    def test_evidence_inside_git_root_does_not_make_unchanged_run_stale(self):
        result = self.run_command([sys.executable, "-c", "print('ok')"])

        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.record()
        self.assertEqual(record["inputFreshness"], "current")
        self.assertIn("results/run.json", record["inputScope"]["excluded"])

        verified = subprocess.run(
            [sys.executable, str(SCRIPT), "verify", "--root", str(self.root), str(self.evidence)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertEqual(json.loads(verified.stdout)["status"], "current")

    def test_failed_run_keeps_exit_status_and_both_streams(self):
        result = self.run_command(
            [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(7)"]
        )

        self.assertEqual(result.returncode, 7)
        record = self.record()
        self.assertEqual(record["runResult"], "failed")
        self.assertEqual(record["exitCode"], 7)
        self.assertEqual(record["stdout"], "out\n")
        self.assertEqual(record["stderr"], "err\n")

    def test_changed_input_marks_run_stale_and_verify_reports_currentness(self):
        command = [sys.executable, "-c", "from pathlib import Path; Path('source.txt').write_text('after\\n')"]
        result = self.run_command(command)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.record()["inputFreshness"], "stale")
        verified = subprocess.run(
            [sys.executable, str(SCRIPT), "verify", "--root", str(self.root), str(self.evidence)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(verified.returncode, 1)
        self.assertIn('"status": "stale"', verified.stdout)

    def test_verify_preserves_run_staleness_when_git_inputs_changed_during_command(self):
        output = self.root.parent / f"{self.root.name}-external.json"
        command = [sys.executable, "-c", "from pathlib import Path; Path('source.txt').write_text('after\\n')"]
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "run", "--root", str(self.root), "--output", str(output), "--", *command],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(record["inputFreshness"], "stale")

            verified = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--root", str(self.root), str(output)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(verified.returncode, 1)
            report = json.loads(verified.stdout)
            self.assertEqual(report["initialInputFreshness"], "stale")
            self.assertEqual(report["inputStatus"], "stale")
            self.assertEqual(report["status"], "stale")
        finally:
            output.unlink(missing_ok=True)

    def test_verify_preserves_run_staleness_for_explicit_scope(self):
        output = self.root.parent / f"{self.root.name}-explicit-external.json"
        command = [sys.executable, "-c", "from pathlib import Path; Path('source.txt').write_text('after\\n')"]
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--root",
                    str(self.root),
                    "--output",
                    str(output),
                    "--input",
                    "source.txt",
                    "--",
                    *command,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(record["inputFreshness"], "stale")

            verified = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--root", str(self.root), str(output)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(verified.returncode, 1)
            report = json.loads(verified.stdout)
            self.assertEqual(report["initialInputFreshness"], "stale")
            self.assertEqual(report["inputStatus"], "stale")
            self.assertEqual(report["status"], "stale")
        finally:
            output.unlink(missing_ok=True)

    def test_timeout_keeps_evidence(self):
        result = self.run_command(
            [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(2)"],
            "--timeout",
            "0.1",
        )

        self.assertEqual(result.returncode, 124)
        self.assertTrue(self.evidence.is_file())
        self.assertEqual(self.record()["runResult"], "timed-out")
        self.assertIn("started", self.record()["stdout"])

    def test_timeout_cleans_up_descendant_holding_output_pipes_after_parent_exits(self):
        started = time.monotonic()
        result = self.run_command(
            [
                sys.executable,
                "-c",
                "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(3)'])",
            ],
            "--timeout",
            "0.1",
        )

        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertLess(elapsed, 2.0, f"timeout cleanup waited {elapsed:.2f}s for a descendant")
        self.assertEqual(self.record()["runResult"], "timed-out")

    def test_sigterm_keeps_interrupted_evidence(self):
        process = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "run",
                "--root",
                str(self.root),
                "--output",
                str(self.evidence),
                "--",
                sys.executable,
                "-c",
                "import time; print('started', flush=True); time.sleep(5)",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            time.sleep(0.3)
            process.terminate()
            _, stderr = process.communicate(timeout=4)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

        self.assertEqual(process.returncode, 143, stderr)
        self.assertTrue(self.evidence.is_file())
        self.assertEqual(self.record()["runResult"], "interrupted")
        self.assertIn("started", self.record()["stdout"])


if __name__ == "__main__":
    unittest.main()
