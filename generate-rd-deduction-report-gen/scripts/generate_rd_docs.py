#!/usr/bin/env python3
"""Generate the retained-document package from templates + data.

Fixed pipeline over declarative inputs:

- ``templates/report.json`` lists every output (DOCX and XLSX), its template
  file, the date field for DOCX documents and the sheet→data bindings for
  workbooks. Adding or renaming an output is a manifest edit, not a code edit.
- ``templates/rules.json`` is the executable specification of *shape* rules
  (required fields, topic count, date order, Hxx format/uniqueness/continuity,
  page references, path existence, fixed enumerations); it is interpreted by
  ``scripts/rule_engine.py`` and is swappable per business. Rules needing
  semantic understanding live in ``references/rules.md`` for the model.
- DOCX templates own document structure; the variable contract is derived
  from each template itself (``get_undeclared_template_variables``) instead
  of being hardcoded here.
- XLSX templates own sheet layout; a marker row of ``{{ key }}`` cells per
  data sheet declares where rows are injected, and inline ``{{ name }}``
  cells declare scalar substitution.
- ``data_model`` owns normalization and derived values; this module only
  orchestrates: build context -> render -> verify cross-file consistency.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from copy import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from docx import Document
from docxtpl import DocxTemplate, InlineImage
from jinja2 import Environment, StrictUndefined
from openpyxl import load_workbook
from docx.shared import Mm

try:
    from .data_model import RDProjectData, as_text, ensure_project
    from .report_verification import verify_outputs
    from .rule_engine import load_rules
except ImportError:  # Running as ``python3 scripts/generate_rd_docs.py``.
    from data_model import RDProjectData, as_text, ensure_project  # type: ignore[no-redef]
    from report_verification import verify_outputs  # type: ignore[no-redef]
    from rule_engine import load_rules  # type: ignore[no-redef]


MANIFEST_NAME = "report.json"
TOKEN_RE = re.compile(r"{{\s*([A-Za-z_]\w*)\s*}}")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def load_manifest(template_dir: Path) -> dict:
    manifest_path = template_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"Render manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest.get("documents")
    workbooks = manifest.get("workbooks")
    if not isinstance(documents, list) or not isinstance(workbooks, list):
        raise ValueError(f"{MANIFEST_NAME} must contain 'documents' and 'workbooks' lists")
    for entry in documents:
        for key in ("template", "output", "date_field"):
            if key not in entry:
                raise ValueError(f"Manifest document entry missing '{key}': {entry}")
        if not (template_dir / entry["template"]).exists():
            raise FileNotFoundError(f"DOCX template listed in manifest not found: {entry['template']}")
    for entry in workbooks:
        for key in ("template", "output", "sheets"):
            if key not in entry:
                raise ValueError(f"Manifest workbook entry missing '{key}': {entry}")
        if not isinstance(entry["sheets"], dict):
            raise ValueError(f"Manifest workbook sheets must be a sheet→data-key mapping: {entry}")
        if not (template_dir / entry["template"]).exists():
            raise FileNotFoundError(f"XLSX template listed in manifest not found: {entry['template']}")
    return manifest


# ---------------------------------------------------------------------------
# DOCX rendering
# ---------------------------------------------------------------------------

def _image(template: DocxTemplate, path: Any) -> object:
    if not path:
        return ""
    image_path = Path(as_text(path))
    if not image_path.exists():
        raise ValueError(f"Image does not exist: {image_path}")
    return InlineImage(template, str(image_path), width=Mm(145))


def validate_input(data: dict, rules: Mapping[str, Any] | None = None) -> RDProjectData:
    return RDProjectData.from_dict(data, rules)


def build_context(
    data: dict | RDProjectData,
    template: DocxTemplate,
    document_date: str,
    rules: Mapping[str, Any] | None = None,
) -> dict:
    project = ensure_project(data, rules)
    context = project.to_dict(rules)
    context["supplements"] = [
        item for item in context["supplements"] if item.get("channel", "word") == "word"
    ]
    context.update(project.derived_context())
    context["document_date"] = document_date
    context["result_image"] = _image(template, context.pop("result_image_path", ""))
    for topic in context["topics"]:
        topic["image"] = _image(template, topic.pop("image_path", ""))
    return context


def render_docx_template(template: Path, output: Path, context: dict | None = None, context_builder=None) -> None:
    document = DocxTemplate(str(template))
    if context_builder is not None:
        context = context_builder(document)
    if context is None:
        raise ValueError("A template context or context_builder is required")
    environment = Environment(undefined=StrictUndefined, autoescape=False)
    document.render(context, jinja_env=environment)
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output))


def validate_template_contract(document: DocxTemplate, context: dict, template_name: str) -> None:
    """The template itself is the contract: every variable it declares must
    resolve in the render context, and a template declaring nothing is
    rejected as a likely wrong file."""
    declared = document.get_undeclared_template_variables()
    if not declared:
        raise ValueError(f"DOCX template {template_name} declares no variables; is it the right template file?")
    missing = document.get_undeclared_template_variables(context=context)
    if missing:
        raise ValueError(
            f"DOCX template {template_name} requires variables missing from the render context: {sorted(missing)}"
        )


def build_document(
    template_dir: Path,
    template_name: str,
    output: Path,
    data: dict,
    document_date: str,
    rules: Mapping[str, Any] | None = None,
) -> None:
    template = template_dir / template_name
    if not template.exists():
        raise FileNotFoundError(f"DOCX template not found: {template}")
    document = DocxTemplate(str(template))
    context = build_context(data, document, document_date, rules)
    validate_template_contract(document, context, template_name)
    environment = Environment(undefined=StrictUndefined, autoescape=False)
    document.render(context, jinja_env=environment)
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output))


# ---------------------------------------------------------------------------
# XLSX rendering (template owns layout; marker rows declare data injection)
# ---------------------------------------------------------------------------

def _find_marker_row(sheet) -> tuple[int, dict[int, str]] | None:
    for row in sheet.iter_rows():
        keys: dict[int, str] = {}
        for cell in row:
            if isinstance(cell.value, str):
                match = TOKEN_RE.fullmatch(cell.value.strip())
                if match:
                    keys[cell.column] = match.group(1)
        if keys:
            return row[0].row, keys
    return None


def _fill_sheet(sheet, items: list, data_key: str) -> None:
    found = _find_marker_row(sheet)
    if found is None:
        raise ValueError(f"XLSX sheet '{sheet.title}' (data key '{data_key}') has no marker row of {{{{ key }}}} cells")
    marker_row, keys = found
    styles = {cell.column: copy(cell._style) for cell in sheet[marker_row] if cell.column in keys}
    height = sheet.row_dimensions[marker_row].height

    if not items:
        sheet.delete_rows(marker_row)
    else:
        for offset, item in enumerate(items):
            row_number = marker_row + offset
            if height is not None:
                sheet.row_dimensions[row_number].height = height
            for column, key in keys.items():
                cell = sheet.cell(row=row_number, column=column)
                if offset:
                    cell._style = copy(styles[column])
                raw = item.get(key, "") if isinstance(item, Mapping) else ""
                cell.value = raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) else as_text(raw)

    if sheet.auto_filter.ref:
        match = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", sheet.auto_filter.ref)
        if match:
            sheet.auto_filter.ref = f"{match.group(1)}{match.group(2)}:{match.group(3)}{max(sheet.max_row, int(match.group(4)))}"


def _substitute_scalars(sheet, scalars: Mapping[str, Any]) -> None:
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and "{{" in cell.value:
                def replace(match: re.Match) -> str:
                    key = match.group(1)
                    if key not in scalars:
                        raise ValueError(f"XLSX sheet '{sheet.title}' references unknown scalar variable: {key}")
                    return as_text(scalars[key])

                cell.value = TOKEN_RE.sub(replace, cell.value)


def render_workbook(
    template: Path,
    output: Path,
    data: dict | RDProjectData,
    sheet_bindings: dict[str, str],
    rules: Mapping[str, Any] | None = None,
) -> None:
    if not template.exists():
        raise FileNotFoundError(f"XLSX template not found: {template}")
    context = ensure_project(data, rules).to_dict(rules)
    workbook = load_workbook(template)
    for sheet_name, data_key in sheet_bindings.items():
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"XLSX template {template.name} is missing sheet '{sheet_name}'")
        sheet = workbook[sheet_name]
        items = context.get(data_key) or []
        if not isinstance(items, list):
            raise ValueError(f"Data key '{data_key}' for sheet '{sheet_name}' must be a list")
        _fill_sheet(sheet, items, data_key)
    for sheet in workbook.worksheets:
        _substitute_scalars(sheet, context)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)


# ---------------------------------------------------------------------------
# Verification (cross-file output invariants from rules.json output_invariants)
# ---------------------------------------------------------------------------

def render_outputs(output_dir: Path, render_dir: Path, manifest: dict) -> None:
    office = shutil.which("libreoffice") or shutil.which("soffice")
    if not office:
        raise RuntimeError("--render-dir requires libreoffice or soffice on PATH")
    render_dir.mkdir(parents=True, exist_ok=True)
    names = [entry["output"] for entry in manifest["workbooks"]] + [entry["output"] for entry in manifest["documents"]]
    inputs = [output_dir / name for name in names]
    subprocess.run([office, "--headless", "--convert-to", "pdf", "--outdir", str(render_dir), *map(str, inputs)], check=True, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--template-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--render-dir", type=Path)
    args = parser.parse_args()
    manifest = load_manifest(args.template_dir)
    rules = load_rules(args.template_dir / "rules.json")
    data = validate_input(json.loads(args.input.read_text(encoding="utf-8")), rules)
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_names = [entry["output"] for entry in manifest["workbooks"]] + [entry["output"] for entry in manifest["documents"]]
    with TemporaryDirectory(prefix=".rd-build-", dir=args.output_dir.parent) as staging_name:
        staging = Path(staging_name)
        for entry in manifest["workbooks"]:
            render_workbook(
                args.template_dir / entry["template"],
                staging / entry["output"],
                data,
                entry["sheets"],
                rules,
            )
        for entry in manifest["documents"]:
            if not hasattr(data, entry["date_field"]):
                raise ValueError(f"Manifest date_field '{entry['date_field']}' is not a data model field")
            build_document(
                args.template_dir,
                entry["template"],
                staging / entry["output"],
                data,
                as_text(getattr(data, entry["date_field"])),
                rules,
            )
        verify_outputs(data, staging, manifest, rules)
        if args.render_dir:
            render_outputs(staging, args.render_dir, manifest)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name in output_names:
            shutil.copy2(staging / name, args.output_dir / name)
    print(f"Generated package in {args.output_dir}")


if __name__ == "__main__":
    main()
