import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document
from docxtpl import DocxTemplate
from jinja2 import UndefinedError
from openpyxl import load_workbook

from scripts.tests.test_data_model import valid_input
from scripts.data_model import RDProjectData
from scripts.generate_rd_docs import build_context, main, render_docx_template, validate_input, validate_template_contract


class DocxTemplateRendererTest(unittest.TestCase):
    def test_list_channel_supplements_are_excluded_from_docx_context(self):
        facts = valid_input()
        facts["supplements"] = [
            {"id": "H01", "pages": "1", "request": "正文待补事项"},
            {"id": "L01", "channel": "list", "request": "仅清单留痕"},
        ]
        template = DocxTemplate("templates/01-立项决议-template.docx")

        context = build_context(facts, template, "2026-01-02")

        self.assertEqual([item["id"] for item in context["supplements"]], ["H01"])

    def test_explicit_empty_objectives_stays_empty_in_template_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = Path(temp_dir) / "template.docx"
            Document().save(template_path)
            facts = valid_input()
            facts["objectives"] = []

            context = build_context(facts, DocxTemplate(str(template_path)), "2026-01-02")

            self.assertEqual(context["objectives"], [])

    def test_renders_table_row_loop_from_docx_template(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.docx"
            output = root / "output.docx"

            document = Document()
            table = document.add_table(rows=4, cols=2)
            table.rows[0].cells[0].text = "名称"
            table.rows[0].cells[1].text = "结果"
            table.rows[1].cells[0].text = "{%tr for item in items %}"
            table.rows[2].cells[0].text = "{{ item.name }}"
            table.rows[2].cells[1].text = "{{ item.result }}"
            table.rows[3].cells[0].text = "{%tr endfor %}"
            document.save(template)

            render_docx_template(
                template,
                output,
                {"items": [{"name": "A", "result": "通过"}, {"name": "B", "result": "待确认"}]},
            )

            rows = [[cell.text for cell in row.cells] for row in Document(output).tables[0].rows]
            self.assertEqual(rows, [["名称", "结果"], ["A", "通过"], ["B", "待确认"]])

    def test_missing_context_variable_fails_instead_of_rendering_blank(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.docx"
            output = root / "output.docx"
            document = Document()
            document.add_paragraph("{{ required_value }}")
            document.save(template)

            with self.assertRaises(UndefinedError):
                render_docx_template(template, output, {})

    def test_empty_real_template_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            template = Path(temp_dir) / "empty.docx"
            Document().save(template)
            with self.assertRaisesRegex(ValueError, "declares no variables"):
                validate_template_contract(DocxTemplate(str(template)), {}, "empty.docx")

    def test_template_variable_contract_is_derived_from_the_template_itself(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            template = Path(temp_dir) / "template.docx"
            document = Document()
            document.add_paragraph("{{ known_value }} / {{ missing_value }}")
            document.save(template)
            doc = DocxTemplate(str(template))

            with self.assertRaisesRegex(ValueError, "missing_value"):
                validate_template_contract(doc, {"known_value": "有值"}, "template.docx")
            validate_template_contract(doc, {"known_value": "有值", "missing_value": "有值"}, "template.docx")

    def test_package_entrypoint_generates_all_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "facts.json"
            output_dir = root / "output"
            facts = {
                "project_name": "入口测试【待补充：H01】", "company_name": "公司", "period": "2026",
                "leader": "负责人", "decision_maker": "决策人", "decision_date": "2026-01-01",
                "plan_date": "2026-01-02", "outcome_date": "2026-01-03", "funding_source": "资金",
                "background": "背景", "objective": "目标", "difficulties": ["难点"],
                "uncertainties": ["不确定性"], "company_advantages": ["公司"], "personnel_advantages": ["人员"],
                "purpose": "目的", "technical_indicators": [{"name": "指标", "target": "目标", "actual": "结果", "evidence": "依据"}],
                "actual_results": ["成果"], "innovation_points": ["创新"], "social_benefits": "社会",
                "economic_benefits": "经济", "application_results": ["应用"],
                "topics": [{"title": str(i), "existing_problem": "问题", "research_objective": "目标", "research_content": "内容", "variables": "变量", "verification": "验证", "expected_effect": "效果"} for i in range(1, 4)],
                "schedule": [{"time": "2026", "stage": "阶段", "content": "内容", "output": "输出"}],
                "personnel": [{"name": "人", "department": "部", "responsibility": "责", "work_content": "工作"}],
                "budget_items": [{"category": "类", "amount": "额", "purpose": "用"}],
                "intellectual_property": [{"name": "知识产权", "number": "编号", "date": "日期", "status": "状态"}],
                "supplements": [
                    {"id": "H01", "pages": "1", "request": "确认项目名称"},
                    {"id": "L01", "channel": "list", "request": "补交原始材料"},
                ],
            }
            self.assertIsInstance(validate_input(facts), RDProjectData)
            input_path.write_text(json.dumps(facts, ensure_ascii=False), encoding="utf-8")
            with patch("sys.argv", ["generate_rd_docs.py", "--input", str(input_path), "--template-dir", "templates", "--output-dir", str(output_dir)]):
                main()
            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                sorted(["00-研发加计工作底稿.xlsx", "01-立项决议.docx", "02-项目计划书.docx", "03-成果效用说明.docx", "04-补充信息清单.xlsx"]),
            )
            plan = Document(output_dir / "02-项目计划书.docx")
            self.assertFalse(any(cell.text == "图片" for table in plan.tables for row in table.rows for cell in row.cells))
            rendered_text = "\n".join(
                paragraph.text
                for name in ("01-立项决议.docx", "02-项目计划书.docx", "03-成果效用说明.docx")
                for paragraph in Document(output_dir / name).paragraphs
            )
            self.assertNotIn("补交原始材料", rendered_text)
            workbook = load_workbook(output_dir / "04-补充信息清单.xlsx", data_only=True)
            values = {
                cell.value
                for sheet in workbook.worksheets
                for row in sheet.iter_rows()
                for cell in row
            }
            self.assertIn("L01", values)
            self.assertIn("补交原始材料", values)
            workbook.close()
            workpaper = load_workbook(output_dir / "00-研发加计工作底稿.xlsx", data_only=True)
            workpaper_values = {
                cell.value
                for sheet in workpaper.worksheets
                for row in sheet.iter_rows()
                for cell in row
            }
            self.assertNotIn("L01", workpaper_values)
            self.assertNotIn("补交原始材料", workpaper_values)
            workpaper.close()


if __name__ == "__main__":
    unittest.main()
