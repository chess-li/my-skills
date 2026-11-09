#!/usr/bin/env python3
"""Create editable XLSX templates for the two companion workbooks.

Workbook layout lives in these template files, not in the render script:
sheet names, headers, column widths, statistics formulas, freeze panes,
auto-filters, data validation, conditional formatting and colors are all
baked in here.  Each data sheet carries one marker row whose cells hold
``{{ key }}`` tokens; ``scripts/generate_rd_docs.py`` finds the marker row,
copies its style per data item and replaces scalar ``{{ name }}`` cells
inline.  Changing the layout means editing this script (or the generated
file) — never the render pipeline.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation


BLUE = "1F4E79"
LIGHT_GREEN = "E2F0D9"
LIGHT_AMBER = "FFF2CC"
LIGHT_RED = "FCE4D6"
DATA_RANGE_END = 500  # fixed generous range for formulas/validation/formatting

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor=BLUE)
DATA_ALIGNMENT = Alignment(vertical="top", wrap_text=True)

# 00-研发加计工作底稿 sheets: (sheet name, [(header, marker key), ...])
WORKING_SHEETS = [
    ("资料清单", [
        ("资料编号", "id"), ("文件名", "name"), ("相对路径", "relative_path"),
        ("文件类型", "file_type"), ("资料类别", "category"), ("对应项目", "project"),
        ("覆盖年度", "year"), ("形成日期", "date"), ("主要用途", "purpose"),
        ("可读性", "readability"), ("来源状态", "status"), ("备注", "note"),
    ]),
    ("统一研发活动要素", [
        ("要素编号", "id"), ("要素名称", "name"), ("统一值", "value"),
        ("状态", "status"), ("来源资料编号", "source_id"), ("来源位置", "source_location"),
        ("相关 Hxx", "placeholder"), ("备注", "note"),
    ]),
    ("事实与来源索引", [
        ("事实编号", "id"), ("事实摘要", "summary"), ("原文/数据摘要", "excerpt"),
        ("来源文件", "source"), ("页码/表名/段落", "location"), ("资料类别", "category"),
        ("可信状态", "confidence"), ("使用文档", "documents"), ("备注", "note"),
    ]),
    ("文档投射矩阵", [
        ("统一要素", "element"), ("立项决议处理", "decision"), ("项目计划书处理", "plan"),
        ("成果效用说明处理", "outcome"), ("时点限制", "time_limit"), ("来源状态", "status"),
        ("待补编号", "placeholder"),
    ]),
    ("一致性核对", [
        ("核对项", "item"), ("立项决议值", "decision"), ("项目计划书值", "plan"),
        ("成果效用说明值", "outcome"), ("辅助账/原始资料值", "source"), ("是否一致", "consistent"),
        ("来源", "reference"), ("处理动作", "action"),
    ]),
    ("待补信息", [
        ("Hxx", "id"), ("待补事项", "request"), ("影响文档", "documents"),
        ("首次出现章节", "location"), ("来源冲突/缺口", "gap"), ("建议提供材料", "suggested_material"),
        ("责任部门", "owner"), ("优先级", "priority"), ("状态", "status"), ("备注", "note"),
    ]),
]

COLUMN_WIDTHS = {"A": 20, "B": 30, "C": 32, "D": 28, "E": 28, "F": 24,
                 "G": 20, "H": 22, "I": 18, "J": 24, "K": 18, "L": 24}

SUPPLEMENT_HEADERS = [
    ("编号", "id"), ("Word页码（word项）", "pages"), ("Word章节/位置（word项）", "location"),
    ("当前占位文字", "placeholder"), ("需要补充什么信息", "request"), ("建议填写格式", "format"),
    ("建议责任部门", "owner"), ("优先级", "priority"), ("填写状态", "status"), ("备注", "note"),
]

INSTRUCTION_ROWS = [
    "word 通道编号 Hxx 与三份 DOCX 占位符一一对应；list 通道编号 Lxx 只用于清单定位，不对应 DOCX，也不填写 Word 页码。",
    "word 通道按最终 Word 页码和章节位置填写；list 通道按来源材料记录。不得用推测值替代原始材料事实。",
    "Word 内容或分页变化后，复核 word 通道 Hxx 集合与页码/章节；list 通道不填写 Word 页码。",
]


def style_header(sheet, headers: list[str]) -> None:
    for index, title in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=index, value=title)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"


def style_sheet_view(sheet, widths: dict[str, int], last_column: int, header_row: int = 1) -> None:
    sheet.sheet_view.showGridLines = False
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(last_column)}{header_row}"


def add_marker_row(sheet, row: int, keys: list[str]) -> None:
    for index, key in enumerate(keys, start=1):
        cell = sheet.cell(row=row, column=index, value=f"{{{{ {key} }}}}")
        cell.alignment = DATA_ALIGNMENT


def create_workbook_template(path: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, columns in WORKING_SHEETS:
        sheet = workbook.create_sheet(sheet_name)
        style_header(sheet, [header for header, _ in columns])
        add_marker_row(sheet, 2, [key for _, key in columns])
        style_sheet_view(sheet, COLUMN_WIDTHS, len(columns))
    workbook.save(path)


def create_supplement_template(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "补充信息清单"
    end = DATA_RANGE_END

    title = sheet.cell(row=1, column=1, value="{{ project_name }}—补充信息清单")
    title.font = Font(bold=True, size=14, color=BLUE)
    sheet.cell(
        row=2,
        column=1,
        value="word 通道请根据 Word 页码和章节位置补充确认事实；list 通道只作清单留痕，不填写 Word 页码；完成后将状态改为已完成。",
    )

    stats = ["待补项总数", "高优先级数量", "已完成数量", "完成率"]
    for index, label in enumerate(stats, start=1):
        cell = sheet.cell(row=4, column=index, value=label)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    sheet.cell(row=5, column=1, value=f"=COUNTA(A8:A{end})")
    sheet.cell(row=5, column=2, value=f'=COUNTIF(H8:H{end},"高")')
    sheet.cell(row=5, column=3, value=f'=COUNTIF(I8:I{end},"已完成")')
    sheet.cell(row=5, column=4, value="=IFERROR(C5/A5,0)")
    sheet.cell(row=5, column=4).number_format = "0.0%"

    style_header_row = 7
    for index, (header, _) in enumerate(SUPPLEMENT_HEADERS, start=1):
        cell = sheet.cell(row=style_header_row, column=index, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    add_marker_row(sheet, 8, [key for _, key in SUPPLEMENT_HEADERS])

    priority = DataValidation(type="list", formula1='"高,中,低"', allow_blank=True)
    status = DataValidation(type="list", formula1='"未填写,填写中,待复核,已完成"', allow_blank=True)
    sheet.add_data_validation(priority)
    sheet.add_data_validation(status)
    priority.add(f"H8:H{end}")
    status.add(f"I8:I{end}")
    sheet.conditional_formatting.add(f"H8:H{end}", CellIsRule(operator="equal", formula=['"高"'], fill=PatternFill("solid", fgColor=LIGHT_RED)))
    sheet.conditional_formatting.add(f"I8:I{end}", CellIsRule(operator="equal", formula=['"未填写"'], fill=PatternFill("solid", fgColor=LIGHT_AMBER)))
    sheet.conditional_formatting.add(f"I8:I{end}", CellIsRule(operator="equal", formula=['"已完成"'], fill=PatternFill("solid", fgColor=LIGHT_GREEN)))

    sheet.freeze_panes = "A8"
    sheet.auto_filter.ref = f"A{style_header_row}:J{style_header_row}"
    style_sheet_view(sheet, {"A": 12, "B": 12, "C": 28, "D": 25, "E": 32, "F": 25,
                             "G": 16, "H": 10, "I": 12, "J": 24}, len(SUPPLEMENT_HEADERS),
                     header_row=style_header_row)

    notes = workbook.create_sheet("填写说明")
    notes.cell(row=1, column=1, value="填写说明").font = Font(bold=True, size=14, color=BLUE)
    for index, text in enumerate(INSTRUCTION_ROWS, start=2):
        notes.cell(row=index, column=1, value=text).alignment = DATA_ALIGNMENT
    style_sheet_view(notes, {"A": 120}, 1)
    notes.auto_filter.ref = None  # 说明页不需要筛选

    workbook.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    create_workbook_template(args.output_dir / "00-研发加计工作底稿-template.xlsx")
    create_supplement_template(args.output_dir / "04-补充信息清单-template.xlsx")


if __name__ == "__main__":
    main()
