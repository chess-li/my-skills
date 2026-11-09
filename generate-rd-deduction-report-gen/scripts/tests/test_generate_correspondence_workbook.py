import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from scripts.generate_correspondence_workbook import main


class GenerateCorrespondenceWorkbookTest(unittest.TestCase):
    def test_cli_renders_material_mapping_and_open_questions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "correspondence.json"
            output_path = root / "对应表与待确认事项清单.xlsx"
            input_path.write_text(
                json.dumps(
                    {
                        "company_name": "测试公司",
                        "year": "2026",
                        "materials": [
                            {
                                "source_file": "研发记录.docx",
                                "source_location": "第 2 页",
                                "project_name": "项目甲",
                                "report_document": "02-项目计划书.docx",
                                "match_basis": "文件主题与项目目标一致",
                                "status": "待确认",
                                "note": "",
                            }
                        ],
                        "questions": [
                            {
                                "topic": "项目归属",
                                "question": "该记录属于哪个项目？",
                                "proposal": "项目甲",
                                "decision": "",
                                "status": "待确认",
                                "evidence": "文件标题含项目甲关键词",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "generate_correspondence_workbook.py",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
            ), redirect_stdout(stdout):
                main()

            self.assertEqual(
                json.loads(stdout.getvalue()),
                {"ok": True, "output": str(output_path), "materials": 1, "questions": 1},
            )
            workbook = load_workbook(output_path, data_only=True)
            self.assertEqual(workbook.sheetnames, ["材料对应表", "待确认事项"])
            self.assertEqual(workbook["材料对应表"]["B2"].value, "研发记录.docx")
            self.assertEqual(workbook["材料对应表"]["D2"].value, "项目甲")
            self.assertEqual(workbook["待确认事项"]["C2"].value, "该记录属于哪个项目？")
            self.assertEqual(workbook["待确认事项"]["F2"].value, "待确认")
            workbook.close()


if __name__ == "__main__":
    unittest.main()
