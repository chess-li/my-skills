#!/usr/bin/env python3
"""TPD 声明式模板填充与书签对齐脚本 (render node)

读取 Base Word 文档与 mapping_plan.json，按声明的映射关系：
1. 更新 Word 表格中的数据行与合计行；
2. 为表格与关键数据段落建立同步书签 (TPL_TR_xxxxxx)，保证两端 100% 精确 Diff 对齐；
3. 输出填充后的本期报告模板文档。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def add_bookmark(paragraph, name: str):
    """为段落包裹书签"""
    p = paragraph._p
    bm_start = OxmlElement('w:bookmarkStart')
    bm_start.set(qn('w:id'), name)
    bm_start.set(qn('w:name'), name)
    bm_end = OxmlElement('w:bookmarkEnd')
    bm_end.set(qn('w:id'), name)
    p.insert(0, bm_start)
    p.append(bm_end)


def render_template(base_word_path: Path, mapping_plan_path: Path, output_path: Path):
    plan = json.loads(mapping_plan_path.read_text(encoding="utf-8"))
    tables_plan = {item["table_seq"]: item for item in plan.get("tables", [])}

    doc = Document(str(base_word_path))
    bm_seq = 1

    # 1. 遍历所有表格并根据 plan 回填
    for t_idx, table in enumerate(doc.tables, start=1):
        # 标注表格锚点
        bm_name = f"TPL_TR_{bm_seq:06d}"
        bm_seq += 1
        if table.rows and table.rows[0].cells:
            add_bookmark(table.rows[0].cells[0].paragraphs[0], bm_name)

        if t_idx not in tables_plan:
            continue

        tbl_cfg = tables_plan[t_idx]
        rows_data = tbl_cfg.get("rows", [])
        if not rows_data:
            continue

        target_headers = tbl_cfg.get("target_headers", [])
        template_row = table.rows[1] if len(table.rows) > 1 else table.rows[0]

        # 清理多余数据行（保留表头和必要样板）
        needed_rows = len(rows_data)
        current_rows = len(table.rows) - 1

        for r_idx, data_row in enumerate(rows_data):
            row_target_idx = r_idx + 1
            if row_target_idx < len(table.rows):
                cur_row = table.rows[row_target_idx]
            else:
                # 克隆添加新行
                cur_row = table.add_row()

            # 按表头对齐填充单元格
            for c_idx, cell in enumerate(cur_row.cells):
                if c_idx < len(target_headers):
                    col_name = target_headers[c_idx].strip()
                    val = data_row.get(col_name)
                    if val is None:
                        # 尝试前缀模糊配对
                        for k, v in data_row.items():
                            if k in col_name or col_name in k:
                                val = v
                                break
                    if val is not None:
                        cell.text = str(val)

    # 2. 为关键段落打上锚点
    for p in doc.paragraphs:
        txt = p.text.strip()
        if len(txt) >= 15 and any(kw in txt for kw in ["年度", "关联交易", "转让定价", "营业收入", "利润", "万元", "202"]):
            bm_name = f"TPL_TR_{bm_seq:06d}"
            bm_seq += 1
            add_bookmark(p, bm_name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    print(f"[render] Successfully rendered template to {output_path.name} with {bm_seq - 1} bookmarks.")


def main():
    parser = argparse.ArgumentParser(description="Render TPD Word template using mapping plan")
    parser.add_argument("--base-word", required=True, help="Base Word document")
    parser.add_argument("--plan", required=True, help="Path to mapping_plan.json")
    parser.add_argument("--output", required=True, help="Output Word document path")
    args = parser.parse_args()

    render_template(Path(args.base_word), Path(args.plan), Path(args.output))


if __name__ == "__main__":
    main()
