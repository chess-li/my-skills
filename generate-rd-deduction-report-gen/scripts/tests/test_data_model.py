import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.data_model import RDProjectData, main as data_model_main
from scripts.rule_engine import load_rules


def valid_input():
    return {
        "project_name": "模型测试项目",
        "company_name": "测试公司",
        "period": "2026",
        "leader": "负责人",
        "decision_maker": "决策人",
        "decision_date": "2026-01-01",
        "plan_date": "2026-01-02",
        "outcome_date": "2026-01-03",
        "background": "背景",
        "objective": "目标",
        "difficulties": ["难点"],
        "uncertainties": ["不确定性"],
        "company_advantages": ["公司基础"],
        "personnel_advantages": ["人员基础"],
        "purpose": "目的",
        "technical_indicators": [
            {"name": "指标", "target": "目标", "actual": "结果", "evidence": "依据"}
        ],
        "actual_results": ["成果"],
        "innovation_points": ["创新"],
        "social_benefits": "社会效益",
        "economic_benefits": "经济效益",
        "application_results": ["应用"],
        "topics": [
            {
                "title": str(index),
                "problem": "问题",
                "goal": "目标",
                "approach": "内容",
                "parameters": "变量",
                "validation": "验证",
                "effect": "效果",
            }
            for index in range(1, 4)
        ],
        "schedule": [{"planned_time": "阶段时间", "research_content": "内容", "deliverable": "输出"}],
        "personnel": [{"name": "人员", "role": "部门", "work": "职责"}],
        "budget_items": [{"type": "费用", "amount": "100", "usage": "用途"}],
        "intellectual_property": [{"name": "成果", "number": "编号", "date": "日期", "status": "状态"}],
        "supplements": [],
    }


