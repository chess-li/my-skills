#!/usr/bin/env python3
"""Create, inspect, extract, and replace text in DOCX documents."""

import argparse
import importlib
import json
import os
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path


class ToolError(Exception):
    pass


def require_docx():
    # This directory also contains the local ``docx.py`` command wrapper.
    # Remove the script directory while resolving the third-party package so
    # ``python3 docx_tool.py ...`` cannot mistake that wrapper for python-docx.
    script_dir = Path(__file__).resolve().parent
    original_path = list(sys.path)
    try:
        sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != script_dir]
        docx = importlib.import_module("docx")
        exceptions = importlib.import_module("docx.opc.exceptions")
    except ImportError as exc:
        raise ToolError("missing dependency 'docx'; install with: pip3 install python-docx") from exc
    finally:
        sys.path[:] = original_path
    return docx, exceptions.PackageNotFoundError


def check_output(output, force, source=None):
    if source is not None and source.resolve() == output.resolve():
        raise ToolError("input and output must be different files")
    if output.exists() and not force:
        raise ToolError(f"output already exists: '{output}'; use --force to replace it")


@contextmanager
def atomic_output(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=output.parent, suffix=output.suffix)
    os.close(descriptor)
    try:
        yield Path(temporary)
        os.replace(temporary, output)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def load_document(path, docx, package_error):
    try:
        return docx.Document(str(path))
    except (package_error, ValueError, zipfile.BadZipFile, OSError) as exc:
        raise ToolError(f"cannot open DOCX '{path}': {exc}") from exc


def iter_blocks(document):
    if hasattr(document, "iter_inner_content"):
        yield from document.iter_inner_content()
    else:
        yield from document.paragraphs
        yield from document.tables


def table_paragraphs(table):
    for row in table.rows:
        for cell in row.cells:
            yield from cell.paragraphs
            for nested in cell.tables:
                yield from table_paragraphs(nested)


def document_paragraphs(document):
    for block in iter_blocks(document):
        if hasattr(block, "rows"):
            yield from table_paragraphs(block)
        else:
            yield block


def replace_in_paragraph(paragraph, old, new):
    replacements = 0
    search_from = 0
    while True:
        runs = paragraph.runs
        full_text = "".join(run.text for run in runs)
        start = full_text.find(old, search_from)
        if start < 0:
            return replacements
        end = start + len(old)

        def locate(position):
            offset = 0
            for index, run in enumerate(runs):
                next_offset = offset + len(run.text)
                if position < next_offset:
                    return index, position - offset
                offset = next_offset
            raise ToolError("could not map matched text to document runs")

        start_index, start_offset = locate(start)
        end_index, end_last_offset = locate(end - 1)
        end_offset = end_last_offset + 1
        if start_index == end_index:
            text = runs[start_index].text
            runs[start_index].text = text[:start_offset] + new + text[end_offset:]
        else:
            start_run = runs[start_index]
            end_run = runs[end_index]
            prefix = start_run.text[:start_offset]
            suffix = end_run.text[end_offset:]
            start_run.text = prefix + new
            for index in range(start_index + 1, end_index):
                runs[index].text = ""
            end_run.text = suffix
        replacements += 1
        search_from = start + len(new)


def create_file(args):
    check_output(args.output, args.force, args.from_text)
    docx, _ = require_docx()
    document = docx.Document()
    # python-docx's stock template omits the required w:percent attribute on
    # w:zoom.  Add the default explicitly so the generated package passes the
    # bundled OOXML schema validator without a follow-up repair pass.
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    zoom = document.settings.element.find(qn("w:zoom"))
    if zoom is None:
        zoom = OxmlElement("w:zoom")
        document.settings.element.append(zoom)
    zoom.set(qn("w:percent"), "100")
    if args.title is not None:
        document.core_properties.title = args.title
        document.add_heading(args.title, level=1)
    if args.from_text is not None:
        try:
            text = args.from_text.read_text(encoding=args.encoding)
        except (OSError, UnicodeError, LookupError) as exc:
            raise ToolError(f"cannot read source text '{args.from_text}': {exc}") from exc
        for line in text.splitlines():
            document.add_paragraph(line)
    with atomic_output(args.output) as temporary:
        document.save(temporary)
    print(json.dumps({"output": str(args.output), "paragraphs": len(document.paragraphs)}, ensure_ascii=False))


def inspect_file(args):
    docx, package_error = require_docx()
    document = load_document(args.input, docx, package_error)
    report = {
        "path": str(args.input),
        "title": document.core_properties.title,
        "paragraphs": len(document.paragraphs),
        "tables": len(document.tables),
        "sections": len(document.sections),
        "inline_shapes": len(document.inline_shapes),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def extract_text(document):
    lines = []
    for block in iter_blocks(document):
        if hasattr(block, "rows"):
            for row in block.rows:
                lines.append("\t".join(cell.text.replace("\n", " ") for cell in row.cells))
        else:
            lines.append(block.text)
    return "\n".join(lines) + ("\n" if lines else "")


def extract_file(args):
    if args.output is not None:
        check_output(args.output, args.force, args.input)
    docx, package_error = require_docx()
    document = load_document(args.input, docx, package_error)
    text = extract_text(document)
    if args.output is None:
        sys.stdout.write(text)
        return
    with atomic_output(args.output) as temporary:
        temporary.write_text(text, encoding=args.encoding)
    print(json.dumps({"output": str(args.output), "characters": len(text)}, ensure_ascii=False))


def replace_file(args):
    if not args.find:
        raise ToolError("--find must not be empty")
    check_output(args.output, args.force, args.input)
    docx, package_error = require_docx()
    document = load_document(args.input, docx, package_error)
    replacements = 0
    for paragraph in document_paragraphs(document):
        replacements += replace_in_paragraph(paragraph, args.find, args.replace)
    with atomic_output(args.output) as temporary:
        document.save(temporary)
    print(json.dumps({"output": str(args.output), "replacements": replacements}, ensure_ascii=False))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="create a DOCX from optional plain text")
    create_parser.add_argument("output", type=Path)
    create_parser.add_argument("--from-text", type=Path)
    create_parser.add_argument("--encoding", default="utf-8")
    create_parser.add_argument("--title")
    create_parser.add_argument("--force", action="store_true")
    create_parser.set_defaults(func=create_file)

    inspect_parser = subparsers.add_parser("inspect", help="report document structure")
    inspect_parser.add_argument("input", type=Path)
    inspect_parser.set_defaults(func=inspect_file)

    extract_parser = subparsers.add_parser("extract", help="extract body paragraphs and tables")
    extract_parser.add_argument("input", type=Path)
    extract_parser.add_argument("--output", type=Path)
    extract_parser.add_argument("--encoding", default="utf-8")
    extract_parser.add_argument("--force", action="store_true")
    extract_parser.set_defaults(func=extract_file)

    replace_parser = subparsers.add_parser("replace", help="replace text in body paragraphs and tables")
    replace_parser.add_argument("input", type=Path)
    replace_parser.add_argument("output", type=Path)
    replace_parser.add_argument("--find", required=True)
    replace_parser.add_argument("--replace", required=True)
    replace_parser.add_argument("--force", action="store_true")
    replace_parser.set_defaults(func=replace_file)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ToolError, OSError, ValueError, LookupError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
