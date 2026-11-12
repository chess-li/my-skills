#!/usr/bin/env python3
"""TPD 材料物理解析脚本 (extract node)

无语义格式解码：
1. 对 Word (.docx) 解码为表格列表、段落列表与书签结构 (word_layers.json)；
2. 对 Excel (.xlsx/.xlsm) 解码为全部工作表的行列纯数据矩阵 (wp_tables.json)。
输出统一供后续规则匹配脚本 evaluate_rules.py 消费，杜绝任何平台端的格式与表名硬编码。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


# 修复 openpyxl 解析 tabRatio 浮点数字符串的已知 bug
try:
    import openpyxl.descriptors.base
    _orig_convert = openpyxl.descriptors.base._convert
    def _safe_convert(expected_type, value):
        if expected_type is int and isinstance(value, str) and '.' in value:
            try:
                return int(float(value))
            except Exception:
                pass
        return _orig_convert(expected_type, value)
    openpyxl.descriptors.base._convert = _safe_convert

    import openpyxl.workbook.defined_name
    _orig_dn_init = openpyxl.workbook.defined_name.DefinedName.__init__
    def _safe_dn_init(self, *args, **kwargs):
        kwargs.pop('isReadOnly', None)
        _orig_dn_init(self, *args, **kwargs)
    openpyxl.workbook.defined_name.DefinedName.__init__ = _safe_dn_init
except Exception:
    pass


def extract_word_layers(docx_path: Path, output_dir: Path) -> dict:
    """提取 Word 中的段落、表格结构与已存在书签"""
    nodes = []
    bookmarks = []
    tables = []

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def get_text(element: ET.Element) -> str:
        parts = []
        for child in element.iter():
            if local(child.tag) == "t" and child.text:
                parts.append(child.text)
        return "".join(parts).strip()

    with zipfile.ZipFile(docx_path) as archive:
        if "word/document.xml" not in archive.namelist():
            raise ValueError(f"Invalid DOCX file, missing word/document.xml: {docx_path}")
        root = ET.fromstring(archive.read("word/document.xml"))

    body = root.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body")
    if body is None:
        body = root

    table_seq = 0
    paragraph_seq = 0

    for child in body:
        tag = local(child.tag)
        if tag == "p":
            paragraph_seq += 1
            txt = get_text(child)
            for bm in child.iter():
                if local(bm.tag) == "bookmarkStart":
                    bname = bm.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name")
                    if bname:
                        bookmarks.append(bname)
            nodes.append({
                "kind": "paragraph",
                "seq": paragraph_seq,
                "text": txt
            })
        elif tag == "tbl":
            table_seq += 1
            tbl_rows = []
            for row in child.findall("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tr"):
                row_cells = []
                for tc in row.findall("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc"):
                    row_cells.append(get_text(tc))
                tbl_rows.append(row_cells)

            headers = tbl_rows[0] if tbl_rows else []
            table_meta = {
                "kind": "table",
                "seq": table_seq,
                "total_rows": len(tbl_rows),
                "total_cols": len(headers),
                "headers": headers,
                "rows": tbl_rows
            }
            tables.append(table_meta)
            nodes.append({
                "kind": "table_ref",
                "seq": table_seq,
                "headers": headers
            })

    result = {
        "file_name": docx_path.name,
        "bookmarks": bookmarks,
        "tables_count": len(tables),
        "tables": tables,
        "paragraphs_count": len(nodes) - len(tables)
    }

    out_file = output_dir / "word_layers.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def extract_excel_layers(excel_path: Path, output_dir: Path) -> dict:
    """提取 Excel 中所有 Sheet 的纯数据矩阵 (纯文本/数字/缓存值)"""
    import openpyxl

    wb = openpyxl.load_workbook(str(excel_path), data_only=True)
    sheets: dict[str, list[list[str]]] = {}
    sheet_summaries = []

    for name in wb.sheetnames:
        ws = wb[name]
        clean_name = name.strip()
        rows: list[list[str]] = []
        for row in ws.iter_rows(values_only=True):
            vals = ["" if v is None else str(v).strip() for v in row]
            if any(vals):
                rows.append(vals)
        sheets[clean_name] = rows
        sheet_summaries.append({
            "name": clean_name,
            "rows_count": len(rows),
            "headers": rows[0] if rows else []
        })
    wb.close()

    result = {
        "file_name": excel_path.name,
        "sheets_count": len(sheets),
        "sheet_summaries": sheet_summaries,
        "sheets": sheets
    }

    out_file = output_dir / "wp_tables.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="Extract TPD materials into structured JSON")
    parser.add_argument("--word", required=True, help="Path to base Word (.docx)")
    parser.add_argument("--excel", required=True, help="Path to workingpaper Excel (.xlsx)")
    parser.add_argument("--output-dir", required=True, help="Directory to save extracted JSON layers")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    word_path = Path(args.word)
    excel_path = Path(args.excel)

    if not word_path.exists():
        print(f"Error: Word file not found: {word_path}", file=sys.stderr)
        sys.exit(1)
    if not excel_path.exists():
        print(f"Error: Excel file not found: {excel_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[extract] Decoding Word: {word_path.name}", file=sys.stderr)
    w_meta = extract_word_layers(word_path, out_dir)
    print(f"[extract] Word extracted: {w_meta['tables_count']} tables, {w_meta['paragraphs_count']} paragraphs", file=sys.stderr)

    print(f"[extract] Decoding Excel: {excel_path.name}", file=sys.stderr)
    x_meta = extract_excel_layers(excel_path, out_dir)
    print(f"[extract] Excel extracted: {x_meta['sheets_count']} sheets", file=sys.stderr)

    summary_file = out_dir / "extract_manifest.json"
    summary_file.write_text(json.dumps({
        "status": "success",
        "word_tables": w_meta["tables_count"],
        "excel_sheets": x_meta["sheets_count"],
        "layers": ["word_layers.json", "wp_tables.json"]
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[extract] Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
