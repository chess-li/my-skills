import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document
from openpyxl import Workbook

from scripts.verify_rd_docs import main
from scripts.tests.test_data_model import valid_input


class VerifyRdDocsTest(unittest.TestCase):
    def _prepare(self, temp: Path, missing_workbook_placeholder: bool, include_list_item: bool = False):
        root = Path(__file__).resolve().parents[2]
        template_dir = root / "templates"
        manifest = json.loads((template_dir / "report.json").read_text(encoding="utf-8"))
        input_path = temp / "facts.json"
        output_dir = temp / "rendered"
        output_dir.mkdir()
        data = valid_input()
        data["supplements"] = [
            {
                "id": "H01",
                "pages": "1",
                "location": "一、研发目标",
                "placeholder": "【待补充：H01】",
                "request": "确认研发目标",
            }
        ]
        if include_list_item:
            data["supplements"].append(
                {"id": "L01", "channel": "list", "request": "补交原始材料"}
            )
        input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        for item in manifest["documents"]:
            document = Document()
            document.add_paragraph("【待补充：H01】")
            document.save(output_dir / item["output"])
        for index, item in enumerate(manifest["workbooks"]):
            workbook = Workbook()
            if not (missing_workbook_placeholder and index == 1):
                workbook.active["A1"] = "【待补充：H01】"
            workbook.save(output_dir / item["output"])
        return input_path, output_dir, template_dir

    def _run_cli(self, input_path: Path, output_dir: Path, template_dir: Path):
        argv = [
            "verify_rd_docs.py",
            "--input",
            str(input_path),
            "--template-dir",
            str(template_dir),
            "--output-dir",
            str(output_dir),
        ]
        stdout = io.StringIO()
        try:
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
                main()
        except SystemExit as exc:
            return json.loads(stdout.getvalue()), exc.code
        return json.loads(stdout.getvalue()), 0

    def test_cli_reports_pass_only_after_all_rendered_files_verify(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path, output_dir, template_dir = self._prepare(Path(temp_dir), False)
            self.assertEqual(
                self._run_cli(input_path, output_dir, template_dir),
                ({"ok": True, "verify_passed": True}, 0),
            )

    def test_cli_reports_failure_when_a_workbook_placeholder_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path, output_dir, template_dir = self._prepare(Path(temp_dir), True)
            result, exit_code = self._run_cli(input_path, output_dir, template_dir)
            self.assertEqual(exit_code, 1)
            self.assertFalse(result["verify_passed"])

    def test_cli_ignores_list_channel_items_in_hxx_consistency(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path, output_dir, template_dir = self._prepare(
                Path(temp_dir), False, include_list_item=True
            )

            self.assertEqual(
                self._run_cli(input_path, output_dir, template_dir),
                ({"ok": True, "verify_passed": True}, 0),
            )


if __name__ == "__main__":
    unittest.main()
