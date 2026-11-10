#!/usr/bin/env python3
"""Render a local Word file through LibreOffice and Poppler.

The command produces a PDF and one PNG per page using local file paths and
executables.

Usage::

    python3 render_docx.py input.docx output-directory

``soffice`` is used for the DOCX/DOC/DOTX to PDF conversion and ``pdftoppm``
is used for PDF to PNG rendering.  The output directory is replaced as one
operation only after both stages succeed; an existing directory requires
``--force``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from office.soffice import get_soffice_env, run_soffice
except ImportError:  # pragma: no cover - useful when imported from another cwd
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from office.soffice import get_soffice_env, run_soffice


PAGE_RE = re.compile(r"-(\d+)\.png$")


class RenderError(RuntimeError):
    """A dependency, conversion, or output error that should be shown to a user."""


def _page_key(path: Path) -> tuple[int, str]:
    match = PAGE_RE.search(path.name)
    return (int(match.group(1)), path.name) if match else (10**9, path.name)


def _unique_backup(destination: Path) -> Path:
    """Choose a sibling backup path without touching an existing sibling."""

    stamp = time.strftime("%Y%m%d-%H%M%S")
    serial = 0
    while True:
        suffix = f".previous-{stamp}" if serial == 0 else f".previous-{stamp}-{serial}"
        candidate = destination.with_name(f".{destination.name}{suffix}")
        if not candidate.exists():
            return candidate
        serial += 1


def _replace_directory(staged: Path, destination: Path) -> None:
    """Atomically publish ``staged`` while retaining a rollback path."""

    backup: Path | None = None
    if destination.exists():
        backup = _unique_backup(destination)
        os.replace(destination, backup)
    try:
        os.replace(staged, destination)
    except Exception:
        if backup is not None and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup is not None:
        if backup.is_dir():
            shutil.rmtree(backup)
        else:
            backup.unlink()


def _convert_with_libreoffice(executable: str, args: list[str]) -> subprocess.CompletedProcess:
    """Run either the standard ``soffice`` wrapper or a ``libreoffice`` binary."""

    if Path(executable).name == "soffice":
        return run_soffice(args, capture_output=True, text=True, check=False)
    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile:
        profile_arg = f"-env:UserInstallation={Path(profile).as_uri()}"
        return subprocess.run(
            [executable, profile_arg, *args],
            env=get_soffice_env(),
            capture_output=True,
            text=True,
            check=False,
        )


def render_document(
    input_path: Path,
    output_dir: Path,
    *,
    dpi: int = 150,
    force: bool = False,
) -> dict[str, object]:
    input_path = input_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not input_path.is_file():
        raise RenderError(f"input document not found: {input_path}")
    if input_path.suffix.lower() not in {".doc", ".docx", ".dot", ".dotx"}:
        raise RenderError("input must be a DOC, DOCX, DOT, or DOTX file")
    if dpi < 36 or dpi > 1200:
        raise RenderError("dpi must be between 36 and 1200")
    if output_dir == input_path.parent:
        raise RenderError("output directory cannot be the input document's parent")
    if output_dir.exists() and not force:
        raise RenderError(f"output directory already exists (use --force): {output_dir}")
    if output_dir.exists() and not output_dir.is_dir():
        raise RenderError(f"output path is not a directory: {output_dir}")

    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    if not soffice:
        raise RenderError("LibreOffice executable not found (expected soffice or libreoffice)")
    if not pdftoppm:
        raise RenderError("Poppler executable not found (expected pdftoppm)")

    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}.", dir=parent) as work:
        work_dir = Path(work)
        pdf_dir = work_dir / "pdf"
        pdf_dir.mkdir()
        try:
            result = _convert_with_libreoffice(
                soffice,
                [
                    "--headless",
                    "--convert-to",
                    "pdf",
                    str(input_path),
                    "--outdir",
                    str(pdf_dir),
                ],
            )
        except Exception as exc:  # pragma: no cover - platform-dependent wrapper errors
            raise RenderError(f"LibreOffice could not start: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RenderError(f"LibreOffice conversion failed: {detail}")

        pdf_candidates = sorted(pdf_dir.glob("*.pdf"))
        if not pdf_candidates:
            detail = (result.stderr or result.stdout or "").strip()
            raise RenderError(f"LibreOffice produced no PDF{': ' + detail if detail else ''}")
        pdf_path = pdf_candidates[0]
        image_prefix = work_dir / "page"
        image_result = subprocess.run(
            [pdftoppm, "-png", "-r", str(dpi), str(pdf_path), str(image_prefix)],
            capture_output=True,
            text=True,
            check=False,
        )
        if image_result.returncode != 0:
            detail = (image_result.stderr or image_result.stdout or "").strip()
            raise RenderError(f"pdftoppm failed: {detail}")
        images = sorted(work_dir.glob("page-*.png"), key=_page_key)
        if not images:
            raise RenderError("pdftoppm produced no page images")

        staged = work_dir / "published"
        staged.mkdir()
        staged_pdf = staged / f"{input_path.stem}.pdf"
        shutil.copy2(pdf_path, staged_pdf)
        staged_images: list[Path] = []
        for index, image in enumerate(images, 1):
            target = staged / f"page-{index:03d}.png"
            shutil.copy2(image, target)
            staged_images.append(target)
        report = {
            "input": str(input_path),
            "output": str(output_dir),
            "pdf": str(staged_pdf.relative_to(staged)),
            "pages": [str(path.relative_to(staged)) for path in staged_images],
            "dpi": dpi,
            "engine": "LibreOffice -> Poppler",
        }
        (staged / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _replace_directory(staged, output_dir)

    report["pdf"] = str(output_dir / report["pdf"])
    report["pages"] = [str(output_dir / page) for page in report["pages"]]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="DOC, DOCX, DOT, or DOTX file")
    parser.add_argument("output_dir", type=Path, help="directory for the PDF, PNG pages, and report")
    parser.add_argument("--dpi", type=int, default=150, help="Poppler rasterization DPI (default: 150)")
    parser.add_argument("--force", action="store_true", help="replace an existing output directory")
    args = parser.parse_args(argv)
    try:
        report = render_document(args.input, args.output_dir, dpi=args.dpi, force=args.force)
    except RenderError as exc:
        print(f"render_docx: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"render_docx: filesystem error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
