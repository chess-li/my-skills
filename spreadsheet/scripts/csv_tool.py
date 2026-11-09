#!/usr/bin/env python3
"""Inspect and convert CSV files with the Python standard library."""

import argparse
import csv
import io
import json
import os
import sys
import tempfile
from pathlib import Path


DELIMITERS = {"comma": ",", "tab": "\t", "semicolon": ";", "pipe": "|"}


class ToolError(Exception):
    pass


def read_text(path, encoding):
    try:
        return path.read_bytes().decode(encoding)
    except (OSError, UnicodeError, LookupError) as exc:
        raise ToolError(f"cannot read '{path}' as {encoding}: {exc}") from exc


def select_delimiter(text, selected):
    if selected != "auto":
        return DELIMITERS[selected]
    try:
        return csv.Sniffer().sniff(text[:8192], delimiters="".join(DELIMITERS.values())).delimiter
    except csv.Error:
        return ","


def parse_rows(text, delimiter):
    try:
        return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    except csv.Error as exc:
        raise ToolError(f"invalid CSV input: {exc}") from exc


def check_output(source, output, force):
    if source.resolve() == output.resolve():
        raise ToolError("input and output must be different files")
    if output.exists() and not force:
        raise ToolError(f"output already exists: '{output}'; use --force to replace it")


def write_atomic(output, data):
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=output.parent, suffix=output.suffix)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, output)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def inspect_file(args):
    text = read_text(args.input, args.encoding)
    delimiter = select_delimiter(text, args.delimiter)
    rows = parse_rows(text, delimiter)
    widths = [len(row) for row in rows]
    report = {
        "path": str(args.input),
        "encoding": args.encoding,
        "delimiter": delimiter,
        "rows": len(rows),
        "columns": max(widths, default=0),
        "header": rows[0] if rows else [],
        "consistent_columns": len(set(widths)) <= 1,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def convert_file(args):
    check_output(args.input, args.output, args.force)
    text = read_text(args.input, args.from_encoding)
    source_delimiter = select_delimiter(text, args.from_delimiter)
    rows = parse_rows(text, source_delimiter)
    buffer = io.StringIO(newline="")
    writer = csv.writer(
        buffer,
        delimiter=DELIMITERS[args.to_delimiter],
        lineterminator={"lf": "\n", "crlf": "\r\n"}[args.newline],
    )
    writer.writerows(rows)
    try:
        data = buffer.getvalue().encode(args.to_encoding)
    except (UnicodeError, LookupError) as exc:
        raise ToolError(f"cannot encode output as {args.to_encoding}: {exc}") from exc
    write_atomic(args.output, data)
    report = {
        "output": str(args.output),
        "encoding": args.to_encoding,
        "delimiter": DELIMITERS[args.to_delimiter],
        "rows": len(rows),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="report CSV structure")
    inspect_parser.add_argument("input", type=Path)
    inspect_parser.add_argument("--encoding", default="utf-8-sig")
    inspect_parser.add_argument("--delimiter", choices=("auto", *DELIMITERS), default="auto")
    inspect_parser.set_defaults(func=inspect_file)

    convert_parser = subparsers.add_parser("convert", help="rewrite encoding, delimiter, or newlines")
    convert_parser.add_argument("input", type=Path)
    convert_parser.add_argument("output", type=Path)
    convert_parser.add_argument("--from-encoding", default="utf-8-sig")
    convert_parser.add_argument("--to-encoding", default="utf-8")
    convert_parser.add_argument("--from-delimiter", choices=("auto", *DELIMITERS), default="auto")
    convert_parser.add_argument("--to-delimiter", choices=tuple(DELIMITERS), default="comma")
    convert_parser.add_argument("--newline", choices=("lf", "crlf"), default="crlf")
    convert_parser.add_argument("--force", action="store_true", help="replace an existing output")
    convert_parser.set_defaults(func=convert_file)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ToolError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
