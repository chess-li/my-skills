import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from scripts.generate_supplement_summary import generate_summary, main


class GenerateSupplementSummaryTest(unittest.TestCase):
    def test_cli_skips_output_when_batch_is_false(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "summary.xlsx"
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                ["generate_supplement_summary.py", "--output", str(output)],
            ), redirect_stdout(stdout):
                main()

            self.assertFalse(output.exists())
            self.assertEqual(
                json.loads(stdout.getvalue()),
                {"ok": True, "skipped": True, "reason": "batch is false"},
            )

    def test_cli_generates_output_when_batch_is_true(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facts = root / "project.json"
            facts.write_text(
                json.dumps({"project_name": "项目甲", "supplements": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            output = root / "summary.xlsx"
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "generate_supplement_summary.py",
                    "--batch",
                    "--input",
                    str(facts),
                    "--output",
                    str(output),
                ],
            ), redirect_stdout(stdout):
                main()

            self.assertTrue(output.is_file())
            self.assertEqual(
                json.loads(stdout.getvalue()),
                {"ok": True, "output": str(output), "rows": 0, "departments": 0},
            )

    def test_summary_sorts_items_and_builds_department_totals_from_facts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_a = root / "project-a.json"
            project_b = root / "project-b.json"
            project_a.write_text(
                json.dumps(
                    {
                        "project_name": "项目甲",
                        "supplements": [
                            {
                                "id": "H01",
                                "pages": "2",
                                "location": "一、研发目标",
                                "placeholder": "【待补充：H01】",
                                "request": "确认目标",
                                "format": "文字说明",
                                "owner": "技术部",
                                "priority": "中",
                                "status": "未填写",
                                "note": "",
                                "channel": "word",
                            },
                            {
                                "id": "L01",
                                "request": "补交损坏附件",
                                "owner": "财务部",
                                "priority": "高",
                                "channel": "list",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            project_b.write_text(
                json.dumps(
                    {
                        "project_name": "项目乙",
                        "supplements": [
                            {
                                "id": "H02",
                                "request": "确认金额",
                                "owner": "技术部",
                                "priority": "高",
                                "channel": "word",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output = root / "补充信息汇总清单.xlsx"

            result = generate_summary([project_a, project_b], output)

            self.assertEqual(result, {"rows": 3, "departments": 2})
            workbook = load_workbook(output, data_only=True)
            summary = workbook["补充信息汇总"]
            self.assertEqual(
                tuple(cell.value for cell in summary[1]),
                (
                    "项目", "编号", "Word页码", "Word章节/位置", "当前占位文字",
                    "需要补充什么信息", "建议填写格式", "责任部门", "优先级",
                    "填写状态", "备注", "通道",
                ),
            )
            self.assertEqual(
                [tuple(cell.value for cell in row) for row in summary.iter_rows(min_row=2, max_col=12)],
                [
                    ("项目乙", "H02", None, None, None, "确认金额", None, "技术部", "高", "未填写", None, "word"),
                    ("项目甲", "H01", "2", "一、研发目标", "【待补充：H01】", "确认目标", "文字说明", "技术部", "中", "未填写", None, "word"),
                    ("项目甲", "L01", None, None, None, "补交损坏附件", None, "财务部", "高", "未填写", None, "list"),
                ],
            )
            department = workbook["分部门统计"]
            self.assertEqual(
                [tuple(cell.value for cell in row) for row in department.iter_rows(min_row=1, max_col=4)],
                [
                    ("责任部门", "待办项数", "高优先级", "涉及项目"),
                    ("技术部", 2, 1, "项目甲、项目乙"),
                    ("财务部", 1, 1, "项目甲"),
                ],
            )
            workbook.close()


if __name__ == "__main__":
    unittest.main()
