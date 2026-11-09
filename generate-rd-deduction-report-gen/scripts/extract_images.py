#!/usr/bin/env python3
"""Extract embedded images from Word/Excel materials, carrying page context.

Materials often carry facts as embedded images (photos of logs, scanned
reports, screenshots).  Text extraction returns nothing for them; this
module extracts each image together with the context needed to interpret
it:

- DOCX: images are extracted in document order with the surrounding text
  (nearest preceding heading, containing paragraph, next paragraph);
- XLSX: images are extracted with sheet name, anchor cell and the nearest
  non-empty neighbouring cells;
- DOC (OLE2): embedded JPEG/PNG are carved from the binary stream (no
  context available — page order only).

Extraction is only the first step: ``--ocr`` runs tesseract (chi_sim+eng)
on each image and stores the recognized text in the manifest.  OCR text
must be treated as 待核对 unless it matches the visual content; the
context recorded here is what allows a reader to confirm or correct it.

Output layout::

    <output-dir>/<source-stem>/img_001.<ext>
    <output-dir>/<source-stem>/manifest.json

Standalone image files (``.jpg``/``.png``/...) are first-class inputs too:
an attachment page may exist with no surrounding context at all — the
filename itself (e.g. a product label scan) is often the only context, so
it is recorded, and OCR still runs.  Missing context must never mean
"skip recognition".
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
EXTRACTABLE_SUFFIXES = IMAGE_SUFFIXES | {".docx", ".xlsm", ".xlsx", ".doc"}


JPEG_SOI = b"\xff\xd8\xff"
JPEG_EOI = b"\xff\xd9"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND"


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def _docx_paragraph_context(paragraphs: list, index: int) -> dict:
    def text_at(i: int) -> str:
        return paragraphs[i].text.strip() if 0 <= i < len(paragraphs) else ""

    previous = ""
    for i in range(index - 1, -1, -1):
        if paragraphs[i].text.strip():
            previous = paragraphs[i].text.strip()
            break
    following = ""
    for i in range(index + 1, len(paragraphs)):
        if paragraphs[i].text.strip():
            following = paragraphs[i].text.strip()
            break
    heading = ""
    for i in range(index, -1, -1):
        style = paragraphs[i].style.name if paragraphs[i].style is not None else ""
        if style.startswith("Heading") and paragraphs[i].text.strip():
            heading = paragraphs[i].text.strip()
            break
    return {
        "heading": heading,
        "paragraph": text_at(index),
        "previous": previous,
        "following": following,
    }


def extract_docx_images(source: Path, target_dir: Path) -> list[dict]:
    from docx import Document

    target_dir.mkdir(parents=True, exist_ok=True)
    document = Document(str(source))
    entries: list[dict] = []
    paragraphs = document.paragraphs
    seen: set[int] = set()
    sequence = 0
    for index, paragraph in enumerate(paragraphs):
        blips = paragraph._p.findall(
            ".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
        )
        for blip in blips:
            embed = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
            if not embed:
                continue
            part = document.part.related_parts.get(embed)
            if part is None or id(part) in seen:
                continue
            seen.add(id(part))
            sequence += 1
            suffix = Path(str(part.partname)).suffix or ".bin"
            image_path = target_dir / f"img_{sequence:03d}{suffix}"
            image_path.write_bytes(part.blob)
            entry = {
                "source": source.name,
                "kind": "docx",
                "image": image_path.name,
                "context": _docx_paragraph_context(paragraphs, index),
            }
            entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

def extract_xlsx_images(source: Path, target_dir: Path) -> list[dict]:
    from openpyxl import load_workbook

    target_dir.mkdir(parents=True, exist_ok=True)
    workbook = load_workbook(str(source))
    entries: list[dict] = []
    sequence = 0
    for sheet in workbook.worksheets:
        for image in getattr(sheet, "_images", []):
            anchor = getattr(image, "anchor", None)
            row = getattr(getattr(anchor, "_from", None), "row", None)
            col = getattr(getattr(anchor, "_from", None), "col", None)

            def cell_at(r: int, c: int) -> str:
                if r is None or c is None or r < 0 or c < 0:
                    return ""
                value = sheet.cell(row=r + 1, column=c + 1).value
                return str(value).strip() if value is not None else ""

            near = ""
            for dr, dc in ((0, -1), (0, -2), (-1, 0), (-2, 0), (1, 0)):
                near = cell_at((row or 0) + dr, (col or 0) + dc) if row is not None and col is not None else ""
                if near:
                    break
            ref = sheet.cell(row=(row or 0) + 1, column=(col or 0) + 1).coordinate if row is not None and col is not None else ""
            sequence += 1
            image_path = target_dir / f"img_{sequence:03d}.png"
            image_path.write_bytes(image._data())
            entries.append(
                {
                    "source": source.name,
                    "kind": "xlsx",
                    "image": image_path.name,
                    "context": {
                        "sheet": sheet.title,
                        "cell": ref,
                        "nearby": near,
                    },
                }
            )
    workbook.close()
    return entries


# ---------------------------------------------------------------------------
# DOC (OLE2) — carve JPEG/PNG from the binary streams
# ---------------------------------------------------------------------------

def _carve_images(data: bytes) -> list[tuple[str, bytes]]:
    images: list[tuple[str, bytes]] = []
    sois = [m.start() for m in re.finditer(re.escape(JPEG_SOI), data)]
    for i, start in enumerate(sois):
        region_end = sois[i + 1] if i + 1 < len(sois) else len(data)
        end = data.rfind(JPEG_EOI, start, region_end)
        if end < 0:
            continue
        images.append(("jpg", data[start : end + 2]))
    pos = 0
    while True:
        start = data.find(PNG_SIG, pos)
        if start < 0:
            break
        end = data.find(PNG_IEND, start)
        if end < 0:
            break
        images.append(("png", data[start : end + 8]))
        pos = end + 8
    return images


def extract_doc_images(source: Path, target_dir: Path) -> list[dict]:
    target_dir.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    entries: list[dict] = []
    for sequence, (ext, blob) in enumerate(_carve_images(data), start=1):
        image_path = target_dir / f"img_{sequence:03d}.{ext}"
        image_path.write_bytes(blob)
        entries.append(
            {
                "source": source.name,
                "kind": "doc",
                "image": image_path.name,
                "context": {"page_order": sequence, "note": "doc 图片无文字上下文，按出现顺序对应页序"},
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Standalone image files (attachment pages without context)
# ---------------------------------------------------------------------------

def extract_standalone_image(source: Path, target_dir: Path) -> list[dict]:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"img_001{source.suffix.lower()}"
    shutil.copy2(source, target)
    return [
        {
            "source": source.name,
            "kind": "image",
            "image": target.name,
            "context": {
                "filename": source.name,
                "note": "独立附件图片，无环绕上下文；文件名本身即主要语义线索",
            },
        }
    ]


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def ocr_images(entries: list[dict], target_dir: Path, lang: str = "chi_sim+eng") -> None:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise RuntimeError("--ocr requires tesseract on PATH")
    for entry in entries:
        image_path = target_dir / entry["image"]
        result = subprocess.run(
            [tesseract, str(image_path), "stdout", "-l", lang, "--psm", "6"],
            capture_output=True,
            text=True,
        )
        text = "\n".join(line for line in result.stdout.splitlines() if line.strip())
        entry["ocr_text"] = text
        entry["ocr_error"] = result.stderr.strip() if result.returncode != 0 else ""


# ---------------------------------------------------------------------------
# Image class (document vs photo) — fimgx 取证分级
# ---------------------------------------------------------------------------

DOCUMENT_NAME_HINTS = (
    "扫描", "截图", "文档", "合同", "报告", "标签", "说明书", "检测", "报告单",
    "scan", "screenshot", "receipt", "invoice", "label",
)
PHOTO_NAME_HINTS = (
    "照片", "现场", "微信图片", "实拍", "photo", "camera", "img_",
)


def classify_image_class(source: Path) -> dict:
    """Heuristic image_class for standalone images. No LLM.

    Returns ``{"image_class": "document"|"photo", "reasons": [...]}``.
    Filename hints win over geometry; WeChat dumps default to photo unless
    the name clearly looks like a scanned document/label.
    """
    reasons: list[str] = []
    name = source.name
    lower = name.lower()

    for hint in DOCUMENT_NAME_HINTS:
        if hint.lower() in lower or hint in name:
            reasons.append(f"filename_hint:{hint}")
            return {"image_class": "document", "reasons": reasons, "source": name}
    for hint in PHOTO_NAME_HINTS:
        if hint.lower() in lower or hint in name:
            reasons.append(f"filename_hint:{hint}")
            return {"image_class": "photo", "reasons": reasons, "source": name}

    try:
        from PIL import Image

        with Image.open(source) as im:
            width, height = im.size
        if width > 0 and height > 0:
            ratio = max(width, height) / min(width, height)
            reasons.append(f"size:{width}x{height}")
            reasons.append(f"aspect:{ratio:.2f}")
            # Portrait near A4 (~1.41) or very tall → document scan tendency
            if 1.25 <= ratio <= 1.55 and min(width, height) >= 600:
                reasons.append("geometry:a4ish")
                return {"image_class": "document", "reasons": reasons, "source": name}
            if ratio >= 1.8 and height > width:
                reasons.append("geometry:tall_scan")
                return {"image_class": "document", "reasons": reasons, "source": name}
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"geometry_error:{exc}")

    reasons.append("default:photo")
    return {"image_class": "photo", "reasons": reasons, "source": name}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def extract_source(source: Path, output_root: Path, with_ocr: bool) -> list[dict]:
    target_dir = output_root / source.stem
    target_dir.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".docx":
        entries = extract_docx_images(source, target_dir)
    elif source.suffix.lower() in (".xlsx", ".xlsm"):
        entries = extract_xlsx_images(source, target_dir)
    elif source.suffix.lower() == ".doc":
        entries = extract_doc_images(source, target_dir)
    elif source.suffix.lower() in IMAGE_SUFFIXES:
        entries = extract_standalone_image(source, target_dir)
    else:
        raise ValueError(f"Unsupported file type: {source}")
    if with_ocr and entries:
        ocr_images(entries, target_dir)
    manifest = target_dir / "manifest.json"
    manifest.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="file or directory to scan")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="required for extract mode; optional for --classify",
    )
    parser.add_argument("--ocr", action="store_true", help="run tesseract on each extracted image")
    parser.add_argument(
        "--classify",
        action="store_true",
        help="fimgx mode: emit image_class JSON (document|photo), no extract",
    )
    args = parser.parse_args()

    if args.classify:
        sources = (
            sorted(p for p in args.input.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
            if args.input.is_dir()
            else [args.input]
        )
        if not sources:
            raise SystemExit("no image files to classify")
        results = []
        for source in sources:
            if source.suffix.lower() not in IMAGE_SUFFIXES:
                print(json.dumps({"ok": False, "error": f"not an image: {source}"}, ensure_ascii=False))
                raise SystemExit(1)
            results.append(classify_image_class(source))
        payload = results[0] if len(results) == 1 else {"items": results}
        payload_out = {"ok": True, **payload} if len(results) == 1 else {"ok": True, "items": results}
        print(json.dumps(payload_out, ensure_ascii=False, indent=2))
        return

    if args.output_dir is None:
        raise SystemExit("--output-dir is required unless --classify")

    sources = (
        sorted(p for p in args.input.rglob("*") if p.suffix.lower() in EXTRACTABLE_SUFFIXES)
        if args.input.is_dir()
        else [args.input]
    )
    total = 0
    for source in sources:
        try:
            entries = extract_source(source, args.output_dir, args.ocr)
        except Exception as exc:  # one bad file must not stop the batch
            print(f"[跳过] {source}: {exc}")
            continue
        total += len(entries)
        print(f"{source.name}: {len(entries)} 张图片")
    print(f"共提取 {total} 张图片 -> {args.output_dir}")


if __name__ == "__main__":
    main()
