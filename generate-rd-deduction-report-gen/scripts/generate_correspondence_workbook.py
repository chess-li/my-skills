#!/usr/bin/env python3
"""Render model-prepared material mappings and audit questions to XLSX."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


MATERIAL_HEADERS = (
    "序号",
    "原始材料",
    "材料位置",
    "拟归属项目",
    "对应最终文档",
    "对应依据",
    "审核状态",
    "备注",
)
QUESTION_HEADERS = ("序号", "事项", "待确认问题", "建议裁定", "用户裁定", "状态", "证据/备注")
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def _rows(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{key} must be a list of objects")
    return value


def _text(item: Mapping[str, Any], key: str, default: str = "") -> str:
    value = item.get(key, default)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "；".join(str(part) for part in value)
    return str(value)


def _style_sheet(sheet, widths: tuple[int, ...]) -> None:
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.showGridLines = False
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def generate_correspondence_workbook(input_path: Path, output_path: Path) -> dict[str, int]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("input JSON root must be an object")
    materials = _rows(payload, "materials")
    questions = _rows(payload, "questions")

    workbook = Workbook()
    material_sheet = workbook.active
    material_sheet.title = "材料对应表"
    material_sheet.append(MATERIAL_HEADERS)
    for index, item in enumerate(materials, start=1):
        material_sheet.append(
            (
                index,
                _text(item, "source_file"),
                _text(item, "source_location"),
                _text(item, "project_name"),
                _text(item, "report_document"),
                _text(item, "match_basis"),
                _text(item, "status", "待确认"),
                _text(item, "note"),
            )
        )
    _style_sheet(material_sheet, (10, 34, 22, 28, 30, 42, 16, 32))

    question_sheet = workbook.create_sheet("待确认事项")
    question_sheet.append(QUESTION_HEADERS)
    for index, item in enumerate(questions, start=1):
        question_sheet.append(
            (
                index,
                _text(item, "topic"),
                _text(item, "question"),
                _text(item, "proposal"),
                _text(item, "decision"),
                _text(item, "status", "待确认"),
                _text(item, "evidence"),
            )
        )
    _style_sheet(question_sheet, (10, 20, 42, 28, 28, 16, 42))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    workbook.close()
    return {"materials": len(materials), "questions": len(questions)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="model-prepared correspondence JSON")
    parser.add_argument("--output", required=True, type=Path, help="audit workbook output path")
    args = parser.parse_args()
    try:
        result = generate_correspondence_workbook(args.input, args.output)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps({"ok": True, "output": str(args.output), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
