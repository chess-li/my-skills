#!/usr/bin/env python3
"""Inspect and convert plain-text files without third-party dependencies."""

import argparse
import codecs
import json
import os
import re
import sys
import tempfile
from pathlib import Path


class ToolError(Exception):
    pass


def detect_encoding(data):
    bom_types = (
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF8, "utf-8-sig"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
    )
    for bom, encoding in bom_types:
        if data.startswith(bom):
            return encoding
    return "utf-8"


def read_source(path, encoding=None):
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ToolError(f"cannot read '{path}': {exc}") from exc
    selected = encoding or detect_encoding(data)
    try:
        return data.decode(selected), selected
    except (UnicodeError, LookupError) as exc:
        raise ToolError(
            f"cannot decode '{path}' as {selected}: {exc}; specify the source encoding"
        ) from exc


def newline_name(text):
    styles = {"LF": 0, "CRLF": 0, "CR": 0}
    for match in re.finditer(r"\r\n|\r|\n", text):
        styles[{ "\n": "LF", "\r": "CR", "\r\n": "CRLF" }[match.group(0)]] += 1
    present = [name for name, count in styles.items() if count]
    if not present:
        return "none"
    if len(present) == 1:
        return present[0]
    return "mixed"


def convert_newlines(text, style):
    if style == "preserve":
        return text
    normalized = re.sub(r"\r\n|\r|\n", "\n", text)
    replacement = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}[style]
    return normalized.replace("\n", replacement)


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
    text, encoding = read_source(args.input, args.encoding)
    report = {
        "path": str(args.input),
        "encoding": encoding,
        "bytes": args.input.stat().st_size,
        "lines": len(text.splitlines()),
        "newlines": newline_name(text),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def convert_file(args):
    check_output(args.input, args.output, args.force)
    text, _ = read_source(args.input, args.from_encoding)
    converted = convert_newlines(text, args.newline)
    try:
        data = converted.encode(args.to_encoding)
    except (UnicodeError, LookupError) as exc:
        raise ToolError(f"cannot encode output as {args.to_encoding}: {exc}") from exc
    write_atomic(args.output, data)
    report = {
        "output": str(args.output),
        "encoding": args.to_encoding,
        "newlines": newline_name(converted),
        "characters": len(converted),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="report encoding and line structure")
    inspect_parser.add_argument("input", type=Path)
    inspect_parser.add_argument("--encoding", help="source encoding; default detects BOM or UTF-8")
    inspect_parser.set_defaults(func=inspect_file)

    convert_parser = subparsers.add_parser("convert", help="convert encoding or newline style")
    convert_parser.add_argument("input", type=Path)
    convert_parser.add_argument("output", type=Path)
    convert_parser.add_argument("--from-encoding", help="source encoding; default detects BOM or UTF-8")
    convert_parser.add_argument("--to-encoding", default="utf-8")
    convert_parser.add_argument(
        "--newline", choices=("preserve", "lf", "crlf", "cr"), default="preserve"
    )
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
