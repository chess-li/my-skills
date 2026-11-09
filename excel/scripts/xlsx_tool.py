#!/usr/bin/env python3
"""Create, inspect, export, and edit cells in XLSX workbooks."""

import argparse
import csv
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


def require_openpyxl():
    try:
        openpyxl = importlib.import_module("openpyxl")
        exceptions = importlib.import_module("openpyxl.utils.exceptions")
    except ImportError as exc:
        raise ToolError("missing dependency 'openpyxl'; install with: pip3 install openpyxl") from exc
    return openpyxl, exceptions.InvalidFileException


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


def load_workbook(path, openpyxl, invalid_error, read_only=False):
    try:
        return openpyxl.load_workbook(path, read_only=read_only, data_only=False)
    except (invalid_error, ValueError, zipfile.BadZipFile, OSError) as exc:
        raise ToolError(f"cannot open XLSX '{path}': {exc}") from exc


def get_sheet(workbook, title):
    try:
        return workbook[title]
    except KeyError as exc:
        raise ToolError(f"sheet not found: '{title}'") from exc


def read_csv(path, encoding):
    try:
        text = path.read_bytes().decode(encoding)
    except (OSError, UnicodeError, LookupError) as exc:
        raise ToolError(f"cannot read CSV '{path}': {exc}") from exc
    try:
        return list(csv.reader(text.splitlines(keepends=True), strict=True))
    except csv.Error as exc:
        raise ToolError(f"invalid CSV '{path}': {exc}") from exc


def create_file(args):
    check_output(args.output, args.force, args.from_csv)
    openpyxl, _ = require_openpyxl()
    rows = read_csv(args.from_csv, args.encoding)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = args.sheet
    for row in rows:
        sheet.append(row)
    with atomic_output(args.output) as temporary:
        workbook.save(temporary)
    workbook.close()
    print(json.dumps({"output": str(args.output), "rows": len(rows)}, ensure_ascii=False))


def inspect_file(args):
    openpyxl, invalid_error = require_openpyxl()
    workbook = load_workbook(args.input, openpyxl, invalid_error, read_only=True)
    try:
        sheets = [
            {"title": sheet.title, "rows": sheet.max_row or 0, "columns": sheet.max_column or 0}
            for sheet in workbook.worksheets
        ]
    finally:
        workbook.close()
    print(json.dumps({"path": str(args.input), "sheets": sheets}, ensure_ascii=False, indent=2))


def export_file(args):
    check_output(args.output, args.force, args.input)
    openpyxl, invalid_error = require_openpyxl()
    workbook = load_workbook(args.input, openpyxl, invalid_error, read_only=True)
    try:
        sheet = get_sheet(workbook, args.sheet)
        with atomic_output(args.output) as temporary:
            with temporary.open("w", encoding=args.encoding, newline="") as stream:
                writer = csv.writer(stream, lineterminator="\r\n")
                for row in sheet.iter_rows(values_only=True):
                    writer.writerow(["" if value is None else value for value in row])
    finally:
        workbook.close()
    print(json.dumps({"output": str(args.output), "sheet": args.sheet}, ensure_ascii=False))


def set_file(args):
    check_output(args.output, args.force, args.input)
    openpyxl, invalid_error = require_openpyxl()
    workbook = load_workbook(args.input, openpyxl, invalid_error)
    try:
        sheet = get_sheet(workbook, args.sheet)
        sheet[args.cell] = args.value
        with atomic_output(args.output) as temporary:
            workbook.save(temporary)
    finally:
        workbook.close()
    print(
        json.dumps(
            {"output": str(args.output), "sheet": args.sheet, "cell": args.cell},
            ensure_ascii=False,
        )
    )


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="create an XLSX from CSV text")
    create_parser.add_argument("output", type=Path)
    create_parser.add_argument("--from-csv", type=Path, required=True)
    create_parser.add_argument("--encoding", default="utf-8-sig")
    create_parser.add_argument("--sheet", default="Sheet1")
    create_parser.add_argument("--force", action="store_true")
    create_parser.set_defaults(func=create_file)

    inspect_parser = subparsers.add_parser("inspect", help="report workbook sheets")
    inspect_parser.add_argument("input", type=Path)
    inspect_parser.set_defaults(func=inspect_file)

    export_parser = subparsers.add_parser("export", help="export one sheet to CSV")
    export_parser.add_argument("input", type=Path)
    export_parser.add_argument("output", type=Path)
    export_parser.add_argument("--sheet", required=True)
    export_parser.add_argument("--encoding", default="utf-8")
    export_parser.add_argument("--force", action="store_true")
    export_parser.set_defaults(func=export_file)

    set_parser = subparsers.add_parser("set", help="set one cell to a literal string")
    set_parser.add_argument("input", type=Path)
    set_parser.add_argument("output", type=Path)
    set_parser.add_argument("--sheet", required=True)
    set_parser.add_argument("--cell", required=True)
    set_parser.add_argument("--value", required=True)
    set_parser.add_argument("--force", action="store_true")
    set_parser.set_defaults(func=set_file)
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
