#!/usr/bin/env python3
"""Executable rule-spec interpreter for the document generation pipeline.

Rules live in ``templates/rules.json`` (or a business-specific copy): a
parseable specification with Chinese names and descriptions, executed by the
fixed check vocabulary implemented here. ``input`` stage rules run against
the raw JSON before normalization; ``model`` stage rules run against the
normalized projection. Rules that need semantic understanding are *not* in
this file — see ``references/rules.md``.

Check vocabulary (extend only when a new *shape* of determinism is needed):

- ``required``      top-level fields must be present and non-empty
- ``list_length``   a list field must exist with exactly ``equals`` items
- ``item_required`` every item of a list must provide non-empty subfields
- ``paired``        fields must be all-present or all-empty
- ``date_order``    ordered date fields must parse and be non-decreasing
- ``item_regex``    every item's field must fullmatch a pattern
- ``item_unique``   every item's field value must be unique
- ``item_sequential`` numeric suffixes must form a continuous sequence
- ``item_pages``    Word page references: single, range or comma list
- ``paths_exist``   files referenced by ``a[].b[].path`` expressions exist
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "templates" / "rules.json"

PAGE_COMPONENT = r"(?:第\s*)?\d+(?:\s*[-~—]\s*(?:第\s*)?\d+)?"
PAGE_RE = re.compile(rf"^\s*{PAGE_COMPONENT}(?:\s*[、,，]\s*{PAGE_COMPONENT})*\s*页?\s*$")


def load_rules(path: str | Path | None = None) -> dict:
    """Load a rules specification; falls back to the bundled default."""
    candidate = Path(path) if path else DEFAULT_RULES_PATH
    if not candidate.exists():
        if candidate != DEFAULT_RULES_PATH and DEFAULT_RULES_PATH.exists():
            candidate = DEFAULT_RULES_PATH
        else:
            raise FileNotFoundError(f"Rules specification not found: {candidate}")
    rules = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(rules.get("stages"), Mapping) or "placeholder" not in rules:
        raise ValueError(f"Rules specification {candidate} must contain 'stages' and 'placeholder'")
    return rules


def placeholder_re(rules: Mapping) -> re.Pattern:
    return re.compile(rules["placeholder"]["pattern"])


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "；".join(_as_text(item) for item in value)
    if isinstance(value, Mapping):
        return "；".join(f"{key}：{_as_text(item)}" for key, item in value.items())
    return str(value)


# ---------------------------------------------------------------------------
# Check implementations. Each raises ValueError with the rule's message on
# violation and never returns a value.
# ---------------------------------------------------------------------------

def check_required(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    for field in rule["fields"]:
        if _empty(data.get(field)):
            raise ValueError(rule["message"].format(field=field))


def check_list_length(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    value = data.get(rule["field"]) or []
    if not isinstance(value, list) or len(value) != rule["equals"]:
        raise ValueError(rule["message"])


def check_item_required(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    items = data.get(rule["field"]) or []
    for index, item in enumerate(items, start=1):
        for subfield in rule["subfields"]:
            if not isinstance(item, Mapping) or _empty(item.get(subfield)):
                raise ValueError(rule["message"].format(index=index, subfield=subfield))


def _items_for_rule(data: Mapping, rule: Mapping) -> list[Any]:
    items = data.get(rule["field"]) or []
    channel_field = rule.get("channel_field")
    if not channel_field:
        return items
    expected_channel = rule.get("channel_value", "word")
    return [
        item
        for item in items
        if isinstance(item, Mapping) and item.get(channel_field, "word") == expected_channel
    ]


def check_paired(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    first, second = rule["fields"]
    if _empty(data.get(first)) != _empty(data.get(second)):
        raise ValueError(rule["message"])


def check_date_order(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    placeholder = placeholder_re(rules)
    parsed: list[tuple[str, datetime]] = []
    for field in rule["fields"]:
        value = _as_text(data.get(field))
        if not value or placeholder.search(value):
            continue  # 日期缺失或待补时不参与比较，由语义规则兜底
        moment = None
        for fmt in rule["formats"]:
            try:
                moment = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        if moment is None:
            raise ValueError(f"Invalid date format for {field}: {value}")
        parsed.append((field, moment))
    if any(left[1] > right[1] for left, right in zip(parsed, parsed[1:])):
        raise ValueError(rule["message"])


def check_item_regex(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    pattern = re.compile(rule["pattern"])
    for item in _items_for_rule(data, rule):
        if not pattern.fullmatch(_as_text(item.get(rule["item_field"]))):
            raise ValueError(rule["message"])


def check_item_unique(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    values = [_as_text(item.get(rule["item_field"])) for item in data.get(rule["field"]) or []]
    if len(values) != len(set(values)):
        raise ValueError(rule["message"])


def check_item_sequential(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    prefix = rule["prefix"]
    values = [_as_text(item.get(rule["item_field"])) for item in _items_for_rule(data, rule)]
    suffixes = [value[len(prefix):] for value in values if value.startswith(prefix)]
    numbers = [int(suffix) for suffix in suffixes if suffix.isdigit()]
    if len(numbers) != len(values):
        raise ValueError(rule["message"])
    start = rule["start"]
    if numbers != list(range(start, start + len(numbers))):
        raise ValueError(rule["message"])


def _valid_pages(value: Any) -> bool:
    if isinstance(value, int) and not isinstance(value, bool):
        return value > 0
    if not isinstance(value, str) or not PAGE_RE.fullmatch(value):
        return False
    components = re.split(r"[、,，]", value.strip().removesuffix("页"))
    for component in components:
        numbers = [int(item) for item in re.findall(r"\d+", component)]
        if any(number <= 0 for number in numbers):
            return False
        if len(numbers) == 2 and numbers[0] > numbers[1]:
            return False
    return True


def check_item_pages(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    for item in _items_for_rule(data, rule):
        if not _valid_pages(item.get(rule["item_field"])):
            raise ValueError(rule["message"])


def _walk_paths(node: Any, segments: list[str], found: list[str]) -> None:
    if not segments:
        if isinstance(node, str) and node:
            found.append(node)
        return
    segment, rest = segments[0], segments[1:]
    if segment.endswith("[]"):
        field = segment[:-2]
        if isinstance(node, Mapping):
            node = node.get(field)
        if isinstance(node, list):
            for item in node:
                _walk_paths(item, rest, found)
        return
    if isinstance(node, Mapping):
        _walk_paths(node.get(segment), rest, found)


def check_paths_exist(data: Mapping, rule: Mapping, rules: Mapping) -> None:
    for expression in rule["paths"]:
        found: list[str] = []
        _walk_paths(data, expression.split("."), found)
        for path in found:
            if not Path(path).exists():
                raise ValueError(rule["message"].format(path=path))


CHECKS = {
    "required": check_required,
    "list_length": check_list_length,
    "item_required": check_item_required,
    "paired": check_paired,
    "date_order": check_date_order,
    "item_regex": check_item_regex,
    "item_unique": check_item_unique,
    "item_sequential": check_item_sequential,
    "item_pages": check_item_pages,
    "paths_exist": check_paths_exist,
}


def run_stage(data: Mapping, rules: Mapping, stage: str) -> None:
    for rule in rules.get("stages", {}).get(stage, []):
        check = CHECKS.get(rule.get("check"))
        if check is None:
            raise ValueError(f"Unknown rule check type: {rule.get('check')} (rule: {rule.get('name')})")
        check(data, rule, rules)


def validate(value: Mapping, projection: Mapping, rules: Mapping) -> None:
    """Run input-stage rules on the raw JSON, then model-stage rules on the
    normalized projection."""
    run_stage(value, rules, "input")
    run_stage(projection, rules, "model")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate raw and normalized project JSON against rules.")
    parser.add_argument("--input", required=True, type=Path, help="raw facts JSON")
    parser.add_argument("--projection", required=True, type=Path, help="normalized projection JSON")
    parser.add_argument("--rules", type=Path, help="rules JSON; defaults to templates/rules.json")
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        projection = json.loads(args.projection.read_text(encoding="utf-8"))
        validate(raw, projection, load_rules(args.rules))
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps({"ok": False, "valid": False, "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        sys.exit(1)
    print(json.dumps({"ok": True, "valid": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
