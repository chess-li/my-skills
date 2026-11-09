#!/usr/bin/env python3
"""Build a cross-project supplement workbook from project facts JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

try:
    from .data_model import as_text
except ImportError:  # Running as a script from the skill root.
    from data_model import as_text  # type: ignore[no-redef]


SUMMARY_HEADERS = (
    "项目",
    "编号",
    "Word页码",
    "Word章节/位置",
    "当前占位文字",
    "需要补充什么信息",
    "建议填写格式",
    "责任部门",
    "优先级",
    "填写状态",
    "备注",
    "通道",
)
DEPARTMENT_HEADERS = ("责任部门", "待办项数", "高优先级", "涉及项目")
PRIORITY_ORDER = {"高": 0, "中": 1, "低": 2}
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def _cell_text(value: Any) -> str | None:
    text = as_text(value).strip()
    return text or None


def _read_facts(path: Path) -> list[dict[str, str | None]]:
    facts = json.loads(path.read_text(encoding="utf-8"))
    project = as_text(facts.get("project_name")).strip()
    if not project:
        raise ValueError(f"{path}: project_name is required")
    supplements = facts.get("supplements", [])
    if not isinstance(supplements, list) or any(not isinstance(item, dict) for item in supplements):
        raise ValueError(f"{path}: supplements must be a list of objects")

    rows = []
    for item in supplements:
        rows.append(
            {
                "project": project,
                "id": _cell_text(item.get("id")),
                "pages": _cell_text(item.get("pages")),
                "location": _cell_text(item.get("location")),
                "placeholder": _cell_text(item.get("placeholder")),
                "request": _cell_text(item.get("request", item.get("what_to_provide"))),
                "format": _cell_text(item.get("format")),
                "owner": _cell_text(item.get("owner", item.get("department"))) or "未指定部门",
                "priority": _cell_text(item.get("priority")) or "中",
                "status": _cell_text(item.get("status")) or "未填写",
                "note": _cell_text(item.get("note")),
                "channel": _cell_text(item.get("channel")) or "word",
            }
        )
    return rows


def _style_header(sheet, widths: dict[str, int]) -> None:
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.showGridLines = False
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width


def generate_summary(input_paths: list[Path], output_path: Path) -> dict[str, int]:
    if not input_paths:
        raise ValueError("at least one project facts JSON file is required")

    rows = [row for path in input_paths for row in _read_facts(path)]
    project_order: dict[str, int] = {}
    for row in rows:
        project = row["project"] or ""
        if project and project not in project_order:
            project_order[project] = len(project_order)
    rows.sort(
        key=lambda row: (
            row["owner"] or "",
            PRIORITY_ORDER.get(row["priority"] or "", 3),
        )
    )

    workbook = Workbook()
    summary = workbook.active
    summary.title = "补充信息汇总"
    summary.append(SUMMARY_HEADERS)
    for row in rows:
        summary.append(
            [
                row["project"],
                row["id"],
                row["pages"],
                row["location"],
                row["placeholder"],
                row["request"],
                row["format"],
                row["owner"],
                row["priority"],
                row["status"],
                row["note"],
                row["channel"],
            ]
        )
    _style_header(
        summary,
        {"A": 30, "B": 12, "C": 14, "D": 24, "E": 32, "F": 42,
         "G": 24, "H": 20, "I": 12, "J": 16, "K": 32, "L": 12},
    )

    departments: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "high": 0, "projects": []}
    )
    for row in rows:
        owner = row["owner"] or "未指定部门"
        department = departments[owner]
        department["count"] += 1
        department["high"] += row["priority"] == "高"
        project = row["project"] or ""
        if project and project not in department["projects"]:
            department["projects"].append(project)

    department_sheet = workbook.create_sheet("分部门统计")
    department_sheet.append(DEPARTMENT_HEADERS)
    for owner in sorted(departments):
        stats = departments[owner]
        projects = "、".join(sorted(stats["projects"], key=lambda project: project_order[project]))
        department_sheet.append((owner, stats["count"], stats["high"], projects))
    _style_header(department_sheet, {"A": 24, "B": 16, "C": 16, "D": 60})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    workbook.close()
    return {"rows": len(rows), "departments": len(departments)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", action="store_true", help="generate a cross-project summary")
    parser.add_argument("--input", nargs="*", type=Path, default=[], help="project facts JSON files")
    parser.add_argument("--output", required=True, type=Path, help="summary XLSX output path")
    args = parser.parse_args()
    if not args.batch:
        print(json.dumps({"ok": True, "skipped": True, "reason": "batch is false"}, ensure_ascii=False))
        return
    try:
        result = generate_summary(args.input, args.output)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps({"ok": True, "output": str(args.output), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
