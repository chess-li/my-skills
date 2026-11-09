import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from scripts.generate_rd_docs import render_workbook
from scripts.tests.test_data_model import valid_input


def build_template(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "清单"
    sheet.cell(row=1, column=1, value="项目：{{ project_name }}")
    sheet.cell(row=2, column=1, value="编号")
    sheet.cell(row=2, column=2, value="事项")
    sheet.cell(row=3, column=1, value="{{ id }}")
    sheet.cell(row=3, column=2, value="{{ request }}")
    workbook.save(path)


class XlsxRendererTest(unittest.TestCase):
    def test_marker_row_is_replaced_by_data_rows_and_scalars_substituted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.xlsx"
            output = root / "output.xlsx"
            build_template(template)
            facts = valid_input()
            facts["supplements"] = [
                {"id": "H01", "pages": "1", "request": "确认名称"},
                {"id": "H02", "pages": "2", "request": "确认日期"},
            ]

            render_workbook(template, output, facts, {"清单": "supplements"})

            sheet = load_workbook(output)["清单"]
            self.assertEqual(sheet.cell(row=1, column=1).value, "项目：模型测试项目")
            self.assertEqual(sheet.cell(row=3, column=1).value, "H01")
            self.assertEqual(sheet.cell(row=3, column=2).value, "确认名称")
            self.assertEqual(sheet.cell(row=4, column=1).value, "H02")
            self.assertIsNone(sheet.cell(row=5, column=1).value)

    def test_empty_data_removes_the_marker_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.xlsx"
            output = root / "output.xlsx"
            build_template(template)

            render_workbook(template, output, valid_input(), {"清单": "supplements"})

            sheet = load_workbook(output)["清单"]
            self.assertEqual(sheet.cell(row=1, column=1).value, "项目：模型测试项目")
            self.assertEqual(sheet.cell(row=2, column=1).value, "编号")
            self.assertIsNone(sheet.cell(row=3, column=1).value)

    def test_unknown_scalar_variable_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.xlsx"
            output = root / "output.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.cell(row=1, column=1, value="{{ not_a_field }}")
            workbook.save(template)

            with self.assertRaisesRegex(ValueError, "not_a_field"):
                render_workbook(template, output, valid_input(), {})

    def test_missing_sheet_in_template_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.xlsx"
            output = root / "output.xlsx"
            build_template(template)

            with self.assertRaisesRegex(ValueError, "missing sheet"):
                render_workbook(template, output, valid_input(), {"不存在的表": "supplements"})


if __name__ == "__main__":
    unittest.main()
