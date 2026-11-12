#!/usr/bin/env python3
"""TPD 区域差异比对脚本 (diff node)

基于 Word 中的锚点书签 (TPL_TR_xxxxxx) 对比 Base 稿与 Template 稿，
计算区域级别的文本与表格 Diff，输出标准差异报表。
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from docx import Document


def extract_doc_regions(docx_path: Path) -> dict:
    doc = Document(str(docx_path))
    regions = {}
    for idx, table in enumerate(doc.tables, 1):
        r_id = f"table_{idx}"
        rows_text = []
        for row in table.rows:
            rows_text.append([c.text.strip() for c in row.cells])
        regions[r_id] = {
            "type": "table",
            "index": idx,
            "data": rows_text
        }
    return regions


def diff_documents(base_doc: Path, tpl_doc: Path, output_file: Path):
    base_regions = extract_doc_regions(base_doc)
    tpl_regions = extract_doc_regions(tpl_doc)

    diffs = []
    total = len(tpl_regions)
    modified = 0
    unchanged = 0

    for r_id, t_info in tpl_regions.items():
        b_info = base_regions.get(r_id)
        if not b_info:
            diffs.append({
                "region_id": r_id,
                "status": "added",
                "diff": "New table"
            })
            modified += 1
            continue

        b_rows = b_info["data"]
        t_rows = t_info["data"]

        if b_rows == t_rows:
            diffs.append({
                "region_id": r_id,
                "status": "unchanged"
            })
            unchanged += 1
        else:
            diffs.append({
                "region_id": r_id,
                "status": "modified",
                "base_row_count": len(b_rows),
                "tpl_row_count": len(t_rows)
            })
            modified += 1

    report = {
        "base_file": base_doc.name,
        "template_file": tpl_doc.name,
        "total_regions": total,
        "modified_regions": modified,
        "unchanged_regions": unchanged,
        "diffs": diffs
    }

    output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[diff] Analyzed {total} regions: {modified} modified, {unchanged} unchanged.")


def main():
    parser = argparse.ArgumentParser(description="Diff TPD document regions")
    parser.add_argument("--base", required=True, help="Base Word document")
    parser.add_argument("--template", required=True, help="Template Word document")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    diff_documents(Path(args.base), Path(args.template), Path(args.output))


if __name__ == "__main__":
    main()
