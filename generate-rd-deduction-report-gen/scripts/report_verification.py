from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from docx import Document
from openpyxl import load_workbook

try:
    from .data_model import RDProjectData, as_text, ensure_project
    from .rule_engine import load_rules, placeholder_re
except ImportError:  # Running as a flat module inside scripts/.
    from data_model import RDProjectData, as_text, ensure_project  # type: ignore[no-redef]
    from rule_engine import load_rules, placeholder_re  # type: ignore[no-redef]


def paragraph_texts(document: Document) -> list[str]:
    values = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                values.extend(paragraph.text for paragraph in cell.paragraphs)
    for section in document.sections:
        values.extend(paragraph.text for paragraph in section.header.paragraphs)
        values.extend(paragraph.text for paragraph in section.footer.paragraphs)
    return values


def docx_placeholders(path: Path, pattern: re.Pattern) -> set[str]:
    return set(pattern.findall("\n".join(paragraph_texts(Document(path)))))


def docx_placeholder_order(path: Path, pattern: re.Pattern) -> list[str]:
    order = []
    for text in paragraph_texts(Document(path)):
        order.extend(pattern.findall(text))
    return order


def workbook_placeholders(path: Path, pattern: re.Pattern) -> set[str]:
    workbook = load_workbook(path, data_only=False)
    try:
        values = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        continue
                    values.append(as_text(cell.value))
        return set(pattern.findall("\n".join(values)))
    finally:
        workbook.close()


def verify_outputs(
    data: dict | RDProjectData,
    output_dir: Path,
    manifest: dict,
    rules: Mapping[str, Any] | None = None,
) -> None:
    rules = rules if rules is not None else load_rules()
    pattern = placeholder_re(rules)
    data = ensure_project(data, rules).to_dict(rules)
    word_supplements = [
        item for item in data.get("supplements", []) if item.get("channel", "word") == "word"
    ]
    expected = {as_text(item.get("id")) for item in word_supplements}
    docs = [output_dir / entry["output"] for entry in manifest["documents"]]
    actual = set().union(*(docx_placeholders(path, pattern) for path in docs))
    workbook_sets = {
        entry["output"]: workbook_placeholders(output_dir / entry["output"], pattern)
        for entry in manifest["workbooks"]
    }
    mismatched = {name: ids for name, ids in workbook_sets.items() if ids != expected}
    if actual != expected or mismatched:
        raise ValueError(
            f"Hxx mismatch: expected={sorted(expected)}, docs={sorted(actual)}, workbooks={ {k: sorted(v) for k, v in mismatched.items()} }"
        )
    first_order = []
    for path in docs:
        for identifier in docx_placeholder_order(path, pattern):
            if identifier not in first_order:
                first_order.append(identifier)
    expected_order = [as_text(item.get("id")) for item in word_supplements]
    if first_order != expected_order:
        raise ValueError(f"Hxx first appearance order does not match supplements: docs={first_order}, supplements={expected_order}")
