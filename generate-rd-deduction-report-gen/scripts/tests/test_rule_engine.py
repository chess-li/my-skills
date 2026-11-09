import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.data_model import RDProjectData
from scripts.rule_engine import load_rules, main as rule_engine_main, validate
from scripts.tests.test_data_model import valid_input


class RuleEngineTest(unittest.TestCase):
    def test_cli_validates_raw_and_normalized_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_path = root / "facts.json"
            projection_path = root / "normalized.json"
            raw = valid_input()
            projection = RDProjectData.from_dict(raw).to_dict()
            raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            projection_path.write_text(json.dumps(projection, ensure_ascii=False), encoding="utf-8")
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "rule_engine.py",
                    "--input",
                    str(raw_path),
                    "--projection",
                    str(projection_path),
                ],
            ), redirect_stdout(stdout):
                rule_engine_main()

            self.assertEqual(json.loads(stdout.getvalue()), {"ok": True, "valid": True})

    def test_default_rules_reject_two_topics(self):
        data = valid_input()
        data["topics"] = data["topics"][:2]

        with self.assertRaisesRegex(ValueError, "exactly three"):
            RDProjectData.from_dict(data)

    def test_swapped_rules_accept_a_different_topic_count(self):
        """不同业务替换 rules.json 即可更换形式规则：例如两条技术主线。"""
        data = valid_input()
        data["topics"] = data["topics"][:2]
        rules = load_rules()
        for rule in rules["stages"]["input"]:
            if rule["check"] == "list_length" and rule["field"] == "topics":
                rule["equals"] = 2

        model = RDProjectData.from_dict(data, rules)

        self.assertEqual(len(model.topics), 2)

    def test_unknown_check_type_fails_loudly(self):
        rules = load_rules()
        rules["stages"]["model"] = [
            {"name": "虚构规则", "check": "no_such_check", "message": "should not run"}
        ]

        with self.assertRaisesRegex(ValueError, "Unknown rule check type"):
            validate(valid_input(), {}, rules)

    def test_date_order_skips_placeholder_dates(self):
        data = valid_input()
        data["decision_date"] = "【待补充：H01】"
        rules = load_rules()

        model = RDProjectData.from_dict(data, rules)

        self.assertEqual(model.decision_date, "【待补充：H01】")

    def test_hxx_continuity_is_enforced_on_the_projection(self):
        data = valid_input()
        data["supplements"] = [
            {"id": "H01", "pages": "1", "request": "事项一"},
            {"id": "H03", "pages": "2", "request": "事项二"},
        ]

        with self.assertRaisesRegex(ValueError, "continuous from H01"):
            RDProjectData.from_dict(data)

    def test_paths_exist_rejects_missing_images(self):
        data = valid_input()
        data["result_images"] = [{"path": "/no/such/image.png"}]

        with self.assertRaisesRegex(ValueError, "Image does not exist"):
            RDProjectData.from_dict(data)

    def test_rules_file_is_parseable_and_documents_each_check(self):
        rules = load_rules()

        self.assertIn("placeholder", rules)
        self.assertIn("description", rules["placeholder"])
        for stage in ("input", "model"):
            for rule in rules["stages"][stage]:
                with self.subTest(rule=rule["name"]):
                    self.assertIn("name", rule)
                    self.assertIn("description", rule)
                    self.assertIn("message", rule)

    def test_load_rules_falls_back_to_default_for_missing_business_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            rules = load_rules(Path(temp_dir) / "rules.json")

        self.assertEqual(rules["spec"], "rd-document-validation-rules")


if __name__ == "__main__":
    unittest.main()
