#!/usr/bin/env python3
"""Extract text and/or image layers from legacy .doc (OLE2) without interpretation.

docext node: decode only. Semantic reading belongs to docread (model).

Output layout::

    <output-dir>/<source-stem>/layers.json
    <output-dir>/<source-stem>/text.txt          # when text layer requested and found
    <output-dir>/<source-stem>/img_XXX.<ext>    # when image layer requested

layers.json fields: source, mode, text_path, text_chars, images[], errors[].
Exit non-zero only when the file cannot be opened at all; partial layer
failures are recorded in errors[] and still produce layers.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

# Reuse JPEG/PNG carving from sibling module when available.
try:
    from extract_images import extract_doc_images
except ImportError:  # allow `python3 scripts/extract_doc_layers.py` from the skill root
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from extract_images import extract_doc_images


def _extract_ole_text(data: bytes) -> tuple[str, list[str]]:
    """Best-effort text scrape from a Word OLE compound file.

    Prefers the WordDocument stream via olefile; falls back to UTF-16LE /
    CP945-ish printable runs so a missing dependency still yields something
    usable for image_only vs readable triage downstream.
    """
    errors: list[str] = []
    text = ""
    try:
        import olefile  # type: ignore
    except ImportError:
        olefile = None
        errors.append("olefile not installed; using binary string scrape")

    if olefile is not None:
        try:
            ole = olefile.OleFileIO(data)
            stream_names = ["/WordDocument", "WordDocument"]
            blob = None
            for name in stream_names:
                if ole.exists(name):
                    blob = ole.openstream(name).read()
                    break
            # Some files expose streams as path lists
            if blob is None:
                for entry in ole.listdir():
                    joined = "/".join(entry)
                    if joined.lower().endswith("worddocument") or entry[-1].lower() == "worddocument":
                        blob = ole.openstream(entry).read()
                        break
            ole.close()
            if blob:
                text = _decode_word_stream(blob)
            else:
                errors.append("WordDocument stream not found")
        except Exception as exc:  # noqa: BLE001 — surface to errors[]
            errors.append(f"olefile read failed: {exc}")

    if not text.strip():
        text = _scrape_printable(data)
    return text, errors


def _decode_word_stream(blob: bytes) -> str:
    # WordDocument is mixed binary; keep UTF-16LE runs containing printable
    # ASCII or common CJK characters. Decode first because bytes regexes do not
    # support Unicode escapes such as ``\u4e00``.
    chunks: list[str] = []
    run: list[str] = []

    def is_text_char(char: str) -> bool:
        codepoint = ord(char)
        return (
            (char.isascii() and (char.isprintable() or char in "\r\n\t"))
            or 0x2E80 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0xFF00 <= codepoint <= 0xFFEF
            or 0x20000 <= codepoint <= 0x2FA1F
        )

    for char in blob.decode("utf-16le", errors="ignore"):
        if is_text_char(char):
            run.append(char)
        else:
            if len(run) >= 4:
                chunks.append("".join(run))
            run.clear()
    if len(run) >= 4:
        chunks.append("".join(run))
    if chunks:
        return _normalize_ws("\n".join(chunks))
    try:
        return _normalize_ws(blob.decode("latin-1", errors="ignore"))
    except Exception:
        return ""


def _scrape_printable(data: bytes) -> str:
    ascii_runs = [
        m.group().decode("ascii", errors="ignore")
        for m in re.finditer(rb"[\x20-\x7e\r\n\t]{6,}", data)
    ]
    utf16_runs = []
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){6,}", data):
        utf16_runs.append(m.group().decode("utf-16le", errors="ignore"))
    return _normalize_ws("\n".join(utf16_runs + ascii_runs))


def _normalize_ws(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def extract_doc_layers(
    source: Path,
    output_root: Path,
    mode: str = "auto",
    forensic_result: str | None = None,
) -> dict:
    if not source.is_file():
        raise FileNotFoundError(f"input not found: {source}")
    if source.suffix.lower() != ".doc":
        raise ValueError(f"extract_doc_layers expects .doc, got: {source.suffix}")

    data = source.read_bytes()
    if len(data) < 8:
        raise ValueError(f"file too small to be a .doc: {source}")

    # OLE magic D0 CF 11 E0
    if not data.startswith(b"\xd0\xcf\x11\xe0"):
        # still attempt; may be misnamed
        pass

    if forensic_result == "image_only":
        mode = "images"
    elif forensic_result == "readable" and mode == "auto":
        mode = "both"
    elif mode == "auto":
        mode = "both"

    target = output_root / source.stem
    target.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "source": source.name,
        "mode": mode,
        "forensic_result": forensic_result,
        "text_path": None,
        "text_chars": 0,
        "images": [],
        "errors": [],
    }

    if mode in ("text", "both"):
        text, errs = _extract_ole_text(data)
        result["errors"].extend(errs)
        if text.strip():
            text_path = target / "text.txt"
            text_path.write_text(text, encoding="utf-8")
            result["text_path"] = str(text_path.name)
            result["text_chars"] = len(text)
        else:
            result["errors"].append("no text layer extracted")

    if mode in ("images", "both"):
        try:
            entries = extract_doc_images(source, target)
            result["images"] = [
                {"image": e["image"], "context": e.get("context", {})} for e in entries
            ]
            if not entries:
                result["errors"].append("no embedded images carved")
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"image carve failed: {exc}")

    manifest = target / "layers.json"
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def classify_doc_forensic(source: Path) -> dict:
    """Classify a legacy .doc for the flowA routing field, with observed evidence."""
    if not source.is_file():
        raise FileNotFoundError(f"input not found: {source}")
    if source.suffix.lower() != ".doc":
        raise ValueError(f"classify_doc_forensic expects .doc, got: {source.suffix}")

    data = source.read_bytes()
    if len(data) < 8:
        return {
            "doc_forensic_result": "damaged",
            "evidence": "文件短于 OLE 复合文档头，无法读取",
            "text_chars": 0,
            "image_count": 0,
        }
    if not data.startswith(b"\xd0\xcf\x11\xe0"):
        return {
            "doc_forensic_result": "damaged",
            "evidence": "文件未检测到 OLE 复合文档签名，疑似损坏或扩展名错误",
            "text_chars": 0,
            "image_count": 0,
        }

    text, text_errors = _extract_ole_text(data)
    if text.strip():
        return {
            "doc_forensic_result": "readable",
            "evidence": "已抽取到文字层",
            "text_chars": len(text),
            "image_count": 0,
            "errors": text_errors,
        }

    try:
        with tempfile.TemporaryDirectory(prefix="doc-forensic-") as temp_dir:
            images = extract_doc_images(source, Path(temp_dir))
    except Exception as exc:  # noqa: BLE001
        images = []
        text_errors.append(f"image carve failed: {exc}")

    if images:
        return {
            "doc_forensic_result": "image_only",
            "evidence": "未抽取到文字层，检测到嵌入图片",
            "text_chars": 0,
            "image_count": len(images),
            "errors": text_errors,
        }
    return {
        "doc_forensic_result": "damaged",
        "evidence": "未抽取到文字层或嵌入图片，需索取原件人工核查",
        "text_chars": 0,
        "image_count": 0,
        "errors": text_errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help=".doc file")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--classify-only",
        action="store_true",
        help="emit doc_forensic_result without extracting layers",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "text", "images", "both"],
        default="auto",
        help="which layers to extract (auto→both unless forensic overrides)",
    )
    parser.add_argument(
        "--doc-forensic-result",
        choices=["readable", "image_only", "damaged"],
        default=None,
        help="optional fdoc result; image_only forces images-only",
    )
    args = parser.parse_args()

    if args.classify_only:
        try:
            result = classify_doc_forensic(args.input)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return

    if args.output_dir is None:
        parser.error("--output-dir is required unless --classify-only")

    if args.doc_forensic_result == "damaged":
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "doc_forensic_result=damaged: refuse extract; use docdmg path",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        result = extract_doc_layers(
            args.input, args.output_dir, mode=args.mode, forensic_result=args.doc_forensic_result
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
