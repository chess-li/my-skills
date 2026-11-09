#!/usr/bin/env python3
"""Local orchestration for DOCX build, validation, lint, conversion, and QA.

The wrapper keeps the historical command shape while routing every operation
to the provider-independent assets in this skill.  It accepts only local file
paths and local executables.

Commands::

    python3 docx.py build create.js output.docx
    python3 docx.py validate output.docx
    python3 docx.py lint create.js
    python3 docx.py md2docx report.md report.docx --bibliography refs.bib
    python3 docx.py check-docx /path/to/project
    python3 docx.py render output.docx qa-directory
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def _run(script: Path, args: list[str]) -> int:
    return subprocess.run([sys.executable, str(script), *args], check=False).returncode


def _run_lint(scripts: list[Path]) -> int:
    if not scripts:
        print("docx.py lint: provide at least one JavaScript file", file=sys.stderr)
        return 2
    missing = [path for path in scripts if not path.is_file()]
    if missing:
        print(f"docx.py lint: file not found: {missing[0]}", file=sys.stderr)
        return 2
    return _run(SCRIPT_DIR / "lint_docx_js.py", [str(path) for path in scripts])


def _check_docx(start: Path) -> int:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    while True:
        package = current / "node_modules" / "docx" / "package.json"
        if package.is_file():
            print(json.dumps({"found": str(package), "source": "local node_modules"}, ensure_ascii=False))
            return 0
        if current.parent == current:
            break
        current = current.parent
    bundled = SCRIPT_DIR.parent / "vendor" / "docx" / "package.json"
    if bundled.is_file():
        print(json.dumps({"found": str(bundled), "source": "bundled reference"}, ensure_ascii=False))
        print(
            "提示：build 由 Node 解析调用方项目中的 docx；如未安装，请使用 npm install docx。",
            file=sys.stderr,
        )
        return 0
    print("docx.py check-docx: local docx package not found", file=sys.stderr)
    return 2


def _local_docx_package(start: Path) -> Path | None:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    while True:
        package = current / "node_modules" / "docx" / "package.json"
        if package.is_file():
            return package.parent
        if current.parent == current:
            return None
        current = current.parent


def _node_build_command(node: str, script: Path, output: Path) -> tuple[list[str], tempfile.TemporaryDirectory | None]:
    """Prefer a caller's package; otherwise map the bundled CommonJS package."""

    local_package = _local_docx_package(script)
    if local_package is not None:
        return [node, str(script), str(output)], None
    bundled = SCRIPT_DIR.parent / "vendor" / "docx"
    if not (bundled / "index.js").is_file():
        return [node, str(script), str(output)], None
    loader_dir = tempfile.TemporaryDirectory(prefix="docx-loader-")
    loader = Path(loader_dir.name) / "loader.mjs"
    loader.write_text(
        f"const bundled = {json.dumps((bundled / 'index.js').resolve().as_uri())};\n"
        "export async function resolve(specifier, context, nextResolve) {\n"
        "  if (specifier === 'docx') return { url: bundled, shortCircuit: true };\n"
        "  return nextResolve(specifier, context);\n"
        "}\n",
        encoding="utf-8",
    )
    return [node, "--experimental-loader", str(loader), str(script), str(output)], loader_dir


def _build(script: Path, output: Path, force: bool) -> int:
    script = script.expanduser().resolve()
    output = output.expanduser().resolve()
    if not script.is_file():
        print(f"docx.py build: JavaScript file not found: {script}", file=sys.stderr)
        return 2
    if output.exists() and not force:
        print(f"docx.py build: output exists (use --force): {output}", file=sys.stderr)
        return 2
    node = shutil.which("node")
    if not node:
        print("docx.py build: Node.js executable not found", file=sys.stderr)
        return 2
    lint_status = _run_lint([script])
    if lint_status:
        return lint_status
    syntax = subprocess.run([node, "--check", str(script)], check=False)
    if syntax.returncode:
        return syntax.returncode
    output.parent.mkdir(parents=True, exist_ok=True)
    command, loader_dir = _node_build_command(node, script, output)
    try:
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
    finally:
        if loader_dir is not None:
            loader_dir.cleanup()
    if not output.is_file() or output.stat().st_size == 0:
        print("docx.py build: script returned without a DOCX", file=sys.stderr)
        return 1
    return _run(SCRIPT_DIR / "verify" / "verify.py", [str(output)])


def _usage() -> None:
    print(
        "usage: python3 docx.py {build,validate,lint,md2docx,check-docx,render} ...\n"
        "  build <script.js> <output.docx> [--force]\n"
        "  validate <file.docx>\n"
        "  lint <script.js> [<script.js> ...]\n"
        "  md2docx <input.md> <output.docx> [md2docx options]\n"
        "  check-docx [project-directory]\n"
        "  render <file.docx> <qa-directory> [--dpi N] [--force]"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True, description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    build = subparsers.add_parser("build", help="lint, run, and validate a docx-js script")
    build.add_argument("script", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--force", action="store_true")
    validate = subparsers.add_parser("validate", help="validate and repair a DOCX")
    validate.add_argument("file", type=Path)
    lint = subparsers.add_parser("lint", help="lint one or more docx-js scripts")
    lint.add_argument("scripts", type=Path, nargs="+")
    md2docx = subparsers.add_parser("md2docx", help="convert Markdown with Pandoc citeproc")
    md2docx.add_argument("args", nargs=argparse.REMAINDER)
    check = subparsers.add_parser("check-docx", help="find a local docx npm package")
    check.add_argument("directory", type=Path, nargs="?", default=Path.cwd())
    render = subparsers.add_parser("render", help="render DOCX through LibreOffice and Poppler")
    render.add_argument("input", type=Path)
    render.add_argument("output_dir", type=Path)
    render.add_argument("--dpi", type=int, default=150)
    render.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.command is None:
        _usage()
        return 2
    if args.command == "build":
        return _build(args.script, args.output, args.force)
    if args.command == "validate":
        return _run(SCRIPT_DIR / "verify" / "verify.py", [str(args.file)])
    if args.command == "lint":
        return _run_lint(args.scripts)
    if args.command == "md2docx":
        if not args.args:
            print("docx.py md2docx: provide input and output paths", file=sys.stderr)
            return 2
        return _run(SCRIPT_DIR / "md2docx_citeproc.py", args.args)
    if args.command == "check-docx":
        return _check_docx(args.directory)
    if args.command == "render":
        return _run(
            SCRIPT_DIR / "render_docx.py",
            [str(args.input), str(args.output_dir), "--dpi", str(args.dpi)]
            + (["--force"] if args.force else []),
        )
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
