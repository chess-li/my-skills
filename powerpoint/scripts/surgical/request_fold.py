#!/usr/bin/env python3
"""Publish a local working presentation to an explicit destination path.

Pass ``--source`` and ``--target`` or a JSON request file.  A target that
already exists is reported as a conflict unless ``--force`` is supplied.

Single operation::

    python3 request_fold.py --source working/report.pptx --target report.pptx

Request file::

    {"operations": [{"source": "working/report.pptx",
                      "target": "report.pptx", "force": true}]}

The copy is staged beside the destination and atomically renamed.  The output
is JSON with ``done``, ``planned``, ``conflict``, or ``error`` status so shell
and CI workflows can inspect it directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


class FoldError(RuntimeError):
    """A malformed local request or an unrecoverable filesystem error."""


def _path(value: Any, *, base: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise FoldError("source and target must be non-empty path strings")
    candidate = Path(value).expanduser()
    return (base / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()


def _operations_from_request(path: Path) -> list[dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FoldError(f"could not read request JSON: {exc}") from exc
    if isinstance(document, dict) and "operations" in document:
        operations = document["operations"]
    elif isinstance(document, dict):
        operations = [document]
    else:
        raise FoldError("request JSON must be an object or an object with an operations list")
    if not isinstance(operations, list) or not operations:
        raise FoldError("request operations must be a non-empty list")
    if not all(isinstance(item, dict) for item in operations):
        raise FoldError("each request operation must be an object")
    return operations


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_bool(value: Any, *, field: str) -> bool:
    """Accept JSON booleans only; strings and numbers must not grant overwrite."""

    if type(value) is not bool:
        raise FoldError(f"{field} must be a JSON boolean")
    return value


def _copy_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def fold_operations(
    operations: list[dict[str, Any]], *, base: Path, force: bool = False, dry_run: bool = False
) -> dict[str, Any]:
    planned: list[dict[str, Any]] = []
    conflicts: list[str] = []
    seen_targets: set[Path] = set()
    duplicate_targets: set[str] = set()
    for item in operations:
        source = _path(item.get("source"), base=base)
        target = _path(item.get("target"), base=base)
        operation_force = force or _strict_bool(item.get("force", False), field="force")
        if source == target:
            raise FoldError(f"source and target are the same path: {source}")
        if target in seen_targets:
            duplicate_targets.add(str(target))
        seen_targets.add(target)
        if not source.is_file():
            raise FoldError(f"source file not found: {source}")
        if target.exists() and target.is_dir():
            raise FoldError(f"target is a directory: {target}")
        if target.exists() and not operation_force:
            conflicts.append(str(target))
        planned.append(
            {
                "source": source,
                "target": target,
                "force": operation_force,
                "source_sha256": _sha256(source),
                "bytes": source.stat().st_size,
            }
        )
    if duplicate_targets:
        return {
            "status": "conflict",
            "conflicts": sorted(duplicate_targets),
            "operations": [],
        }
    if conflicts:
        return {"status": "conflict", "conflicts": conflicts, "operations": []}
    if dry_run:
        return {
            "status": "planned",
            "conflicts": [],
            "operations": [
                {
                    "source": str(item["source"]),
                    "target": str(item["target"]),
                    "bytes": item["bytes"],
                    "source_sha256": item["source_sha256"],
                }
                for item in planned
            ],
        }

    completed: list[dict[str, Any]] = []
    try:
        for item in planned:
            _copy_atomic(item["source"], item["target"])
            target_hash = _sha256(item["target"])
            if target_hash != item["source_sha256"]:
                raise FoldError(f"checksum mismatch after copy: {item['target']}")
            completed.append(
                {
                    "source": str(item["source"]),
                    "target": str(item["target"]),
                    "bytes": item["bytes"],
                    "sha256": target_hash,
                }
            )
    except (OSError, FoldError) as exc:
        raise FoldError(f"local publish failed after {len(completed)} operation(s): {exc}") from exc
    return {"status": "done", "conflicts": [], "operations": completed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--request", type=Path, help="JSON request file")
    group.add_argument("--source", type=Path, help="working presentation path")
    parser.add_argument("--target", type=Path, help="destination path (required with --source)")
    parser.add_argument("--force", action="store_true", help="overwrite existing targets")
    parser.add_argument("--dry-run", action="store_true", help="validate and report without copying")
    args = parser.parse_args(argv)

    try:
        if args.request is not None:
            request = args.request.expanduser().resolve()
            operations = _operations_from_request(request)
            base = request.parent
        else:
            if args.target is None:
                parser.error("--target is required with --source")
            operations = [{"source": str(args.source), "target": str(args.target)}]
            base = Path.cwd()
        report = fold_operations(operations, base=base, force=args.force, dry_run=args.dry_run)
    except FoldError as exc:
        report = {"status": "error", "error": str(exc), "operations": []}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report.get("status") == "conflict" else 0


if __name__ == "__main__":
    raise SystemExit(main())
