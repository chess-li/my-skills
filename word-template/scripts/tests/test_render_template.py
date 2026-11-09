import base64
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from docx import Document

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import render_template  # noqa: E402


class RenderTemplateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_docx(self, text):
        path = self.root / "template.docx"
        doc = Document()
        doc.add_paragraph(text)
        doc.save(path)
        return path

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def write_png(self, name="image.png"):
        data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+Q8AApMBgQDJuJ4AAAAASUVORK5CYII="
        )
        path = self.root / name
        path.write_bytes(data)
        return path

    def asset_record(self, asset_id, path, mode="asset_only", **extra):
        record = {
            "asset_id": asset_id,
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": mode,
            "media_type": "image/png" if path.suffix == ".png" else "application/octet-stream",
        }
        record.update(extra)
        return record

    def test_missing_required_field_blocks_before_render(self):
        template = self.write_docx("项目：{{field:project.name}}")
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "required": ["project.name"], "values": {}},
        )
        report = self.root / "report.json"

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=report,
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "FIELD_REQUIRED_MISSING")
        self.assertTrue(report.exists())
        self.assertFalse((self.root / "result.docx").exists())

    def test_projection_without_target_identity_is_blocked(self):
        template = self.write_docx("固定文本")
        projection = self.write_json("projection.json", {})

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "PROJECTION_INVALID")

    def test_malformed_projection_state_returns_reported_error(self):
        template = self.write_docx("{{field:project.name}}")
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "states": {"project.name": []}},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "FIELD_STATE_INVALID")

    def test_malformed_asset_review_returns_reported_error(self):
        template = self.write_docx("{{asset:image-1}}")
        image = self.write_png()
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    self.asset_record("image-1", image, review="approved")
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "ASSET_MANIFEST_INVALID")

    def test_declared_default_renders_without_residual_marker(self):
        template = self.write_docx("负责人：{{field:project.owner}}")
        projection = self.write_json(
            "projection.json",
            {
                "target_id": "target-1",
                "required": ["project.owner"],
                "values": {},
                "defaults": {"project.owner": "未提供"},
            },
        )
        report = self.root / "report.json"
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=report,
        )

        self.assertEqual(result.status, "structural_ready")
        self.assertTrue(output.exists())
        rendered = Document(str(output))
        self.assertEqual(rendered.paragraphs[0].text, "负责人：未提供")

    def test_declared_date_format_is_deterministic(self):
        template = self.write_docx('{{field:project.date|format:"YYYY-MM-DD"}}')
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.date": "2024-01-02T12:34:56"}},
        )
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        self.assertEqual(Document(str(output)).paragraphs[0].text, "2024-01-02")

    def test_unsupported_format_is_rejected_in_preflight(self):
        template = self.write_docx('{{field:project.date|format:"free-form"}}')
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.date": "2024-01-02"}},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "FORMAT_UNSUPPORTED")

    def test_evidence_binding_renders_value_and_records_provenance(self):
        template = self.write_docx("项目：{{field:project.name}}")
        projection = self.write_json(
            "projection.json",
            {
                "target_id": "target-1",
                "required": ["project.name"],
                "bindings": {"project.name": {"source": "evidence:e-1"}},
            },
        )
        evidence = self.write_json(
            "evidence.json",
            {
                "evidence": [
                    {
                        "evidence_id": "e-1",
                        "source_file": "source.docx",
                        "source_sha256": "source-hash",
                        "locator": {"kind": "paragraph", "index": 1},
                        "normalized_text_sha256": "normalized-hash",
                        "status": "machine_readable",
                        "value": "来自证据",
                    }
                ]
            },
        )
        output = self.root / "result.docx"
        report = self.root / "report.json"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=evidence,
            assets=None,
            report=report,
        )

        self.assertEqual(result.status, "structural_ready")
        self.assertEqual(Document(str(output)).paragraphs[0].text, "项目：来自证据")
        report_value = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(report_value["used_evidence"], ["e-1"])
        self.assertTrue(report_value["run_id"])
        self.assertTrue(report_value["projection_sha256"])
        self.assertEqual(report_value["renderer_version"], "word-template/0.1")
        self.assertEqual(report_value["visual_check"], "not_run")

    def test_existing_output_is_not_overwritten(self):
        template = self.write_docx("{{field:project.name}}")
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.name": "新值"}},
        )
        output = self.root / "result.docx"
        existing = self.root / "existing.docx"
        old_doc = Document()
        old_doc.add_paragraph("旧输出")
        old_doc.save(existing)
        output.write_bytes(existing.read_bytes())
        original = output.read_bytes()

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "OUTPUT_EXISTS")
        self.assertEqual(output.read_bytes(), original)

    def test_render_does_not_create_empty_header_footer_parts(self):
        template = self.write_docx("项目：{{field:project.name}}")
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.name": "示例"}},
        )
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        with ZipFile(output) as package:
            self.assertEqual(
                [name for name in package.namelist() if "header" in name or "footer" in name],
                [],
            )

    def test_existing_header_and_footer_markers_are_rendered_without_new_parts(self):
        template = self.root / "template.docx"
        doc = Document()
        doc.add_paragraph("正文：{{field:body}}")
        section = doc.sections[0]
        section.header.paragraphs[0].text = "页眉：{{field:header}}"
        section.footer.paragraphs[0].text = "页脚：{{field:footer}}"
        doc.save(template)
        projection = self.write_json(
            "projection.json",
            {
                "target_id": "target-1",
                "values": {
                    "body": "正文值",
                    "header": "页眉值",
                    "footer": "页脚值",
                },
            },
        )
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        rendered = Document(str(output))
        self.assertEqual(rendered.sections[0].header.paragraphs[0].text, "页眉：页眉值")
        self.assertEqual(rendered.sections[0].footer.paragraphs[0].text, "页脚：页脚值")
        with ZipFile(output) as package:
            names = [name for name in package.namelist() if "header" in name or "footer" in name]
            self.assertEqual(len(names), 2)

    def test_table_cell_field_is_rendered(self):
        template = self.root / "template.docx"
        doc = Document()
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "名称"
        table.cell(0, 1).text = "{{field:project.name}}"
        doc.save(template)
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.name": "表格值"}},
        )
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        self.assertEqual(Document(str(output)).tables[0].cell(0, 1).text, "表格值")

    def test_asset_only_image_is_embedded_without_visual_extraction(self):
        template = self.write_docx("{{asset:image-1}}")
        image = self.write_png()
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    self.asset_record("image-1", image)
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        rendered = Document(str(output))
        self.assertEqual(len(rendered.inline_shapes), 1)

    def test_asset_manifest_without_hash_is_blocked(self):
        template = self.write_docx("{{asset:image-1}}")
        image = self.write_png()
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    {
                        "asset_id": "image-1",
                        "path": image.name,
                        "mode": "asset_only",
                        "media_type": "image/png",
                    }
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "ASSET_HASH_MISSING")

    def test_asset_manifest_without_media_type_is_blocked(self):
        template = self.write_docx("{{asset:image-1}}")
        image = self.write_png()
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    {
                        "asset_id": "image-1",
                        "path": image.name,
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                        "mode": "asset_only",
                    }
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "ASSET_MANIFEST_INVALID")

    def test_unreadable_image_offers_source_and_render_paths(self):
        template = self.write_docx("{{asset:image-1}}")
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    {
                        "asset_id": "image-1",
                        "path": "missing.png",
                        "sha256": "missing-hash",
                        "mode": "asset_only",
                        "media_type": "image/png",
                    }
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "ASSET_UNREADABLE")
        self.assertIn("补充或修改", result.errors[0].source_fix)
        self.assertIn("停止渲染", result.errors[0].render_fix)

    def test_corrupt_image_bytes_are_rejected_during_preflight(self):
        template = self.write_docx("{{asset:image-1}}")
        image = self.root / "bad.png"
        image.write_bytes(b"this is not a png")
        assets = self.write_json(
            "assets.json",
            {"assets": [self.asset_record("image-1", image, media_type="image/png")]},
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "ASSET_UNREADABLE")

    def test_visual_observation_without_provenance_is_blocked(self):
        template = self.write_docx("{{asset:image-1}}")
        image = self.write_png()
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    self.asset_record(
                        "image-1",
                        image,
                        mode="visual_observation",
                        review={
                            "required": True,
                            "scope": "ledger_classification",
                            "status": "approved",
                        },
                    )
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "VISUAL_OBSERVATION_PROVENANCE_MISSING")

    def test_unclosed_condition_block_is_rejected_in_preflight(self):
        template = self.root / "template.docx"
        doc = Document()
        doc.add_paragraph("{{#if:project.enabled}}")
        doc.add_paragraph("应该保留")
        doc.save(template)
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.enabled": True}},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "TEMPLATE_BLOCK_UNMATCHED")

    def test_unverified_visual_observation_cannot_bind_fact_field_by_default(self):
        template = self.write_docx("类别：{{field:project.category}}")
        image = self.write_png()
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    self.asset_record(
                        "image-1",
                        image,
                        mode="visual_observation",
                        observation={
                            "extractor": {"kind": "vision_model", "model": "test-model"},
                            "input_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                            "observations": [{"key": "ledger_category", "value": "test", "confidence": 0.9}],
                            "semantic_status": "unverified",
                        },
                        review={
                            "required": True,
                            "scope": "ledger_classification",
                            "status": "approved",
                        },
                    )
                ]
            },
        )
        projection = self.write_json(
            "projection.json",
            {
                "target_id": "target-1",
                "required": ["project.category"],
                "bindings": {
                    "project.category": {"visual_observation_id": "image-1"}
                },
            },
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "VISUAL_FIELD_NOT_ALLOWED")

    def test_visual_observation_requires_classification_review(self):
        template = self.write_docx("{{asset:image-1}}")
        image = self.write_png()
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    self.asset_record(
                        "image-1",
                        image,
                        mode="visual_observation",
                        observation={
                            "extractor": {"kind": "vision_model", "model": "test-model"},
                            "input_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                            "observations": [{"key": "ledger_category", "value": "test", "confidence": 0.9}],
                            "semantic_status": "unverified",
                        },
                        review={
                            "required": True,
                            "scope": "ledger_classification",
                            "status": "pending",
                        },
                    )
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "VISUAL_OBSERVATION_UNREVIEWED")

    def test_false_condition_removes_entire_paragraph_block(self):
        template = self.root / "template.docx"
        doc = Document()
        doc.add_paragraph("前置")
        doc.add_paragraph("{{#if:project.enabled}}")
        doc.add_paragraph("不应出现")
        doc.add_paragraph("{{/if}}")
        doc.add_paragraph("后置")
        doc.save(template)
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.enabled": False}},
        )
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        self.assertEqual(
            [paragraph.text for paragraph in Document(str(output)).paragraphs],
            ["前置", "后置"],
        )

    def test_condition_literal_comparison_is_deterministic(self):
        template = self.root / "template.docx"
        doc = Document()
        doc.add_paragraph('{{#if:project.kind == "research"}}')
        doc.add_paragraph("匹配内容")
        doc.add_paragraph("{{/if}}")
        doc.save(template)
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.kind": "research"}},
        )
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        self.assertEqual(
            [paragraph.text for paragraph in Document(str(output)).paragraphs],
            ["匹配内容"],
        )

    def test_condition_uses_a_template_default_materialized_into_projection(self):
        template = self.root / "template.docx"
        doc = Document()
        doc.add_paragraph("{{#if:project.enabled}}")
        doc.add_paragraph("启用")
        doc.add_paragraph("{{/if}}")
        doc.add_paragraph('{{field:project.enabled|default:"true"}}')
        doc.save(template)
        projection = self.write_json("projection.json", {"target_id": "target-1"})
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        self.assertEqual(
            [paragraph.text for paragraph in Document(str(output)).paragraphs],
            ["启用", "true"],
        )

    def test_stale_evidence_blocks_with_traceable_error(self):
        template = self.write_docx("项目：{{field:project.name}}")
        projection = self.write_json(
            "projection.json",
            {
                "target_id": "target-1",
                "required": ["project.name"],
                "bindings": {"project.name": {"source": "evidence:e-1"}},
            },
        )
        evidence = self.write_json(
            "evidence.json",
            {
                "evidence": [
                    {
                        "evidence_id": "e-1",
                        "source_file": "source.docx",
                        "source_sha256": "old",
                        "locator": {"kind": "paragraph", "index": 1},
                        "normalized_text_sha256": "normalized-old",
                        "status": "stale",
                        "value": "旧值",
                    }
                ]
            },
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=evidence,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "EVIDENCE_STALE")

    def test_evidence_without_file_hash_and_locator_is_blocked(self):
        template = self.write_docx("项目：{{field:project.name}}")
        projection = self.write_json(
            "projection.json",
            {
                "target_id": "target-1",
                "required": ["project.name"],
                "bindings": {"project.name": {"source": "evidence:e-1"}},
            },
        )
        evidence = self.write_json(
            "evidence.json",
            {"evidence": [{"evidence_id": "e-1", "value": "无定位值", "status": "machine_readable"}]},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=evidence,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "EVIDENCE_LOCATOR_INVALID")

    def test_real_unannotated_template_cannot_bind_required_field(self):
        template = (
            Path(__file__).resolve().parents[4]
            / "files" / "test" / "templates" / "如果a.docx"
        )
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "required": ["a"], "values": {"a": "b"}},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "FIELD_NOT_BOUND")

    def test_dotx_template_is_supported_alongside_docx(self):
        source = self.write_docx("项目：{{field:project.name}}")
        template = self.root / "template.dotx"
        template.write_bytes(source.read_bytes())
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.name": "DOTX"}},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "ready")

    def test_template_with_embedded_ole_part_is_rejected_before_save(self):
        source = self.write_docx("项目：{{field:project.name}}")
        template = self.root / "embedded.docx"
        with ZipFile(source) as source_zip, ZipFile(template, "w") as target_zip:
            for item in source_zip.infolist():
                target_zip.writestr(item, source_zip.read(item.filename))
            target_zip.writestr("word/embeddings/oleObject1.bin", b"opaque")
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.name": "示例"}},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "TEMPLATE_PART_UNSUPPORTED")

    def test_split_marker_is_rejected_instead_of_reformatting_template(self):
        template = self.root / "template.docx"
        doc = Document()
        paragraph = doc.add_paragraph()
        paragraph.add_run("项目：{{field:")
        paragraph.add_run("project.name}}")
        doc.save(template)
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.name": "示例"}},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "TEMPLATE_MARKER_SPLIT")

    def test_unsupported_attachment_relation_offers_source_conversion_path(self):
        template = self.write_docx("{{attachment:attachment-1}}")
        attachment = self.root / "source.bin"
        attachment.write_bytes(b"opaque")
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    self.asset_record("attachment-1", attachment, mode="ole_embedded")
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "ATTACHMENT_RELATION_UNSUPPORTED")
        self.assertIn("转换", result.errors[0].source_fix)

    def test_each_loop_is_rejected_instead_of_guessed(self):
        template = self.root / "template.docx"
        doc = Document()
        doc.add_paragraph("{{#each:items}}")
        doc.add_paragraph("{{field:items.name}}")
        doc.add_paragraph("{{/each}}")
        doc.save(template)
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"items": [{"name": "A"}]}},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertTrue(any(error.code == "TEMPLATE_BLOCK_UNSUPPORTED" for error in result.errors))

    def test_conflicting_template_and_projection_defaults_block(self):
        template = self.write_docx('{{field:project.owner|default:"模板默认"}}')
        projection = self.write_json(
            "projection.json",
            {
                "target_id": "target-1",
                "defaults": {"project.owner": "投影默认"},
            },
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "DEFAULT_CONFLICT")

    def test_unknown_source_state_does_not_silently_use_default(self):
        template = self.write_docx('{{field:project.owner|default:"默认负责人"}}')
        projection = self.write_json(
            "projection.json",
            {
                "target_id": "target-1",
                "required": ["project.owner"],
                "values": {"project.owner": "无法确认"},
                "states": {"project.owner": "unknown"},
            },
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "FIELD_STATE_UNUSABLE")

    def test_supported_appendix_file_is_published_as_companion_artifact(self):
        template = self.write_docx("{{attachment:appendix-1}}")
        appendix = self.root / "source.txt"
        appendix.write_text("附录内容", encoding="utf-8")
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    self.asset_record(
                        "appendix-1",
                        appendix,
                        mode="appendix_file",
                        media_type="text/plain",
                    )
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        companion = self.root / "result.attachments" / appendix.name
        self.assertEqual(companion.read_text(encoding="utf-8"), "附录内容")
        self.assertEqual(Document(str(output)).paragraphs[0].text, "附件：source.txt")

    def test_external_reference_is_rendered_from_registered_reference(self):
        template = self.write_docx("{{attachment:external-1}}")
        assets = self.write_json(
            "assets.json",
            {
                "assets": [
                    {
                        "asset_id": "external-1",
                        "mode": "external_reference",
                        "reference": "https://example.invalid/source",
                        "label": "外部源",
                    }
                ]
            },
        )
        projection = self.write_json("projection.json", {"target_id": "target-1"})
        output = self.root / "result.docx"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=assets,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "structural_ready")
        self.assertEqual(Document(str(output)).paragraphs[0].text, "外部源")

    @unittest.skipUnless(
        shutil.which("soffice") and shutil.which("pdftoppm"),
        "需要 LibreOffice 和 Poppler 的本地视觉验证信道",
    )
    def test_visual_verification_is_required_for_final_rendered_status(self):
        template = self.write_docx("Project: {{field:project.name}}")
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.name": "Visual"}},
        )
        output = self.root / "result.docx"
        report = self.root / "report.json"
        visual_output = self.root / "visual"

        result = render_template.render(
            template=template,
            projection=projection,
            output=output,
            evidence=None,
            assets=None,
            report=report,
        )
        self.assertEqual(result.status, "structural_ready")

        verified = render_template.verify_visual(
            document=output,
            report=report,
            visual_output=visual_output,
            accept=True,
        )

        self.assertEqual(verified.status, "rendered")
        report_value = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(report_value["visual_check"], "passed")
        self.assertTrue(list(visual_output.glob("page-*.png")))

    def test_inline_condition_block_is_rejected_before_render(self):
        template = self.write_docx("前 {{#if:project.enabled}}中{{/if}} 后")
        projection = self.write_json(
            "projection.json",
            {"target_id": "target-1", "values": {"project.enabled": True}},
        )

        result = render_template.preflight(
            template=template,
            projection=projection,
            evidence=None,
            assets=None,
            report=self.root / "report.json",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].code, "TEMPLATE_BLOCK_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
