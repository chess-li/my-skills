#!/usr/bin/env python3
"""Deterministic DOCX template preflight and rendering primitives.

The module deliberately keeps the render context explicit: a template is read,
the target projection and evidence/assets manifests are resolved, and the
result is written only after preflight succeeds.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.image.image import Image as DocxImage
from docx.oxml.ns import qn
from docx.shared import Inches


MARKER_RE = re.compile(r"\{\{(?P<body>[^{}]+)\}\}")
FIELD_PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
CONDITION_RE = re.compile(
    r"^(?P<path>[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)"
    r"(?:\s*(?P<operator>==|!=)\s*(?P<literal>.+))?$"
)
FIELD_STATES = {"missing", "null", "unknown", "not_applicable", "empty"}
SUPPORTED_FORMATS = {"YYYY-MM-DD"}
RENDERER_VERSION = "word-template/0.1"


class TemplateError(ValueError):
    """Raised when a marker cannot be interpreted by the supported protocol."""


@dataclass(frozen=True)
class PreflightError:
    code: str
    object_id: str
    reason: str
    source_fix: str
    render_fix: str
    severity: str = "blocking"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "object_id": self.object_id,
            "reason": self.reason,
            "source_fix": self.source_fix,
            "render_fix": self.render_fix,
        }


@dataclass(frozen=True)
class Marker:
    raw: str
    kind: str
    key: str
    options: dict[str, Any]


@dataclass
class PreflightResult:
    status: str
    errors: list[PreflightError]
    markers: list[Marker]
    template_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "template_sha256": self.template_sha256,
            "markers": [
                {"raw": m.raw, "kind": m.kind, "key": m.key, "options": m.options}
                for m in self.markers
            ],
            "errors": [error.as_dict() for error in self.errors],
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_metadata(
    template_path: Path,
    projection_path: Path,
    evidence_path: Optional[Path],
    assets_path: Optional[Path],
    evidence_value: dict[str, Any],
    assets_value: dict[str, Any],
) -> dict[str, Any]:
    input_hashes = {
        "template": _sha256(template_path),
        "projection": _sha256(projection_path),
    }
    if evidence_path and evidence_path.is_file():
        input_hashes["evidence"] = _sha256(evidence_path)
    if assets_path and assets_path.is_file():
        input_hashes["assets"] = _sha256(assets_path)
    run_id = hashlib.sha256(
        json.dumps(input_hashes, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    evidence_hashes = sorted({
        str(record.get("source_sha256"))
        for record in _evidence_index(evidence_value).values()
        if record.get("source_sha256")
    })
    asset_hashes = sorted({
        str(record.get("sha256"))
        for record in _asset_index(assets_value).values()
        if record.get("sha256")
    })
    return {
        "run_id": run_id,
        "renderer_version": RENDERER_VERSION,
        "projection_sha256": input_hashes["projection"],
        "source_hashes": evidence_hashes,
        "asset_hashes": asset_hashes,
    }


def _template_package_errors(template_path: Path) -> list[PreflightError]:
    if template_path.suffix.lower() not in {".docx", ".dotx"}:
        return [PreflightError(
            "TEMPLATE_FORMAT_UNSUPPORTED", str(template_path),
            "第一版只接受 DOCX 或 DOTX 模板",
            "把模板转换为 DOCX 或 DOTX 后重新登记",
            "停止渲染并重新预检",
        )]
    try:
        with ZipFile(template_path) as package:
            names = set(package.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                return [PreflightError(
                    "TEMPLATE_UNREADABLE", str(template_path),
                    "DOCX/DOTX 包缺少必要部件",
                    "补充或修改数据源，提供完整的 Word 包",
                    "停止渲染并重新预检",
                )]
            embedded = sorted(
                name for name in names
                if name.startswith("word/embeddings/")
                or name.startswith("word/activeX/")
                or name.endswith("vbaProject.bin")
            )
            errors: list[PreflightError] = []
            if embedded:
                errors.append(PreflightError(
                    "TEMPLATE_PART_UNSUPPORTED", ",".join(embedded),
                    "模板包含第一版适配器不会安全重写的嵌入对象或宏部件",
                    "把对象转换为登记的资产/附录，或使用支持该部件的适配器",
                    "停止渲染并重新预检",
                ))
            for name in sorted(names):
                if not name.endswith(".xml"):
                    continue
                text = package.read(name).decode("utf-8", errors="ignore")
                if "{{" not in text:
                    continue
                unsupported_story = (
                    name.startswith("word/footnotes")
                    or name.startswith("word/endnotes")
                    or name.startswith("word/comments")
                    or "txbxContent" in text
                    or "txbx" in text and name.startswith("word/")
                )
                if unsupported_story:
                    errors.append(PreflightError(
                        "TEMPLATE_PART_UNSUPPORTED", name,
                        "模板标记位于第一版不支持的 Word 部件",
                        "把标记移动到正文、表格、已有页眉或已有页脚",
                        "停止渲染并重新预检",
                    ))
            return errors
    except (BadZipFile, OSError, UnicodeError) as exc:
        return [PreflightError(
            "TEMPLATE_UNREADABLE", str(template_path), str(exc),
            "补充或修改数据源，提供可读取的 DOCX/DOTX 模板",
            "停止渲染并重新预检",
        )]


def _validate_package_structure(path: Path) -> None:
    """Check required parts and internal relationship targets after rendering."""
    with ZipFile(path) as package:
        names = set(package.namelist())
        required = {"[Content_Types].xml", "word/document.xml"}
        missing = sorted(required - names)
        if missing:
            raise TemplateError(f"DOCX 包缺少必要部件: {', '.join(missing)}")
        for relationship_name in (name for name in names if name.endswith(".rels")):
            root = ET.fromstring(package.read(relationship_name))
            if relationship_name == "_rels/.rels":
                source_part = ""
            else:
                rel_dir, rel_file = relationship_name.rsplit("/", 1)
                source_dir = rel_dir[:-5] if rel_dir.endswith("/_rels") else rel_dir
                source_file = rel_file[:-5] if rel_file.endswith(".rels") else rel_file
                source_part = f"{source_dir}/{source_file}" if source_dir else source_file
            for relation in root:
                if relation.attrib.get("TargetMode") == "External":
                    continue
                target = relation.attrib.get("Target")
                if not target:
                    raise TemplateError(f"关系缺少 Target: {relationship_name}")
                if target.startswith("/"):
                    resolved = posixpath.normpath(target.lstrip("/"))
                else:
                    resolved = posixpath.normpath(
                        posixpath.join(posixpath.dirname(source_part), target)
                    )
                if resolved not in names:
                    raise TemplateError(
                        f"关系目标不存在: {relationship_name} -> {target}"
                    )


def _load_json(path: Optional[Path]) -> dict[str, Any]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根对象必须是对象: {path}")
    return value


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _parse_literal(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        parsed = json.loads(value)
        if not isinstance(parsed, str):
            raise TemplateError("默认值和格式值必须是字符串")
        return parsed
    return value


def _parse_condition_literal(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        parsed = json.loads(value)
        if isinstance(parsed, (str, int, float, bool)) or parsed is None:
            return parsed
        raise TemplateError("条件字面量必须是 JSON 标量")
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    try:
        return float(value) if "." in value else int(value)
    except ValueError as exc:
        raise TemplateError(f"条件字面量非法: {value}") from exc


def parse_marker(raw: str) -> Marker:
    body = raw[2:-2].strip()
    if body.startswith("field:"):
        parts = body[6:].split("|")
        key = parts[0].strip()
        if not FIELD_PATH_RE.fullmatch(key):
            raise TemplateError(f"字段路径非法: {key}")
        options: dict[str, str] = {}
        for option in parts[1:]:
            name, separator, value = option.partition(":")
            if not separator or name not in {"default", "format"}:
                raise TemplateError(f"字段选项不支持: {option}")
            options[name] = _parse_literal(value)
        return Marker(raw, "field", key, options)
    if body.startswith("#if:"):
        expression = body[4:].strip()
        matched = CONDITION_RE.fullmatch(expression)
        if not matched:
            raise TemplateError(f"条件表达式非法: {expression}")
        options: dict[str, Any] = {}
        if matched.group("operator"):
            options["operator"] = matched.group("operator")
            options["expected"] = _parse_condition_literal(matched.group("literal"))
        return Marker(raw, "if_start", matched.group("path"), options)
    if body == "/if":
        return Marker(raw, "if_end", "", {})
    if body.startswith("#each:"):
        key = body[6:].strip()
        if not FIELD_PATH_RE.fullmatch(key):
            raise TemplateError(f"循环字段路径非法: {key}")
        return Marker(raw, "each_start", key, {})
    if body == "/each":
        return Marker(raw, "each_end", "", {})
    if body.startswith("asset:"):
        key = body[6:].strip()
        if not key:
            raise TemplateError("资产 ID 不能为空")
        return Marker(raw, "asset", key, {})
    if body.startswith("attachment:"):
        key = body[11:].strip()
        if not key:
            raise TemplateError("附件 ID 不能为空")
        return Marker(raw, "attachment", key, {})
    raise TemplateError(f"标记类型不支持: {body}")


def _iter_tables(tables: Iterable[Any]) -> Iterable[Any]:
    for table in tables:
        yield table
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_tables(cell.tables)


def _iter_story_paragraphs(document: Any) -> Iterable[list[Any]]:
    yield list(document.paragraphs)
    for table in _iter_tables(document.tables):
        for row in table.rows:
            for cell in row.cells:
                yield list(cell.paragraphs)
    # Accessing a missing ``section.header``/``section.footer`` through
    # python-docx creates a new empty part.  Inspect section references first
    # so a body-only template keeps its original OOXML package unchanged.
    seen_headers: set[int] = set()
    for section in document.sections:
        references = section._sectPr.xpath("./w:headerReference | ./w:footerReference")
        for reference in references:
            relationship_id = reference.get(qn("r:id"))
            relationship = document.part.rels.get(relationship_id)
            if relationship is None:
                continue
            reference_type = reference.get(qn("w:type"), "default")
            is_header = reference.tag == qn("w:headerReference")
            if is_header:
                story = {
                    "default": section.header,
                    "first": section.first_page_header,
                    "even": section.even_page_header,
                }[reference_type]
            else:
                story = {
                    "default": section.footer,
                    "first": section.first_page_footer,
                    "even": section.even_page_footer,
                }[reference_type]
            identity = id(story._element)
            if identity in seen_headers:
                continue
            seen_headers.add(identity)
            yield list(story.paragraphs)


def _marker_in_one_run(paragraph: Any, raw: str) -> bool:
    return any(raw in (run.text or "") for run in paragraph.runs)


def _collect_markers(document: Any) -> tuple[list[Marker], list[PreflightError]]:
    markers: list[Marker] = []
    errors: list[PreflightError] = []
    for paragraphs in _iter_story_paragraphs(document):
        block_stack: list[Marker] = []
        for paragraph in paragraphs:
            text = paragraph.text or ""
            for match in MARKER_RE.finditer(text):
                raw = match.group(0)
                try:
                    marker = parse_marker(raw)
                except TemplateError as exc:
                    errors.append(PreflightError(
                        "TEMPLATE_MARKER_UNKNOWN", raw, str(exc),
                        "把模板标记改为受支持的显式协议",
                        "停止渲染并重新预检",
                    ))
                    continue
                markers.append(marker)
                if not _marker_in_one_run(paragraph, raw):
                    errors.append(PreflightError(
                        "TEMPLATE_MARKER_SPLIT", raw,
                        "标记被拆到多个 Word run，当前适配器无法安全保持格式",
                        "在模板中把完整标记放入同一个 run",
                        "停止渲染并重新预检",
                    ))
                if marker.kind in {"if_start", "if_end", "each_start", "each_end"} \
                        and text.strip() != raw:
                    errors.append(PreflightError(
                        "TEMPLATE_BLOCK_UNSUPPORTED", raw,
                        "条件或循环块标记必须独立占据一个段落",
                        "把块起止标记移动到独立段落或表格单元格段落",
                        "停止渲染并重新预检",
                    ))
                if marker.kind in {"if_start", "each_start"}:
                    block_stack.append(marker)
                    if marker.kind == "each_start":
                        errors.append(PreflightError(
                            "TEMPLATE_BLOCK_UNSUPPORTED", raw,
                            "第一版尚未实现列表循环的确定性展开",
                            "把列表预展开为目标投影中的文本或表格，或使用支持循环的适配器",
                            "停止渲染并重新预检",
                        ))
                elif marker.kind in {"if_end", "each_end"}:
                    expected = "if_start" if marker.kind == "if_end" else "each_start"
                    if not block_stack or block_stack[-1].kind != expected:
                        errors.append(PreflightError(
                            "TEMPLATE_BLOCK_UNMATCHED", raw,
                            "块结束标记没有匹配的开始标记",
                            "补齐或修正模板中的成对块标记",
                            "停止渲染并重新预检",
                        ))
                    else:
                        block_stack.pop()
        for marker in block_stack:
            errors.append(PreflightError(
                "TEMPLATE_BLOCK_UNMATCHED", marker.raw,
                "块开始标记没有匹配的结束标记",
                "补齐或修正模板中的成对块标记",
                "停止渲染并重新预检",
            ))
    return markers, errors


def _evidence_index(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = value.get("evidence", value.get("records", []))
    if isinstance(records, dict):
        records = list(records.values())
    if not isinstance(records, list):
        return {}
    return {
        item["evidence_id"]: item
        for item in records
        if isinstance(item, dict) and item.get("evidence_id")
    }


def _asset_index(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = value.get("assets", value.get("records", []))
    if isinstance(records, dict):
        records = list(records.values())
    if not isinstance(records, list):
        return {}
    return {
        item["asset_id"]: item
        for item in records
        if isinstance(item, dict) and item.get("asset_id")
    }


def _projection_values(projection: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    values = dict(projection.get("values", {}))
    bindings = projection.get("bindings", {})
    if not isinstance(bindings, dict):
        return values
    for field, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        if "value" in binding:
            values[field] = binding["value"]
            continue
        source = binding.get("source")
        if isinstance(source, str) and source.startswith("evidence:"):
            record = evidence.get(source.split(":", 1)[1])
            if record and record.get("status") not in {"stale", "rejected"} and "value" in record:
                values[field] = record["value"]
    return values


def _required_fields(projection: dict[str, Any]) -> set[str]:
    result = {item for item in projection.get("required", []) if isinstance(item, str)}
    bindings = projection.get("bindings", {})
    if isinstance(bindings, dict):
        result.update(
            field for field, binding in bindings.items()
            if isinstance(binding, dict) and binding.get("required") is True
        )
    return result


def _field_value(
    marker: Marker,
    projection: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> tuple[bool, Any, str]:
    values = _projection_values(projection, evidence)
    states = projection.get("states", {})
    state = states.get(marker.key) if isinstance(states, dict) else None
    if isinstance(state, str) and state in {"null", "unknown", "not_applicable", "empty"}:
        return False, values.get(marker.key), str(state)
    if marker.key in values and values[marker.key] not in (None, ""):
        return True, values[marker.key], "source"
    if marker.key in values:
        return False, values[marker.key], "null" if values[marker.key] is None else "empty"
    defaults = projection.get("defaults", {})
    if isinstance(defaults, dict) and marker.key in defaults:
        return True, defaults[marker.key], "declared_default"
    if "default" in marker.options:
        return True, marker.options["default"], "declared_default"
    return False, None, "missing"


def _field_state_errors(projection: dict[str, Any]) -> list[PreflightError]:
    states = projection.get("states", {})
    if not isinstance(states, dict):
        return []
    return [
        PreflightError(
            "FIELD_STATE_INVALID", str(field),
            f"字段状态不支持: {state}",
            "把字段状态改为 missing、null、unknown、not_applicable 或 empty",
            "停止渲染并重新预检",
        )
        for field, state in states.items()
        if not isinstance(state, str) or state not in FIELD_STATES
    ]


def _projection_errors(projection: dict[str, Any]) -> list[PreflightError]:
    errors: list[PreflightError] = []
    if not isinstance(projection.get("target_id"), str) or not projection.get("target_id"):
        errors.append(PreflightError(
            "PROJECTION_INVALID", "target_id",
            "目标投影缺少非空 target_id",
            "补充目标文档的稳定身份和目标投影版本",
            "停止渲染并重新预检",
        ))
    for field in ("values", "states", "defaults", "bindings", "policies"):
        if field in projection and not isinstance(projection[field], dict):
            errors.append(PreflightError(
                "PROJECTION_INVALID", field,
                f"目标投影字段必须是对象: {field}",
                "修正目标投影的数据类型",
                "停止渲染并重新预检",
            ))
    if "required" in projection and not isinstance(projection["required"], list):
        errors.append(PreflightError(
            "PROJECTION_INVALID", "required",
            "目标投影字段必须是字符串列表: required",
            "修正目标投影的数据类型",
            "停止渲染并重新预检",
        ))
    return errors


def _asset_path(record: dict[str, Any], manifest_path: Optional[Path]) -> Path:
    base = manifest_path.parent if manifest_path else Path.cwd()
    return _resolve_path(str(record.get("path", "")), base)


def _asset_errors(
    markers: list[Marker],
    assets: dict[str, dict[str, Any]],
    assets_path: Optional[Path],
) -> list[PreflightError]:
    errors: list[PreflightError] = []
    for marker in markers:
        if marker.kind not in {"asset", "attachment"}:
            continue
        record = assets.get(marker.key)
        if record is None:
            errors.append(PreflightError(
                "ASSET_NOT_FOUND", marker.key,
                "模板引用的资产 ID 不在资产清单中",
                "补充资产清单或修改模板引用",
                "停止渲染并重新预检",
            ))
            continue
        mode = record.get("mode", "asset_only")
        if mode == "external_reference":
            if not record.get("reference"):
                errors.append(PreflightError(
                    "ASSET_REFERENCE_MISSING", marker.key,
                    "外部引用资产没有 reference 字段",
                    "补充或修改资产清单中的外部引用",
                    "停止渲染并重新预检",
                ))
            continue
        path = _asset_path(record, assets_path)
        if not path.is_file():
            errors.append(PreflightError(
                "ASSET_UNREADABLE", marker.key,
                f"资产文件不存在或不可读: {path}",
                "补充或修改数据源，登记可读取的资产文件",
                "停止渲染并重新预检",
            ))
            continue
        expected = record.get("sha256")
        if not expected:
            errors.append(PreflightError(
                "ASSET_HASH_MISSING", marker.key,
                "资产清单缺少 sha256，无法固定输入版本",
                "重新生成资产清单并记录资产哈希",
                "停止渲染并重新预检",
            ))
        elif _sha256(path) != expected:
            errors.append(PreflightError(
                "ASSET_HASH_MISMATCH", marker.key,
                "资产文件哈希与清单不一致",
                "重新生成资产清单或恢复原始资产",
                "停止渲染并重新预检",
            ))
        media_type = record.get("media_type")
        if not isinstance(media_type, str) or not media_type:
            errors.append(PreflightError(
                "ASSET_MANIFEST_INVALID", marker.key,
                "资产清单缺少非空 media_type",
                "补充资产的媒体类型并重新登记",
                "停止渲染并重新预检",
            ))
            media_type = ""
        suffix_media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
        }
        expected_media_type = suffix_media_types.get(path.suffix.lower())
        if expected_media_type and media_type and expected_media_type != media_type:
            errors.append(PreflightError(
                "ASSET_MEDIA_TYPE_MISMATCH", marker.key,
                f"扩展名与媒体类型不匹配: 扩展名={path.suffix}, 清单={media_type}",
                "修正媒体类型或重新导出并登记资产",
                "停止渲染并重新预检",
            ))
        if media_type.startswith("image/"):
            try:
                image = DocxImage.from_file(str(path))
            except Exception as exc:
                errors.append(PreflightError(
                    "ASSET_UNREADABLE", marker.key,
                    f"图片无法解码: {exc}",
                    "重新导出或替换为可读取的图片资产，并更新哈希",
                    "停止渲染并重新预检",
                ))
            else:
                if image.content_type != media_type:
                    errors.append(PreflightError(
                        "ASSET_MEDIA_TYPE_MISMATCH", marker.key,
                        f"图片媒体类型不匹配: 清单={media_type}, 实际={image.content_type}",
                        "修正媒体类型或重新登记资产",
                        "停止渲染并重新预检",
                    ))
        if marker.kind == "attachment" and mode not in {
            "appendix_file", "external_reference"
        }:
            errors.append(PreflightError(
                "ATTACHMENT_RELATION_UNSUPPORTED", marker.key,
                f"附件模式不支持: {mode}",
                "把附件转换为支持的附录文件或外部引用并重新登记",
                "停止渲染并重新预检",
            ))
        review = record.get("review", {})
        if not isinstance(review, dict):
            errors.append(PreflightError(
                "ASSET_MANIFEST_INVALID", marker.key,
                "资产 review 必须是对象",
                "修正资产清单中的审核记录类型",
                "停止渲染并重新预检",
            ))
            review = {}
        if mode == "visual_observation" and review.get("status") != "approved":
            errors.append(PreflightError(
                "VISUAL_OBSERVATION_UNREVIEWED", marker.key,
                "视觉观察结果尚未完成台账分类审核",
                "补充或修改视觉观察记录并完成分类审核",
                "停止渲染并重新预检",
            ))
        elif mode == "visual_observation":
            observation = record.get("observation")
            extractor = observation.get("extractor") if isinstance(observation, dict) else None
            observation_review = record.get("review")
            valid_observation = (
                isinstance(observation, dict)
                and isinstance(extractor, dict)
                and isinstance(extractor.get("kind"), str)
                and bool(extractor.get("model") or extractor.get("tool"))
                and bool(observation.get("input_sha256"))
                and isinstance(observation.get("observations"), list)
                and isinstance(observation.get("semantic_status"), str)
                and isinstance(observation_review, dict)
                and observation_review.get("required") is True
                and isinstance(observation_review.get("scope"), str)
            )
            if not valid_observation:
                errors.append(PreflightError(
                    "VISUAL_OBSERVATION_PROVENANCE_MISSING", marker.key,
                    "视觉观察缺少完整的提取器、输入哈希、观察结果或审核范围 provenance",
                    "补充模型/工具、输入哈希、结构化观察结果和分类审核范围",
                    "停止渲染并重新预检",
                ))
    return errors


def _visual_binding_errors(
    projection: dict[str, Any],
    assets: dict[str, dict[str, Any]],
) -> list[PreflightError]:
    errors: list[PreflightError] = []
    bindings = projection.get("bindings", {})
    if not isinstance(bindings, dict):
        return errors
    for field, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        observation_id = binding.get("visual_observation_id")
        if not observation_id:
            continue
        asset = assets.get(observation_id)
        if asset is None:
            errors.append(PreflightError(
                "ASSET_NOT_FOUND", str(observation_id),
                f"视觉观察资产不存在: {observation_id}",
                "补充或修改资产清单和目标投影",
                "停止渲染并重新预检",
            ))
            continue
        errors.append(PreflightError(
            "VISUAL_FIELD_NOT_ALLOWED", str(field),
            "视觉观察结果默认只用于台账分类，不能直接绑定事实字段",
            "补充独立证据，或移除该事实字段对视觉观察的绑定",
            "停止渲染并重新预检",
        ))
    return errors


def _evidence_binding_errors(
    projection: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> list[PreflightError]:
    errors: list[PreflightError] = []
    bindings = projection.get("bindings", {})
    if not isinstance(bindings, dict):
        return errors
    for field, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        source = binding.get("source")
        if not isinstance(source, str) or not source.startswith("evidence:"):
            continue
        evidence_id = source.split(":", 1)[1]
        record = evidence.get(evidence_id)
        locator = record.get("locator") if isinstance(record, dict) else None
        locator_kind = locator.get("kind") if isinstance(locator, dict) else None
        locator_valid = (
            isinstance(locator, dict)
            and locator_kind == "paragraph"
            and isinstance(locator.get("index"), int)
        ) or (
            isinstance(locator, dict)
            and locator_kind == "table"
            and all(isinstance(locator.get(key), int) for key in ("table", "row", "column"))
        ) or (
            isinstance(locator, dict)
            and locator_kind == "image"
            and isinstance(locator.get("asset_id"), str)
            and bool(locator.get("asset_id"))
        )
        if record is None:
            errors.append(PreflightError(
                "EVIDENCE_NOT_FOUND", str(field),
                f"目标字段引用的证据不存在: {evidence_id}",
                "补充或修改证据台账",
                "停止渲染并重新预检",
            ))
        elif (
            not record.get("source_file")
            or not record.get("source_sha256")
            or not record.get("normalized_text_sha256")
            or not isinstance(record.get("status"), str)
            or not locator_valid
        ):
            errors.append(PreflightError(
                "EVIDENCE_LOCATOR_INVALID", str(field),
                f"证据缺少源文件、文件哈希或结构定位: {evidence_id}",
                "补充文件 + 段落/表格索引及源文件哈希后更新证据台账",
                "停止渲染并重新预检",
            ))
        elif record.get("status") == "stale":
            errors.append(PreflightError(
                "EVIDENCE_STALE", str(field),
                f"证据已因源文件变化失效: {evidence_id}",
                "根据新的源文件重新建立证据定位和哈希",
                "停止渲染并重新预检",
            ))
        elif record.get("status") == "rejected":
            errors.append(PreflightError(
                "EVIDENCE_REJECTED", str(field),
                f"证据已被拒绝: {evidence_id}",
                "补充可接受的证据并更新目标投影",
                "停止渲染并重新预检",
            ))
    return errors


def _default_conflicts(
    markers: list[Marker],
    projection: dict[str, Any],
) -> list[PreflightError]:
    projection_defaults = projection.get("defaults", {})
    if not isinstance(projection_defaults, dict):
        projection_defaults = {}
    declared: dict[str, list[Any]] = {}
    for marker in markers:
        if marker.kind != "field" or "default" not in marker.options:
            continue
        declared.setdefault(marker.key, []).append(marker.options["default"])
    errors: list[PreflightError] = []
    for field, values in declared.items():
        distinct = []
        for value in values:
            if value not in distinct:
                distinct.append(value)
        if field in projection_defaults and projection_defaults[field] not in distinct:
            distinct.append(projection_defaults[field])
        if len(distinct) > 1:
            errors.append(PreflightError(
                "DEFAULT_CONFLICT", field,
                "模板和目标投影为同一字段声明了不同默认值",
                "保留唯一的默认值声明，或删除其中一个默认值",
                "停止渲染并重新预检",
            ))
    return errors


def _materialize_template_defaults(
    projection: dict[str, Any], markers: list[Marker]
) -> dict[str, Any]:
    result = dict(projection)
    defaults = dict(projection.get("defaults", {})) if isinstance(
        projection.get("defaults", {}), dict
    ) else {}
    for marker in markers:
        if marker.kind == "field" and "default" in marker.options:
            defaults.setdefault(marker.key, marker.options["default"])
    if defaults:
        result["defaults"] = defaults
    return result


def _marker_format(marker: Marker, projection: dict[str, Any]) -> Optional[str]:
    if marker.options.get("format"):
        return str(marker.options["format"])
    bindings = projection.get("bindings", {})
    binding = bindings.get(marker.key) if isinstance(bindings, dict) else None
    if isinstance(binding, dict) and binding.get("format"):
        return str(binding["format"])
    return None


def _format_date(value: Any, format_name: str) -> str:
    if format_name != "YYYY-MM-DD":
        raise TemplateError(f"格式不支持: {format_name}")
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value)
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return text
        raise TemplateError(f"值无法按 {format_name} 格式化: {text}")


def _format_errors(
    markers: list[Marker],
    projection: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> list[PreflightError]:
    errors: list[PreflightError] = []
    for marker in markers:
        if marker.kind != "field":
            continue
        format_name = _marker_format(marker, projection)
        if not format_name:
            continue
        if format_name not in SUPPORTED_FORMATS:
            errors.append(PreflightError(
                "FORMAT_UNSUPPORTED", marker.key,
                f"格式未由当前适配器实现: {format_name}",
                "改用受支持的格式，或由适配器先物化格式化值",
                "停止渲染并重新预检",
            ))
            continue
        available, value, _ = _field_value(marker, projection, evidence)
        if available:
            try:
                _format_date(value, format_name)
            except TemplateError as exc:
                errors.append(PreflightError(
                    "FORMAT_VALUE_INVALID", marker.key, str(exc),
                    "补充符合格式的源值或修改字段格式声明",
                    "停止渲染并重新预检",
                ))
    return errors


def preflight(
    template: Path | str,
    projection: Path | str,
    evidence: Optional[Path | str] = None,
    assets: Optional[Path | str] = None,
    report: Optional[Path | str] = None,
) -> PreflightResult:
    template_path = Path(template).expanduser().resolve()
    projection_path = Path(projection).expanduser().resolve()
    evidence_path = Path(evidence).expanduser().resolve() if evidence else None
    assets_path = Path(assets).expanduser().resolve() if assets else None
    errors: list[PreflightError] = []
    markers: list[Marker] = []
    if not template_path.is_file():
        errors.append(PreflightError(
            "TEMPLATE_UNREADABLE", str(template_path), "模板文件不存在或不可读",
            "补充或修改数据源，提供可读取的 DOCX/DOTX 模板",
            "停止渲染并重新预检",
        ))
    else:
        errors.extend(_template_package_errors(template_path))
    try:
        projection_value = _load_json(projection_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        projection_value = {}
        errors.append(PreflightError(
            "PROJECTION_UNREADABLE", str(projection_path), str(exc),
            "补充或修改目标投影文件",
            "停止渲染并重新预检",
        ))
    try:
        evidence_value = _load_json(evidence_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        evidence_value = {}
        errors.append(PreflightError(
            "EVIDENCE_LEDGER_UNREADABLE", str(evidence_path), str(exc),
            "补充或修改证据台账",
            "停止渲染并重新预检",
        ))
    try:
        assets_value = _load_json(assets_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        assets_value = {}
        errors.append(PreflightError(
            "ASSET_MANIFEST_UNREADABLE", str(assets_path), str(exc),
            "补充或修改资产清单",
            "停止渲染并重新预检",
        ))
    if template_path.is_file():
        try:
            document = Document(str(template_path))
            markers, marker_errors = _collect_markers(document)
            errors.extend(marker_errors)
        except Exception as exc:  # python-docx exposes several package exceptions
            errors.append(PreflightError(
                "TEMPLATE_UNREADABLE", str(template_path), str(exc),
                "补充或修改数据源，提供可读取的 DOCX/DOTX 模板",
                "停止渲染并重新预检",
            ))
    evidence_index = _evidence_index(evidence_value)
    assets_index = _asset_index(assets_value)
    errors.extend(_projection_errors(projection_value))
    errors.extend(_field_state_errors(projection_value))
    errors.extend(_default_conflicts(markers, projection_value))
    errors.extend(_format_errors(markers, projection_value, evidence_index))
    errors.extend(_evidence_binding_errors(projection_value, evidence_index))
    errors.extend(_visual_binding_errors(projection_value, assets_index))
    used_fields = {
        marker.key for marker in markers
        if marker.kind in {"field", "if_start"}
    }
    required = _required_fields(projection_value)
    for field in sorted(required - used_fields):
        errors.append(PreflightError(
            "FIELD_NOT_BOUND", field,
            "目标投影要求的字段没有对应模板锚点",
            "补充模板锚点或修改目标投影",
            "停止渲染并重新预检",
        ))
    for marker in markers:
        if marker.kind != "field":
            continue
        available, _, source = _field_value(marker, projection_value, evidence_index)
        if not available and marker.key in required:
            error_code = (
                "FIELD_STATE_UNUSABLE"
                if source in FIELD_STATES and source != "missing"
                else "FIELD_REQUIRED_MISSING"
            )
            errors.append(PreflightError(
                error_code, marker.key,
                f"字段没有可用于必填绑定的值（状态: {source}）",
                "补充或修改数据源；默认值只对 missing 状态生效",
                "停止渲染并重新预检",
            ))
    errors.extend(_asset_errors(markers, assets_index, assets_path))
    result = PreflightResult(
        "blocked" if errors else "ready",
        errors,
        markers,
        _sha256(template_path) if template_path.is_file() else "",
    )
    if report:
        report_path = Path(report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _truthy(value: Any) -> bool:
    if value is None or value is False or value == "":
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _condition_matches(
    marker: Marker,
    projection: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> bool:
    available, value, _ = _field_value(
        Marker("", "field", marker.key, {}), projection, evidence
    )
    if not available:
        return False
    operator = marker.options.get("operator")
    if operator == "==":
        return value == marker.options.get("expected")
    if operator == "!=":
        return value != marker.options.get("expected")
    return _truthy(value)


def _remove_paragraph(paragraph: Any) -> None:
    element = paragraph._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _paragraph_is_marker(paragraph: Any, kind: str) -> Optional[Marker]:
    text = (paragraph.text or "").strip()
    matches = list(MARKER_RE.finditer(text))
    if len(matches) != 1 or matches[0].group(0) != text:
        return None
    try:
        marker = parse_marker(text)
    except TemplateError:
        return None
    return marker if marker.kind == kind else None


def _replace_field_markers(
    paragraph: Any,
    projection: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> list[str]:
    used_defaults: list[str] = []
    for match in list(MARKER_RE.finditer(paragraph.text or "")):
        raw = match.group(0)
        marker = parse_marker(raw)
        if marker.kind != "field":
            continue
        available, value, source = _field_value(marker, projection, evidence)
        if not available:
            value = ""
        format_name = _marker_format(marker, projection)
        if available and format_name:
            value = _format_date(value, format_name)
        replacement = _stringify(value)
        replaced = False
        for run in paragraph.runs:
            if raw in (run.text or ""):
                run.text = run.text.replace(raw, replacement)
                replaced = True
                break
        if not replaced:
            raise TemplateError(f"渲染时找不到单一 run 中的标记: {raw}")
        if source == "declared_default":
            used_defaults.append(marker.key)
    return used_defaults


def _insert_asset(
    paragraph: Any,
    marker: Marker,
    assets: dict[str, dict[str, Any]],
    assets_path: Optional[Path],
    output_dir: Path,
) -> list[str]:
    record = assets[marker.key]
    source = _asset_path(record, assets_path)
    mode = record.get("mode", "asset_only")
    if mode in {"asset_only", "table_image"}:
        paragraph.clear()
        run = paragraph.add_run()
        width = record.get("width_inches")
        if width is None:
            run.add_picture(str(source))
        else:
            run.add_picture(str(source), width=Inches(float(width)))
        return [marker.key]
    if mode == "external_reference":
        paragraph.clear()
        paragraph.add_run(str(record.get("label") or record.get("reference")))
        return [marker.key]
    if mode == "appendix_file":
        appendix_dir = output_dir / "attachments"
        appendix_dir.mkdir(parents=True, exist_ok=True)
        target = appendix_dir / source.name
        shutil.copy2(source, target)
        paragraph.clear()
        paragraph.add_run(str(record.get("label", f"附件：{source.name}")))
        return [marker.key]
    raise TemplateError(f"附件模式不支持: {mode}")


def _process_story(
    paragraphs: list[Any],
    projection: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    assets: dict[str, dict[str, Any]],
    assets_path: Optional[Path],
    output_dir: Path,
) -> tuple[list[str], list[str]]:
    used_defaults: list[str] = []
    used_assets: list[str] = []
    condition_stack: list[bool] = []
    for paragraph in list(paragraphs):
        start = _paragraph_is_marker(paragraph, "if_start")
        end = _paragraph_is_marker(paragraph, "if_end")
        if start is not None:
            condition_stack.append(_condition_matches(start, projection, evidence))
            _remove_paragraph(paragraph)
            continue
        if end is not None:
            if condition_stack:
                condition_stack.pop()
            _remove_paragraph(paragraph)
            continue
        if condition_stack and not all(condition_stack):
            _remove_paragraph(paragraph)
            continue
        text = paragraph.text or ""
        for match in list(MARKER_RE.finditer(text)):
            marker = parse_marker(match.group(0))
            if marker.kind == "field":
                continue
            if marker.kind == "asset" and text.strip() == match.group(0):
                used_assets.extend(
                    _insert_asset(paragraph, marker, assets, assets_path, output_dir)
                )
            elif marker.kind == "attachment" and text.strip() == match.group(0):
                used_assets.extend(
                    _insert_asset(paragraph, marker, assets, assets_path, output_dir)
                )
            else:
                raise TemplateError(f"资产或附件标记必须占据独立段落: {match.group(0)}")
        used_defaults.extend(_replace_field_markers(paragraph, projection, evidence))
    return used_defaults, used_assets


def _used_evidence_ids(
    projection: dict[str, Any],
    markers: list[Marker],
) -> list[str]:
    bindings = projection.get("bindings", {})
    if not isinstance(bindings, dict):
        return []
    fields = {
        marker.key for marker in markers
        if marker.kind in {"field", "if_start"}
    }
    result: list[str] = []
    for field in sorted(fields):
        binding = bindings.get(field)
        if not isinstance(binding, dict):
            continue
        source = binding.get("source")
        if isinstance(source, str) and source.startswith("evidence:"):
            result.append(source.split(":", 1)[1])
    return result


def render(
    template: Path | str,
    projection: Path | str,
    output: Path | str,
    evidence: Optional[Path | str] = None,
    assets: Optional[Path | str] = None,
    report: Optional[Path | str] = None,
) -> PreflightResult:
    output_path = Path(output).expanduser().resolve()
    report_path = Path(report).expanduser().resolve() if report else None
    target_attachment_dir = output_path.parent / f"{output_path.stem}.attachments"
    result = preflight(template, projection, evidence, assets, report)
    if result.status == "blocked":
        return result
    if output_path.exists() or target_attachment_dir.exists():
        result.status = "blocked"
        result.errors.append(PreflightError(
            "OUTPUT_EXISTS", str(output_path), "输出文件或附件目录已存在，默认不覆盖",
            "选择新的输出路径或明确授权覆盖",
            "停止渲染并重新运行",
        ))
        if report_path:
            report_path.write_text(
                json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return result
    template_path = Path(template).expanduser().resolve()
    projection_path = Path(projection).expanduser().resolve()
    evidence_path = Path(evidence).expanduser().resolve() if evidence else None
    assets_path = Path(assets).expanduser().resolve() if assets else None
    projection_value = _materialize_template_defaults(
        _load_json(projection_path), result.markers
    )
    evidence_value = _load_json(evidence_path)
    assets_value = _load_json(assets_path)
    evidence_index = _evidence_index(evidence_value)
    assets_index = _asset_index(assets_value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="word-template-", dir=str(output_path.parent)) as temp_dir:
        temp_output = Path(temp_dir) / output_path.name
        shutil.copy2(template_path, temp_output)
        document = Document(str(temp_output))
        used_defaults: list[str] = []
        used_assets: list[str] = []
        staged_attachment_dir: Optional[Path] = None
        try:
            for story in _iter_story_paragraphs(document):
                story_defaults, story_assets = _process_story(
                    story, projection_value, evidence_index, assets_index,
                    assets_path, Path(temp_dir),
                )
                used_defaults.extend(story_defaults)
                used_assets.extend(story_assets)
            document.save(temp_output)
            _validate_package_structure(temp_output)
            check = Document(str(temp_output))
            residual = [
                match.group(0)
                for story in _iter_story_paragraphs(check)
                for paragraph in story
                for match in MARKER_RE.finditer(paragraph.text or "")
            ]
            if residual:
                raise TemplateError(f"渲染后仍有未解析标记: {residual}")
            temp_attachment_dir = Path(temp_dir) / "attachments"
            if temp_attachment_dir.is_dir():
                staged_attachment_dir = output_path.parent / (
                    f".{output_path.stem}.attachments.stage-{Path(temp_dir).name}"
                )
                shutil.copytree(temp_attachment_dir, staged_attachment_dir)
            temp_output.replace(output_path)
            if staged_attachment_dir is not None:
                try:
                    staged_attachment_dir.replace(target_attachment_dir)
                except Exception:
                    output_path.unlink(missing_ok=True)
                    shutil.rmtree(staged_attachment_dir, ignore_errors=True)
                    raise
        except Exception as exc:
            if staged_attachment_dir is not None:
                shutil.rmtree(staged_attachment_dir, ignore_errors=True)
            result.status = "failed"
            result.errors.append(PreflightError(
                "RENDER_VERIFY_FAILED", str(output_path), str(exc),
                "补充或修改模板、数据源或资产后重新预检",
                "保持失败状态并根据错误对象修复后重跑",
            ))
            if report_path:
                report_path.write_text(
                    json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            return result
    result.status = "structural_ready"
    report_data = result.as_dict()
    report_data.update(_run_metadata(
        template_path, projection_path, evidence_path, assets_path,
        evidence_value, assets_value,
    ))
    report_data.update({
        "output": str(output_path),
        "used_defaults": sorted(set(used_defaults)),
        "used_assets": sorted(set(used_assets)),
        "used_evidence": _used_evidence_ids(projection_value, result.markers),
        "structural_check": "package_passed",
        "visual_check": "not_run",
    })
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


def verify_visual(
    document: Path | str,
    report: Path | str,
    visual_output: Path | str,
    *,
    accept: bool = False,
) -> PreflightResult:
    """Generate visual pages and optionally record explicit visual acceptance."""
    document_path = Path(document).expanduser().resolve()
    report_path = Path(report).expanduser().resolve()
    visual_output_path = Path(visual_output).expanduser().resolve()
    report_value = json.loads(report_path.read_text(encoding="utf-8"))
    current_status = report_value.get("status")
    if current_status not in {"structural_ready", "visual_ready"}:
        return PreflightResult(
            current_status or "failed", [], [], report_value.get("template_sha256", "")
        )
    if visual_output_path.exists():
        existing_pages = list(visual_output_path.glob("page-*.png"))
        if (
            accept
            and report_value.get("visual_output") == str(visual_output_path)
            and existing_pages
        ):
            report_value.update({"status": "rendered", "visual_check": "passed"})
            report_path.write_text(
                json.dumps(report_value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return PreflightResult("rendered", [], [], report_value.get("template_sha256", ""))
        error = PreflightError(
            "OUTPUT_EXISTS", str(visual_output_path),
            "视觉验证输出目录已存在，默认不覆盖",
            "选择新的视觉输出目录或清理旧目录后重跑",
            "停止视觉验证并重新运行",
        )
        report_value.update({"status": "failed", "visual_check": "failed"})
        report_path.write_text(
            json.dumps(report_value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return PreflightResult("failed", [error], [], report_value.get("template_sha256", ""))
    renderer = Path(__file__).resolve().parents[2] / "word" / "scripts" / "render_docx.py"
    try:
        completed = subprocess.run(
            [sys.executable, str(renderer), str(document_path), str(visual_output_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        completed = None
        detail = str(exc)
    else:
        detail = (completed.stderr or completed.stdout or "").strip()
    pages = list(visual_output_path.glob("page-*.png")) if visual_output_path.is_dir() else []
    if completed is None or completed.returncode != 0 or not pages:
        error = PreflightError(
            "RENDER_VERIFY_FAILED", str(document_path),
            detail or "视觉渲染器没有生成逐页 PNG",
            "补充字体/LibreOffice/Poppler 或修改模板后重跑视觉验证",
            "保持失败状态，不把 DOCX 标记为最终交付",
        )
        report_value.update({"status": "failed", "visual_check": "failed"})
        report_path.write_text(
            json.dumps(report_value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return PreflightResult("failed", [error], [], report_value.get("template_sha256", ""))
    report_value.update({
        "status": "rendered" if accept else "visual_ready",
        "visual_check": "passed" if accept else "generated",
        "visual_output": str(visual_output_path),
    })
    report_path.write_text(
        json.dumps(report_value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return PreflightResult(
        report_value["status"], [], [], report_value.get("template_sha256", "")
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DOCX 模板确定性预检与渲染")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "render"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--template", required=True, type=Path)
        sub.add_argument("--projection", required=True, type=Path)
        sub.add_argument("--evidence", type=Path)
        sub.add_argument("--assets", type=Path)
        sub.add_argument("--report", type=Path, required=True)
        if command == "render":
            sub.add_argument("--output", required=True, type=Path)
    verify = subparsers.add_parser("verify", help="生成视觉页并记录视觉验收")
    verify.add_argument("--document", required=True, type=Path)
    verify.add_argument("--report", required=True, type=Path)
    verify.add_argument("--visual-output", required=True, type=Path)
    verify.add_argument(
        "--accept-visual",
        action="store_true",
        help="已人工检查逐页 PNG 后，将报告状态置为 rendered",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "verify":
        result = verify_visual(
            document=args.document,
            report=args.report,
            visual_output=args.visual_output,
            accept=args.accept_visual,
        )
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0 if result.status == "rendered" else 3
    result = preflight(
        template=args.template,
        projection=args.projection,
        evidence=args.evidence,
        assets=args.assets,
        report=args.report,
    )
    if args.command == "preflight":
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0 if result.status == "ready" else 2
    rendered = render(
        template=args.template,
        projection=args.projection,
        output=args.output,
        evidence=args.evidence,
        assets=args.assets,
        report=args.report,
    )
    print(json.dumps(rendered.as_dict(), ensure_ascii=False, indent=2))
    return 0 if rendered.status == "rendered" else 3


if __name__ == "__main__":
    raise SystemExit(main())