class RDProjectDataTest(unittest.TestCase):
    def test_cli_writes_normalized_projection_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "facts.json"
            output_path = root / "normalized.json"
            input_path.write_text(json.dumps(valid_input(), ensure_ascii=False), encoding="utf-8")
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "data_model.py",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
            ), redirect_stdout(stdout):
                data_model_main()

            normalized = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(normalized["topics"][0]["existing_problem"], "问题")
            self.assertNotIn("problem", normalized["topics"][0])
            self.assertEqual(json.loads(stdout.getvalue())["ok"], True)

    def test_from_dict_normalizes_nested_input_aliases(self):
        model = RDProjectData.from_dict(valid_input())

        self.assertEqual(model.topics[0].existing_problem, "问题")
        self.assertEqual(model.topics[0].research_objective, "目标")
        self.assertEqual(model.schedule[0].time, "阶段时间")
        self.assertEqual(model.schedule[0].content, "内容")
        self.assertEqual(model.schedule[0].output, "输出")
        self.assertEqual(model.personnel[0].department, "部门")
        self.assertEqual(model.personnel[0].responsibility, "职责")
        self.assertEqual(model.budget_items[0].category, "费用")
        self.assertEqual(model.budget_items[0].purpose, "用途")

        serialized = model.to_dict()
        self.assertEqual(serialized["topics"][0]["existing_problem"], "问题")
        self.assertEqual(serialized["schedule"][0]["time"], "阶段时间")
        self.assertEqual(serialized["personnel"][0]["department"], "部门")

    def test_from_dict_rejects_a_topic_collection_that_is_not_exactly_three(self):
        data = valid_input()
        data["topics"] = data["topics"][:2]

        with self.assertRaisesRegex(ValueError, "exactly three"):
            RDProjectData.from_dict(data)

    def test_from_dict_rejects_out_of_order_dates(self):
        data = valid_input()
        data["plan_date"] = "2025-12-31"

        with self.assertRaisesRegex(ValueError, "Date order"):
            RDProjectData.from_dict(data)

    def test_from_dict_rejects_string_objectives_instead_of_splitting_characters(self):
        data = valid_input()
        data["objectives"] = "一个目标"

        with self.assertRaisesRegex(ValueError, "objectives must be a list"):
            RDProjectData.from_dict(data)

    def test_from_dict_rejects_invalid_supplement_pages(self):
        data = valid_input()
        data["supplements"] = [{"id": "H01", "pages": "unknown"}]

        with self.assertRaisesRegex(ValueError, "pages must contain valid Word page"):
            RDProjectData.from_dict(data)

        for pages in ("0", "2-1", "1~0"):
            data["supplements"] = [{"id": "H01", "pages": pages}]
            with self.subTest(pages=pages), self.assertRaisesRegex(ValueError, "pages must contain valid Word page"):
                RDProjectData.from_dict(data)

    def test_missing_supplements_defaults_to_an_empty_collection(self):
        data = valid_input()
        data.pop("supplements")

        self.assertEqual(RDProjectData.from_dict(data).supplements, ())

    def test_list_channel_supplement_does_not_require_hxx_or_word_page(self):
        data = valid_input()
        data["supplements"] = [
            {"id": "H01", "pages": "1", "request": "正文待补事项"},
            {"id": "L01", "channel": "list", "request": "补交原始材料"},
        ]

        model = RDProjectData.from_dict(data)

        self.assertEqual([item.channel for item in model.supplements], ["word", "list"])
        self.assertEqual(model.supplements[1].pages, "")

    def test_explicit_non_list_supplements_are_rejected(self):
        data = valid_input()
        data["supplements"] = None

        with self.assertRaisesRegex(ValueError, "supplements must be a list"):
            RDProjectData.from_dict(data)

    def test_from_dict_rejects_scalars_for_bullet_collections(self):
        for field in (
            "difficulties",
            "uncertainties",
            "company_advantages",
            "personnel_advantages",
            "actual_results",
            "innovation_points",
            "application_results",
        ):
            data = valid_input()
            data[field] = "不能按字符拆分"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, f"{field} must be a list"):
                RDProjectData.from_dict(data)

    def test_explicit_empty_objectives_remain_empty(self):
        data = valid_input()
        data["objectives"] = []

        self.assertEqual(RDProjectData.from_dict(data).objectives, ())
        self.assertIsNone(RDProjectData.from_dict(valid_input()).objectives)

    def test_fixed_element_rows_merge_provided_values_and_keep_fixed_names(self):
        data = valid_input()
        data["unified_elements"] = [{"name": "项目身份", "value": "已确认", "status": "确认事实", "placeholder": "H01"}]
        fixed = load_rules()["fixed_elements"]["items"]

        rows = RDProjectData.from_dict(data).unified_element_rows()

        self.assertEqual(len(rows), len(fixed))
        identity = rows[0]
        self.assertEqual(identity["name"], "项目身份")
        self.assertEqual(identity["value"], "已确认")
        self.assertEqual(identity["placeholder"], "H01")
        self.assertEqual(rows[1]["name"], fixed[1])
        self.assertEqual(rows[1]["status"], "待补信息")
        self.assertEqual(rows[1]["id"], "E02")

    def test_fixed_consistency_rows_merge_provided_values(self):
        data = valid_input()
        data["consistency_checks"] = [{"item": "项目名称", "decision": "一致", "consistent": "是"}]
        fixed = load_rules()["fixed_consistency_items"]["items"]

        rows = RDProjectData.from_dict(data).consistency_rows()

        self.assertEqual([row["item"] for row in rows], fixed)
        self.assertEqual(rows[0]["decision"], "一致")
        self.assertEqual(rows[1]["decision"], "")

    def test_derived_context_falls_back_to_topic_content(self):
        model = RDProjectData.from_dict(valid_input())
        derived = model.derived_context()

        self.assertEqual(derived["objectives"], ["目标"])
        self.assertEqual(derived["research_content_summary"], "内容；内容；内容")
        self.assertEqual(derived["budget_summary"], "费用：100")
        self.assertEqual(derived["expected_results"], "效果；效果；效果")
        self.assertEqual(derived["result_ownership"], "测试公司")
        self.assertEqual(derived["result_image_path"], "")
        self.assertEqual(derived["topics"][0]["caption"], "")

    def test_derived_context_prefers_explicit_summaries(self):
        data = valid_input()
        data["research_content"] = "项目级摘要"
        data["budget_summary"] = "预算摘要"
        data["expected_results"] = "成果摘要"
        data["result_ownership"] = "归属方"
        derived = RDProjectData.from_dict(data).derived_context()

        self.assertEqual(derived["research_content_summary"], "项目级摘要")
        self.assertEqual(derived["budget_summary"], "预算摘要")
        self.assertEqual(derived["expected_results"], "成果摘要")
        self.assertEqual(derived["result_ownership"], "归属方")


if __name__ == "__main__":
    unittest.main()
