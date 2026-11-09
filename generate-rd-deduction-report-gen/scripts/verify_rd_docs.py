#!/usr/bin/env python3
"""Verify rendered DOCX/XLSX files against the project facts and manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .report_verification import verify_outputs
    from .rule_engine import load_rules
except ImportError:  # Running as a script from the skill root.
    from report_verification import verify_outputs  # type: ignore[no-redef]
    from rule_engine import load_rules  # type: ignore[no-redef]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="normalized project facts JSON")
    parser.add_argument("--template-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    try:
        manifest = json.loads((args.template_dir / "report.json").read_text(encoding="utf-8"))
        rules = load_rules(args.template_dir / "rules.json")
        data = json.loads(args.input.read_text(encoding="utf-8"))
        verify_outputs(data, args.output_dir, manifest, rules)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"ok": False, "verify_passed": False, "error": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(1) from exc

    print(json.dumps({"ok": True, "verify_passed": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
