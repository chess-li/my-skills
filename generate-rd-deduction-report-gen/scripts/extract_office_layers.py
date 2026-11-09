#!/usr/bin/env python3
"""Extract text/tables from docx/xlsx/pdf/txt without semantic interpretation.

frext node: format decode only. Semantic reading belongs to fread (model).

Output layout::

    <output-dir>/<source-stem>/layers.json
    <output-dir>/<source-stem>/text.txt
    <output-dir>/<source-stem>/tables.json   # xlsx sheets as list-of-rows

layers.json: source, kind, text_path, text_chars, tables_path, sheet_names, errors[].
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SUPPORTED = {".docx", ".xls", ".xlsx", ".xlsm", ".pdf", ".txt", ".md", ".csv"}


def _write_text(target: Path, text: str) -> tuple[str | None, int]:
    if not text.strip():
        return None, 0
    path = target / "text.txt"
    path.write_text(text, encoding="utf-8")
    return path.name, len(text)


def extract_docx(source: Path, target: Path) -> dict:
    from docx import Document

    doc = Document(str(source))
    parts: list[str] = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            parts.append(t)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append("\t".join(cells))
    text = "\n".join(parts)
    text_path, n = _write_text(target, text)
    return {
        "kind": "docx",
        "text_path": text_path,
        "text_chars": n,
        "tables_path": None,
        "sheet_names": [],
        "errors": [] if n else ["docx produced empty text"],
    }


def extract_xlsx(source: Path, target: Path) -> dict:
    from openpyxl import load_workbook

    wb = load_workbook(str(source), data_only=True, read_only=True)
    sheets: dict[str, list[list[str]]] = {}
    text_parts: list[str] = []
    for name in wb.sheetnames:
        ws = wb[name]
        rows: list[list[str]] = []
        for row in ws.iter_rows(values_only=True):
            vals = ["" if v is None else str(v).strip() for v in row]
            if any(vals):
                rows.append(vals)
                text_parts.append(f"[{name}]\t" + "\t".join(vals))
        sheets[name] = rows
    wb.close()
    tables_path = target / "tables.json"
    tables_path.write_text(json.dumps(sheets, ensure_ascii=False, indent=2), encoding="utf-8")
    text_path, n = _write_text(target, "\n".join(text_parts))
    return {
        "kind": "xlsx",
        "text_path": text_path,
        "text_chars": n,
        "tables_path": tables_path.name,
        "sheet_names": list(sheets.keys()),
        "errors": [] if sheets else ["xlsx has no sheets"],
    }


def extract_xls(source: Path, target: Path) -> dict:
    import xlrd

    workbook = xlrd.open_workbook(str(source), on_demand=True)
    sheets: dict[str, list[list[str]]] = {}
    text_parts: list[str] = []
    try:
        for name in workbook.sheet_names():
            sheet = workbook.sheet_by_name(name)
            rows: list[list[str]] = []
            for row_index in range(sheet.nrows):
                values: list[str] = []
                for column_index in range(sheet.ncols):
                    cell_type = sheet.cell_type(row_index, column_index)
                    value = sheet.cell_value(row_index, column_index)
                    if value in (None, ""):
                        values.append("")
                    elif cell_type == xlrd.XL_CELL_DATE:
                        values.append(
                            xlrd.xldate_as_datetime(value, workbook.datemode).isoformat(sep=" ")
                        )
                    elif (
                        cell_type == xlrd.XL_CELL_NUMBER
                        and isinstance(value, float)
                        and value.is_integer()
                    ):
                        values.append(str(int(value)))
                    else:
                        values.append(str(value).strip())
                while values and not values[-1]:
                    values.pop()
                if any(values):
                    rows.append(values)
                    text_parts.append(f"[{name}]\t" + "\t".join(values))
            sheets[name] = rows
    finally:
        workbook.release_resources()

    tables_path = target / "tables.json"
    tables_path.write_text(json.dumps(sheets, ensure_ascii=False, indent=2), encoding="utf-8")
    text_path, n = _write_text(target, "\n".join(text_parts))
    return {
        "kind": "xls",
        "text_path": text_path,
        "text_chars": n,
        "tables_path": tables_path.name,
        "sheet_names": list(sheets.keys()),
        "errors": [] if sheets else ["xls has no sheets"],
    }


def extract_pdf(source: Path, target: Path) -> dict:
    errors: list[str] = []
    text = ""
    try:
        from pdfminer.high_level import extract_text  # type: ignore

        text = extract_text(str(source)) or ""
    except ImportError:
        errors.append("pdfminer.six not installed")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pdf extract failed: {exc}")
    text_path, n = _write_text(target, text)
    if not n and not errors:
        errors.append("pdf produced empty text (may be scan-only)")
    return {
        "kind": "pdf",
        "text_path": text_path,
        "text_chars": n,
        "tables_path": None,
        "sheet_names": [],
        "errors": errors,
    }


def extract_txt(source: Path, target: Path) -> dict:
    errors: list[str] = []
    raw = source.read_bytes()
    text = ""
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
        errors.append("decoded with replacement characters")
    text_path, n = _write_text(target, text)
    return {
        "kind": "txt",
        "text_path": text_path,
        "text_chars": n,
        "tables_path": None,
        "sheet_names": [],
        "errors": errors,
    }


def extract_office_layers(source: Path, output_root: Path) -> dict:
    if not source.is_file():
        raise FileNotFoundError(f"input not found: {source}")
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"unsupported type {suffix}; expected one of {sorted(SUPPORTED)}")

    target = output_root / source.stem
    target.mkdir(parents=True, exist_ok=True)

    if suffix == ".docx":
        body = extract_docx(source, target)
    elif suffix == ".xls":
        body = extract_xls(source, target)
    elif suffix in (".xlsx", ".xlsm"):
        body = extract_xlsx(source, target)
    elif suffix == ".pdf":
        body = extract_pdf(source, target)
    else:
        body = extract_txt(source, target)

    result = {"source": source.name, **body}
    (target / "layers.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = extract_office_layers(args.input, args.output_dir)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
