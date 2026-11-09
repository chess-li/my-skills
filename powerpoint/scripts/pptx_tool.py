#!/usr/bin/env python3
"""Create, inspect, extract, and replace text in PPTX presentations."""

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


def require_pptx():
    try:
        pptx = importlib.import_module("pptx")
        exceptions = importlib.import_module("pptx.exc")
    except ImportError as exc:
        raise ToolError("missing dependency 'pptx'; install with: pip3 install python-pptx") from exc
    return pptx, exceptions.PackageNotFoundError


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


def load_presentation(path, pptx, package_error):
    try:
        return pptx.Presentation(str(path))
    except (package_error, ValueError, zipfile.BadZipFile, OSError) as exc:
        raise ToolError(f"cannot open PPTX '{path}': {exc}") from exc


def load_deck_spec(path, encoding):
    try:
        data = json.loads(path.read_text(encoding=encoding))
    except (OSError, UnicodeError, LookupError, json.JSONDecodeError) as exc:
        raise ToolError(f"cannot read deck JSON '{path}': {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("slides"), list):
        raise ToolError("deck JSON must be an object with a 'slides' array")
    for index, slide in enumerate(data["slides"], start=1):
        if not isinstance(slide, dict) or not isinstance(slide.get("title"), str):
            raise ToolError(f"slide {index} must have a string 'title'")
        bullets = slide.get("bullets")
        if not isinstance(bullets, list) or not all(isinstance(item, str) for item in bullets):
            raise ToolError(f"slide {index} must have a 'bullets' array of strings")
    return data


def iter_text_frames(slide):
    for shape in slide.shapes:
        if getattr(shape, "has_text_frame", False):
            yield shape.text_frame
        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                for cell in row.cells:
                    yield cell.text_frame


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
            raise ToolError("could not map matched text to presentation runs")

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
    check_output(args.output, args.force, args.from_json)
    pptx, _ = require_pptx()
    deck = load_deck_spec(args.from_json, args.encoding)
    presentation = pptx.Presentation()
    for slide_spec in deck["slides"]:
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = slide_spec["title"]
        content = slide.placeholders[1].text_frame
        content.clear()
        for index, bullet in enumerate(slide_spec["bullets"]):
            paragraph = content.paragraphs[0] if index == 0 else content.add_paragraph()
            paragraph.text = bullet
    with atomic_output(args.output) as temporary:
        presentation.save(temporary)
    print(json.dumps({"output": str(args.output), "slides": len(deck["slides"])}, ensure_ascii=False))


def inspect_file(args):
    pptx, package_error = require_pptx()
    presentation = load_presentation(args.input, pptx, package_error)
    titles = []
    for slide in presentation.slides:
        title = slide.shapes.title
        titles.append(title.text if title is not None else None)
    report = {"path": str(args.input), "slides": len(presentation.slides), "titles": titles}
    print(json.dumps(report, ensure_ascii=False, indent=2))


def extract_file(args):
    pptx, package_error = require_pptx()
    presentation = load_presentation(args.input, pptx, package_error)
    sections = []
    for number, slide in enumerate(presentation.slides, start=1):
        lines = [f"--- Slide {number} ---"]
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                lines.extend(shape.text.splitlines())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    lines.append("\t".join(cell.text.replace("\n", " ") for cell in row.cells))
        sections.append("\n".join(lines))
    sys.stdout.write("\n\n".join(sections) + ("\n" if sections else ""))


def replace_file(args):
    if not args.find:
        raise ToolError("--find must not be empty")
    check_output(args.output, args.force, args.input)
    pptx, package_error = require_pptx()
    presentation = load_presentation(args.input, pptx, package_error)
    replacements = 0
    for slide in presentation.slides:
        for text_frame in iter_text_frames(slide):
            for paragraph in text_frame.paragraphs:
                replacements += replace_in_paragraph(paragraph, args.find, args.replace)
    with atomic_output(args.output) as temporary:
        presentation.save(temporary)
    print(json.dumps({"output": str(args.output), "replacements": replacements}, ensure_ascii=False))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="create a PPTX from deck JSON")
    create_parser.add_argument("output", type=Path)
    create_parser.add_argument("--from-json", type=Path, required=True)
    create_parser.add_argument("--encoding", default="utf-8")
    create_parser.add_argument("--force", action="store_true")
    create_parser.set_defaults(func=create_file)

    inspect_parser = subparsers.add_parser("inspect", help="report slide count and titles")
    inspect_parser.add_argument("input", type=Path)
    inspect_parser.set_defaults(func=inspect_file)

    extract_parser = subparsers.add_parser("extract", help="extract slide and table text")
    extract_parser.add_argument("input", type=Path)
    extract_parser.set_defaults(func=extract_file)

    replace_parser = subparsers.add_parser("replace", help="replace text in slide text frames and tables")
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
