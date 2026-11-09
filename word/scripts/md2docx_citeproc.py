#!/usr/bin/env python3
"""Convert Markdown with standard citations to DOCX using Pandoc citeproc.

The input uses Pandoc's provider-independent citation syntax, for example
``[@smith2024]`` or ``[@smith2024, pp. 10-12]``.  Bibliographies may be
BibTeX/BibLaTeX, CSL JSON/YAML, or RIS files accepted by Pandoc.

Usage::

    python3 md2docx_citeproc.py report.md report.docx \
        --bibliography references.bib --csl apa.csl

The wrapper only assembles a local ``pandoc`` command.  It does not read a
platform citation database, call a service, or rewrite citation identifiers.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class ConversionError(RuntimeError):
    """A local input, dependency, or Pandoc conversion error."""


def _executable(value: str | None) -> str | None:
    if value:
        candidate = Path(value).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return shutil.which(value)
    return shutil.which("pandoc")


def _existing_file(path_value: str, label: str) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ConversionError(f"{label} not found: {path}")
    return path


def convert_markdown(
    input_path: Path,
    output_path: Path,
    *,
    bibliographies: list[Path] | None = None,
    csl: Path | None = None,
    reference_doc: Path | None = None,
    resource_paths: list[Path] | None = None,
    pandoc_bin: str | None = None,
    force: bool = False,
) -> dict[str, object]:
    input_path = _existing_file(str(input_path), "Markdown input")
    output_path = output_path.expanduser().resolve()
    if input_path == output_path:
        raise ConversionError("input and output must be different paths")
    if output_path.suffix.lower() != ".docx":
        raise ConversionError("output must use the .docx extension")
    if output_path.exists() and not force:
        raise ConversionError(f"output already exists (use --force): {output_path}")
    if output_path.exists() and not output_path.is_file():
        raise ConversionError(f"output path is not a regular file: {output_path}")
    executable = _executable(pandoc_bin)
    if not executable:
        raise ConversionError("Pandoc executable not found; install Pandoc locally and retry")

    bibliographies = bibliographies or []
    resource_paths = resource_paths or []
    for index, bibliography in enumerate(bibliographies, 1):
        bibliographies[index - 1] = _existing_file(str(bibliography), f"bibliography {index}")
    if csl is not None:
        csl = _existing_file(str(csl), "CSL style")
    if reference_doc is not None:
        reference_doc = _existing_file(str(reference_doc), "reference DOCX")
    resource_paths = [path.expanduser().resolve() for path in resource_paths]
    missing_resources = [path for path in resource_paths if not path.is_dir()]
    if missing_resources:
        raise ConversionError(f"resource path is not a directory: {missing_resources[0]}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.", suffix=".docx", dir=output_path.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    command = [
        executable,
        str(input_path),
        "--from=markdown",
        "--to=docx",
        "--standalone",
        "--citeproc",
        "--output",
        str(temporary),
    ]
    for bibliography in bibliographies:
        command.extend(["--bibliography", str(bibliography)])
    if csl is not None:
        command.extend(["--csl", str(csl)])
    if reference_doc is not None:
        command.extend(["--reference-doc", str(reference_doc)])
    if resource_paths:
        command.extend(["--resource-path", os.pathsep.join(str(path) for path in resource_paths)])

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise ConversionError(f"Pandoc conversion failed: {detail}")
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise ConversionError("Pandoc completed without producing a DOCX")
        os.replace(temporary, output_path)
    except OSError as exc:
        raise ConversionError(f"could not run Pandoc: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "input": str(input_path),
        "output": str(output_path),
        "bibliography": [str(path) for path in bibliographies],
        "citeproc": True,
        "pandoc": executable,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Markdown source")
    parser.add_argument("output", type=Path, help="DOCX destination")
    parser.add_argument("--bibliography", action="append", default=[], help="BibTeX, CSL JSON/YAML, or RIS file (repeatable)")
    parser.add_argument("--csl", type=Path, help="CSL citation style")
    parser.add_argument("--reference-doc", type=Path, help="DOCX template used by Pandoc")
    parser.add_argument("--resource-path", action="append", default=[], type=Path, help="asset directory (repeatable)")
    parser.add_argument("--pandoc-bin", help="Pandoc executable or absolute path (for testing or non-standard installs)")
    parser.add_argument("--force", action="store_true", help="replace an existing DOCX")
    args = parser.parse_args(argv)
    try:
        report = convert_markdown(
            args.input,
            args.output,
            bibliographies=args.bibliography,
            csl=args.csl,
            reference_doc=args.reference_doc,
            resource_paths=args.resource_path,
            pandoc_bin=args.pandoc_bin,
            force=args.force,
        )
    except ConversionError as exc:
        print(f"md2docx_citeproc: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
