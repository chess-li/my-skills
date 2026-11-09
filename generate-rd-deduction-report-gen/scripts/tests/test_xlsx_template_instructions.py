import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from scripts.create_xlsx_templates import create_supplement_template


class XlsxTemplateInstructionsTest(unittest.TestCase):
    def _instruction_text(self, path: Path) -> str:
        workbook = load_workbook(path, data_only=False)
        try:
            return "\n".join(
                str(cell.value)
                for sheet in workbook.worksheets
                for row in sheet.iter_rows()
                for cell in row
                if cell.value is not None
            )
        finally:
            workbook.close()

    def test_generated_and_bundled_04_template_explain_both_channels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generated = Path(temp_dir) / "04-补充信息清单-template.xlsx"
            create_supplement_template(generated)
            bundled = Path(__file__).resolve().parents[2] / "templates" / generated.name

            for path in (generated, bundled):
                with self.subTest(path=path):
                    text = self._instruction_text(path)
                    self.assertIn("word 通道", text)
                    self.assertIn("list 通道", text)
                    self.assertIn("不填写 Word 页码", text)
                    self.assertNotIn("Hxx 占位符一一对应", text)


if __name__ == "__main__":
    unittest.main()
