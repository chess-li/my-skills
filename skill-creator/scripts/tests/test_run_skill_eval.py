import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "run_skill_eval.py"
REAL_CORPUS = Path(__file__).resolve().parents[2] / "tests" / "触发测试集.md"


class RunSkillEvalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "eval.json"
        self.baseline = self.root / "tree-a"
        self.candidate = self.root / "tree-b"
        for tree, marker in ((self.baseline, "A"), (self.candidate, "B")):
            tree.mkdir()
            (tree / "SKILL.md").write_text(f"marker {marker}\n", encoding="utf-8")
        self.corpus = self.root / "corpus.md"
        self.corpus.write_text(
            "# 样本\n\n"
            "- **P1**（真实返工 2026-10-01）：`打开导出`\n"
            "- **N4**（邻近任务）：`不要做`（应保持原样）\n",
            encoding="utf-8",
        )
        self.criteria = self.root / "hidden.md"
        self.criteria.write_text("HIDDEN-CRITERIA-TOKEN\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def write_script(self, name, body):
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return path

    def test_unrecognized_corpus_errors_and_does_not_invent_cases(self):
        bad = self.root / "bad.md"
        bad.write_text("# 只有说明\n\n没有可运行样本。\n", encoding="utf-8")

        result = self.command(
            "--corpus",
            str(bad),
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([sys.executable, "-c", "print('no')"]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unrecognized", result.stderr)
        self.assertFalse(self.output.exists())

    def test_case_without_source_marker_is_not_skipped(self):
        bad = self.root / "partial.md"
        bad.write_text(
            "- **P1**（有来源）：`可以`\n- **P2**：`没有来源标记`\n",
            encoding="utf-8",
        )

        result = self.command(
            "--corpus",
            str(bad),
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([sys.executable, "-c", "print('no')"]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("P2", result.stderr)
        self.assertFalse(self.output.exists())

    def test_real_corpus_runs_selected_case_without_leaking_expectation(self):
        capture = self.root / "stdin.txt"
        harness = self.write_script(
            "harness.py",
            "import os, sys\n"
            "from pathlib import Path\n"
            f"Path({str(capture)!r}).write_text(sys.stdin.read())\n"
            "print('I loaded the skill')\n",
        )

        result = self.command(
            "--corpus",
            str(REAL_CORPUS),
            "--case",
            "N4",
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([sys.executable, str(harness)]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(capture.read_text(encoding="utf-8"), "用 tdd 给这个函数补测试")
        report = json.loads(self.output.read_text(encoding="utf-8"))
        run = report["candidates"]["baseline"]["runs"][0]
        self.assertEqual(run["triggerStatus"], "unknown")
        self.assertNotIn("loaded", json.dumps(run["triggerStatus"]))
        self.assertIn("I loaded the skill", run["stdout"])

    def test_stdout_self_report_does_not_become_trigger_evidence(self):
        harness = self.write_script(
            "harness.py",
            "import sys\n"
            "sys.stdin.read()\n"
            "print('loaded skill-creator')\n",
        )

        result = self.command(
            "--corpus",
            str(self.corpus),
            "--case",
            "P1",
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([sys.executable, str(harness)]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads(self.output.read_text(encoding="utf-8"))["candidates"]["baseline"]["runs"][0]
        self.assertEqual(run["triggerStatus"], "unknown")
        self.assertEqual(run["observationStatus"], "not-observed")
        self.assertEqual(run["model"], "test-model")
        self.assertEqual(run["stdout"], "loaded skill-creator\n")

    def test_structured_host_trace_can_mark_trigger_observed(self):
        harness = self.write_script(
            "harness.py",
            "import os, sys\n"
            "from pathlib import Path\n"
            "sys.stdin.read()\n"
            "Path(os.environ['SKILL_EVAL_TRACE']).write_text("
            "'{\"loadedSkillPath\":\"/host/skills/demo\"}\\n', encoding='utf-8')\n",
        )

        result = self.command(
            "--corpus",
            str(self.corpus),
            "--case",
            "P1",
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([sys.executable, str(harness)]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads(self.output.read_text(encoding="utf-8"))["candidates"]["baseline"]["runs"][0]
        self.assertEqual(run["triggerStatus"], "observed")
        self.assertEqual(run["triggerPath"], "/host/skills/demo")
        self.assertEqual(run["input"], "打开导出")
        trace_file = Path(run["traceFile"])
        self.assertTrue(trace_file.is_file())
        self.assertEqual(json.loads(trace_file.read_text(encoding="utf-8"))["loadedSkillPath"], "/host/skills/demo")

    def test_plain_text_trace_stays_unknown(self):
        harness = self.write_script(
            "harness.py",
            "import os, sys\n"
            "from pathlib import Path\n"
            "sys.stdin.read()\n"
            "Path(os.environ['SKILL_EVAL_TRACE']).write_text('I loaded the skill\\n', encoding='utf-8')\n",
        )

        result = self.command(
            "--corpus",
            str(self.corpus),
            "--case",
            "P1",
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([sys.executable, str(harness)]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads(self.output.read_text(encoding="utf-8"))["candidates"]["baseline"]["runs"][0]
        self.assertEqual(run["triggerStatus"], "unknown")

    def test_missing_harness_is_environment_blocked_not_task_failed(self):
        result = self.command(
            "--corpus",
            str(self.corpus),
            "--case",
            "P1",
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([str(self.root / "missing-harness")]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads(self.output.read_text(encoding="utf-8"))["candidates"]["baseline"]["runs"][0]
        self.assertEqual(run["runStatus"], "environment-blocked")
        self.assertNotEqual(run["runStatus"], "task-failed")

    def test_environment_block_does_not_ask_judge_to_score_empty_output(self):
        judge = self.write_script(
            "judge.py",
            "import sys\n"
            "sys.stdin.read()\n"
            "print('{\"observation\":\"failed\"}')\n",
        )

        result = self.command(
            "--corpus",
            str(self.corpus),
            "--case",
            "P1",
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([str(self.root / "missing-harness")]),
            "--judge-argv-json",
            json.dumps([sys.executable, str(judge)]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads(self.output.read_text(encoding="utf-8"))["candidates"]["baseline"]["runs"][0]
        self.assertEqual(run["runStatus"], "environment-blocked")
        self.assertEqual(run["observationStatus"], "not-observed")

    def test_nonzero_exit_is_task_failed_and_records_streams(self):
        harness = self.write_script(
            "harness.py",
            "import sys\n"
            "print(sys.stdin.read())\n"
            "print('bad', file=sys.stderr)\n"
            "raise SystemExit(3)\n",
        )

        result = self.command(
            "--corpus",
            str(self.corpus),
            "--case",
            "P1",
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([sys.executable, str(harness)]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads(self.output.read_text(encoding="utf-8"))["candidates"]["baseline"]["runs"][0]
        self.assertEqual(run["runStatus"], "task-failed")
        self.assertEqual(run["exitCode"], 3)
        self.assertEqual(run["stdout"], "打开导出\n")
        self.assertEqual(run["stderr"], "bad\n")
        self.assertEqual(run["harnessArgv"], [sys.executable, str(harness)])
        self.assertEqual(len(run["contentHash"]), 64)

    def test_judge_sees_hidden_criteria_and_anonymous_labels_only(self):
        harness_capture = self.root / "harness-stdin.txt"
        judge_capture = self.root / "judge-stdin.txt"
        harness = self.write_script(
            "harness.py",
            "import sys\n"
            "from pathlib import Path\n"
            f"Path({str(harness_capture)!r}).write_text(sys.stdin.read())\n"
            "print('candidate-output')\n",
        )
        judge = self.write_script(
            "judge.py",
            "import sys\n"
            "from pathlib import Path\n"
            f"Path({str(judge_capture)!r}).write_text(sys.stdin.read())\n"
            "print('{\"observation\":\"passed\"}')\n",
        )

        result = self.command(
            "--corpus",
            str(self.corpus),
            "--case",
            "P1",
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--candidate",
            f"next={self.candidate}",
            "--baseline",
            "baseline",
            "--criteria",
            str(self.criteria),
            "--blind-seed",
            "7",
            "--harness-argv-json",
            json.dumps([sys.executable, str(harness)]),
            "--judge-argv-json",
            json.dumps([sys.executable, str(judge)]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        harness_text = harness_capture.read_text(encoding="utf-8")
        self.assertNotIn("HIDDEN-CRITERIA-TOKEN", harness_text)
        self.assertNotIn("baseline", harness_text)
        judge_text = judge_capture.read_text(encoding="utf-8")
        judge_payload = json.loads(judge_text)
        self.assertIn(judge_payload["label"], {"A", "B"})
        self.assertNotIn("baseline", judge_text)
        self.assertNotIn("next", judge_text)
        self.assertIn("HIDDEN-CRITERIA-TOKEN", judge_payload["criteria"])
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(report["baseline"], "baseline")
        self.assertEqual(report["coverage"]["selected"], ["P1"])
        self.assertEqual(report["coverage"]["ran"], ["P1"])
        self.assertEqual(set(report["candidates"]), {"baseline", "next"})
        observations = {
            name: item["runs"][0]["observationStatus"] for name, item in report["candidates"].items()
        }
        self.assertEqual(set(observations.values()), {"passed"})

    def test_isolated_copy_protects_source_tree(self):
        harness = self.write_script(
            "harness.py",
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            "sys.stdin.read()\n"
            "Path(os.environ['SKILL_EVAL_CANDIDATE_DIR'], 'SKILL.md').write_text('mutated\\n', encoding='utf-8')\n",
        )

        result = self.command(
            "--corpus",
            str(self.corpus),
            "--case",
            "P1",
            "--model",
            "test-model",
            "--candidate",
            f"baseline={self.baseline}",
            "--baseline",
            "baseline",
            "--harness-argv-json",
            json.dumps([sys.executable, str(harness)]),
            "--output",
            str(self.output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.baseline / "SKILL.md").read_text(encoding="utf-8"), "marker A\n")

    def test_completed_case_is_written_before_later_case_finishes(self):
        self.corpus.write_text(
            "- **P1**（真实返工 2026-10-01）：`one`\n"
            "- **P2**（真实返工 2026-10-02）：`two`\n",
            encoding="utf-8",
        )
        harness = self.write_script(
            "harness.py",
            "import os, sys, time\n"
            "sys.stdin.read()\n"
            "if os.environ['SKILL_EVAL_CASE_ID'] == 'P2':\n"
            "    time.sleep(30)\n"
            "print('done')\n",
        )
        process = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "--corpus",
                str(self.corpus),
                "--model",
                "test-model",
                "--candidate",
                f"baseline={self.baseline}",
                "--baseline",
                "baseline",
                "--harness-argv-json",
                json.dumps([sys.executable, str(harness)]),
                "--output",
                str(self.output),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 2
            recorded = False
            while time.monotonic() < deadline:
                if self.output.is_file() and '"caseId": "P1"' in self.output.read_text(encoding="utf-8"):
                    recorded = True
                    break
                time.sleep(0.05)
            self.assertTrue(recorded, "completed case was not written before the later case finished")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def test_platform_flag_is_rejected(self):
        result = self.command(
            "--platform",
            "cursor",
            "--corpus",
            str(self.corpus),
            "--model",
            "test-model",
            "--output",
            str(self.output),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("supported", (result.stdout + result.stderr).lower())
        self.assertFalse(self.output.exists())
