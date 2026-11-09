"""Canonical input model for the R&D deduction document package.

This module owns JSON normalization only: aliases, defaults, structural
guards and derived projections.  Semantic *shape* rules (required fields,
topic count, date order, Hxx format/uniqueness/continuity, page references,
path existence) live in the executable specification ``templates/rules.json``
and are enforced by ``scripts/rule_engine.py`` — swap that file to serve a
different business.  Rules requiring content understanding stay in
``references/rules.md`` and are executed by the model, not by code.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping

try:
    from .rule_engine import load_rules, run_stage
except ImportError:  # Running as a flat module inside scripts/.
    from rule_engine import load_rules, run_stage  # type: ignore[no-redef]

BULLET_COLLECTION_FIELDS = (
    "difficulties",
    "uncertainties",
    "company_advantages",
    "personnel_advantages",
    "actual_results",
    "innovation_points",
    "application_results",
)


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "；".join(as_text(item) for item in value)
    if isinstance(value, dict):
        return "；".join(f"{key}：{as_text(item)}" for key, item in value.items())
    return str(value)


def first(data: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return default


def _first_text(data: Mapping[str, Any], *keys: str, default: str = "") -> str:
    return as_text(first(data, *keys, default=default))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _list_of_mappings(data: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    value = data.get(field)
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{field} must be a list of objects")
    return value


def _required(data: Mapping[str, Any], field: str) -> Any:
    value = data.get(field)
    if value in (None, "", []):
        raise ValueError(f"JSON must contain {field}; use an Hxx placeholder when unknown")
    return value


def _required_list(data: Mapping[str, Any], field: str) -> list[Any]:
    value = _required(data, field)
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _extra(data: Mapping[str, Any], model_type: type) -> dict[str, Any]:
    known = {item.name for item in fields(model_type)}
    return {key: value for key, value in data.items() if key not in known}


@dataclass(frozen=True)
class ImageReference:
    path: str
    caption: str = ""

    @classmethod
    def from_value(cls, value: Any, label: str) -> "ImageReference":
        if isinstance(value, Mapping):
            path = _first_text(value, "path")
            caption = _first_text(value, "caption")
        else:
            path = as_text(value)
            caption = ""
        if not path:
            raise ValueError(f"{label} must contain path")
        return cls(path=path, caption=caption)

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "caption": self.caption}


@dataclass(frozen=True)
class Topic:
    title: str
    existing_problem: str
    research_objective: str
    research_content: str
    variables: str
    verification: str
    expected_effect: str
    images: tuple[ImageReference, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, index: int) -> "Topic":
        data = _mapping(value, f"topics[{index}]")
        aliases = {
            "title": ("title",),
            "existing_problem": ("existing_problem", "problem"),
            "research_objective": ("research_objective", "goal"),
            "research_content": ("research_content", "approach"),
            "variables": ("variables", "parameters"),
            "verification": ("verification", "validation"),
            "expected_effect": ("expected_effect", "effect"),
        }
        values = {}
        for field_name, names in aliases.items():
            values[field_name] = _first_text(data, *names)
            if not values[field_name]:
                raise ValueError(
                    f"topics[{index}] must contain {field_name}; use an Hxx placeholder when unknown"
                )
        images_value = data.get("images") or []
        if not isinstance(images_value, list):
            raise ValueError(f"topics[{index}].images must be a list")
        images = tuple(
            ImageReference.from_value(item, f"topics[{index}].images[{image_index}]")
            for image_index, item in enumerate(images_value)
        )
        values["images"] = images
        values["extra"] = {
            key: item
            for key, item in data.items()
            if key not in {name for names in aliases.values() for name in names} | {"images"}
        }
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.extra)
        result.update(
            {
                "title": self.title,
                "existing_problem": self.existing_problem,
                "research_objective": self.research_objective,
                "research_content": self.research_content,
                "variables": self.variables,
                "verification": self.verification,
                "expected_effect": self.expected_effect,
                "images": [item.to_dict() for item in self.images],
            }
        )
        return result


@dataclass(frozen=True)
class ScheduleItem:
    time: str
    stage: str = ""
    content: str = ""
    output: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, index: int) -> "ScheduleItem":
        data = _mapping(value, f"schedule[{index}]")
        return cls(
            time=_first_text(data, "time", "planned_time"),
            stage=_first_text(data, "stage"),
            content=_first_text(data, "content", "research_content"),
            output=_first_text(data, "output", "deliverable"),
            extra={
                key: item
                for key, item in data.items()
                if key not in {"time", "planned_time", "stage", "content", "research_content", "output", "deliverable"}
            },
        )

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.extra)
        result.update({"time": self.time, "stage": self.stage, "content": self.content, "output": self.output})
        return result


@dataclass(frozen=True)
class PersonnelItem:
    name: str
    department: str = ""
    responsibility: str = ""
    work_content: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, index: int) -> "PersonnelItem":
        data = _mapping(value, f"personnel[{index}]")
        return cls(
            name=_first_text(data, "name"),
            department=_first_text(data, "department", "role"),
            responsibility=_first_text(data, "responsibility", "work"),
            work_content=_first_text(data, "work_content"),
            extra={
                key: item
                for key, item in data.items()
                if key not in {"name", "department", "role", "responsibility", "work", "work_content"}
            },
        )

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.extra)
        result.update(
            {
                "name": self.name,
                "department": self.department,
                "responsibility": self.responsibility,
                "work_content": self.work_content,
            }
        )
        return result


@dataclass(frozen=True)
class BudgetItem:
    category: str
    amount: Any = ""
    purpose: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, index: int) -> "BudgetItem":
        data = _mapping(value, f"budget_items[{index}]")
        return cls(
            category=_first_text(data, "category", "type"),
            amount=data.get("amount", ""),
            purpose=_first_text(data, "purpose", "usage"),
            extra={
                key: item
                for key, item in data.items()
                if key not in {"category", "type", "amount", "purpose", "usage"}
            },
        )

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.extra)
        result.update({"category": self.category, "amount": self.amount, "purpose": self.purpose})
        return result


@dataclass(frozen=True)
class TechnicalIndicator:
    name: str
    target: Any = ""
    actual: Any = ""
    evidence: Any = ""
    date: Any = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, index: int) -> "TechnicalIndicator":
        data = _mapping(value, f"technical_indicators[{index}]")
        return cls(
            name=_first_text(data, "name"),
            target=data.get("target", ""),
            actual=data.get("actual", ""),
            evidence=data.get("evidence", ""),
            date=data.get("date", ""),
            extra={key: item for key, item in data.items() if key not in {"name", "target", "actual", "evidence", "date"}},
        )

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.extra)
        result.update(
            {"name": self.name, "target": self.target, "actual": self.actual, "evidence": self.evidence, "date": self.date}
        )
        return result


@dataclass(frozen=True)
class IntellectualProperty:
    name: str
    number: Any = ""
    date: Any = ""
    status: Any = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, index: int) -> "IntellectualProperty":
        data = _mapping(value, f"intellectual_property[{index}]")
        return cls(
            name=_first_text(data, "name"),
            number=data.get("number", ""),
            date=data.get("date", ""),
            status=data.get("status", ""),
            extra={key: item for key, item in data.items() if key not in {"name", "number", "date", "status"}},
        )

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.extra)
        result.update({"name": self.name, "number": self.number, "date": self.date, "status": self.status})
        return result


@dataclass(frozen=True)
class Supplement:
    id: str
    channel: str = "word"
    pages: Any = ""
    location: str = ""
    placeholder: str = ""
    request: str = ""
    format: str = ""
    owner: str = ""
    priority: str = "中"
    status: str = "未填写"
    note: str = ""
    documents: str = ""
    gap: str = ""
    suggested_material: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, index: int) -> "Supplement":
        data = _mapping(value, f"supplements[{index}]")
        channel = _first_text(data, "channel", default="word")
        if channel not in {"word", "list"}:
            raise ValueError(f"supplements[{index}].channel must be 'word' or 'list'")
        return cls(
            id=as_text(data.get("id")),
            channel=channel,
            pages=data.get("pages", ""),
            location=_first_text(data, "location"),
            placeholder=_first_text(data, "placeholder"),
            request=_first_text(data, "request", "what_to_provide"),
            format=_first_text(data, "format"),
            owner=_first_text(data, "owner", "department"),
            priority=_first_text(data, "priority", default="中"),
            status=_first_text(data, "status", default="未填写"),
            note=_first_text(data, "note"),
            documents=_first_text(data, "documents"),
            gap=_first_text(data, "gap"),
            suggested_material=_first_text(data, "suggested_material"),
            extra={
                key: item
                for key, item in data.items()
                if key
                not in {
                    "id",
                    "channel",
                    "pages",
                    "location",
                    "placeholder",
                    "request",
                    "what_to_provide",
                    "format",
                    "owner",
                    "department",
                    "priority",
                    "status",
                    "note",
                    "documents",
                    "gap",
                    "suggested_material",
                }
            },
        )

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.extra)
        result.update(
            {
                "id": self.id,
                "channel": self.channel,
                "pages": self.pages,
                "location": self.location,
                "placeholder": self.placeholder,
                "request": self.request,
                "format": self.format,
                "owner": self.owner,
                "priority": self.priority,
                "status": self.status,
                "note": self.note,
                "documents": self.documents,
                "gap": self.gap,
                "suggested_material": self.suggested_material,
            }
        )
        return result


@dataclass(frozen=True)
class RDProjectData:
    project_name: str
    company_name: str
    period: str
    leader: str
    decision_maker: str
    decision_date: str
    plan_date: str
    outcome_date: str
    background: Any
    objective: Any
    difficulties: Any
    uncertainties: Any
    company_advantages: Any
    personnel_advantages: Any
    purpose: Any
    technical_indicators: tuple[TechnicalIndicator, ...]
    actual_results: Any
    innovation_points: Any
    social_benefits: Any
    economic_benefits: Any
    application_results: Any
    topics: tuple[Topic, ...]
    schedule: tuple[ScheduleItem, ...]
    personnel: tuple[PersonnelItem, ...]
    budget_items: tuple[BudgetItem, ...]
    intellectual_property: tuple[IntellectualProperty, ...]
    supplements: tuple[Supplement, ...]
    funding_source: Any = ""
    actual_start_date: str = ""
    actual_end_date: str = ""
    objectives: tuple[Any, ...] | None = None
    research_content: Any = ""
    budget_summary: Any = ""
    budget: Any = ""
    expected_results: Any = ""
    result_ownership: Any = ""
    result_images: tuple[ImageReference, ...] = ()
    source_manifest: tuple[Mapping[str, Any], ...] = ()
    unified_elements: tuple[Mapping[str, Any], ...] = ()
    facts: tuple[Mapping[str, Any], ...] = ()
    projection_matrix: tuple[Mapping[str, Any], ...] = ()
    consistency_checks: tuple[Mapping[str, Any], ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        value: Any,
        rules: Mapping[str, Any] | None = None,
        *,
        validate_rules: bool = True,
    ) -> "RDProjectData":
        if not isinstance(value, Mapping):
            raise ValueError("Input JSON root must be an object")
        rules = rules if rules is not None else load_rules()
        if validate_rules:
            run_stage(value, rules, "input")

        # 结构守卫：保证归一化不崩溃的最小类型检查；语义校验在归一化后由规则引擎执行。
        for field_name in BULLET_COLLECTION_FIELDS:
            _required_list(value, field_name)

        topics_value = value.get("topics") or []
        if not isinstance(topics_value, list) or any(not isinstance(item, Mapping) for item in topics_value):
            raise ValueError("topics must be a list of objects")

        topics = tuple(Topic.from_dict(item, index) for index, item in enumerate(topics_value, start=1))
        schedule = tuple(ScheduleItem.from_dict(item, index) for index, item in enumerate(_list_of_mappings(value, "schedule"), start=1))
        personnel = tuple(PersonnelItem.from_dict(item, index) for index, item in enumerate(_list_of_mappings(value, "personnel"), start=1))
        budget_items = tuple(BudgetItem.from_dict(item, index) for index, item in enumerate(_list_of_mappings(value, "budget_items"), start=1))
        technical_indicators = tuple(TechnicalIndicator.from_dict(item, index) for index, item in enumerate(_list_of_mappings(value, "technical_indicators"), start=1))
        intellectual_property = tuple(IntellectualProperty.from_dict(item, index) for index, item in enumerate(_list_of_mappings(value, "intellectual_property"), start=1))
        supplements_value = value["supplements"] if "supplements" in value else []
        if not isinstance(supplements_value, list) or any(not isinstance(item, Mapping) for item in supplements_value):
            raise ValueError("supplements must be a list of objects")
        supplements = tuple(Supplement.from_dict(item, index) for index, item in enumerate(supplements_value, start=1))

        result_images_value = value.get("result_images") or []
        if not isinstance(result_images_value, list):
            raise ValueError("result_images must be a list")
        result_images = tuple(
            ImageReference.from_value(item, f"result_images[{index}]")
            for index, item in enumerate(result_images_value)
        )

        if "objectives" not in value:
            objectives = None
        elif not isinstance(value["objectives"], list):
            raise ValueError("objectives must be a list")
        else:
            objectives = tuple(value["objectives"])

        actual_start_date = _first_text(value, "actual_start_date", "research_start_date")
        actual_end_date = _first_text(value, "actual_end_date", "research_end_date")

        result = cls(
            project_name=_first_text(value, "project_name"),
            company_name=_first_text(value, "company_name"),
            period=_first_text(value, "period"),
            leader=_first_text(value, "leader"),
            decision_maker=_first_text(value, "decision_maker"),
            decision_date=_first_text(value, "decision_date"),
            plan_date=_first_text(value, "plan_date"),
            outcome_date=_first_text(value, "outcome_date"),
            background=value["background"],
            objective=value["objective"],
            difficulties=value["difficulties"],
            uncertainties=value["uncertainties"],
            company_advantages=value["company_advantages"],
            personnel_advantages=value["personnel_advantages"],
            purpose=value["purpose"],
            technical_indicators=technical_indicators,
            actual_results=value["actual_results"],
            innovation_points=value["innovation_points"],
            social_benefits=value["social_benefits"],
            economic_benefits=value["economic_benefits"],
            application_results=value["application_results"],
            topics=topics,
            schedule=schedule,
            personnel=personnel,
            budget_items=budget_items,
            intellectual_property=intellectual_property,
            supplements=supplements,
            funding_source=first(value, "funding_source", default=""),
            actual_start_date=actual_start_date,
            actual_end_date=actual_end_date,
            objectives=objectives,
            research_content=first(value, "research_content", default=""),
            budget_summary=first(value, "budget_summary", default=""),
            budget=first(value, "budget", default=""),
            expected_results=first(value, "expected_results", default=""),
            result_ownership=first(value, "result_ownership", "undertaking_unit", default=""),
            result_images=result_images,
            source_manifest=tuple(_list_of_mappings(value, "source_manifest")) if "source_manifest" in value else (),
            unified_elements=tuple(_list_of_mappings(value, "unified_elements")) if "unified_elements" in value else (),
            facts=tuple(_list_of_mappings(value, "facts")) if "facts" in value else (),
            projection_matrix=tuple(_list_of_mappings(value, "projection_matrix")) if "projection_matrix" in value else (),
            consistency_checks=tuple(_list_of_mappings(value, "consistency_checks")) if "consistency_checks" in value else (),
            extra=_extra(value, cls),
        )
        if validate_rules:
            run_stage(result.to_dict(rules), rules, "model")
        return result

    def to_dict(self, rules: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if rules is None:
            rules = load_rules()
        result = dict(self.extra)
        supplements = [item.to_dict() for item in self.supplements]
        result.update(
            {
                "project_name": self.project_name,
                "company_name": self.company_name,
                "period": self.period,
                "leader": self.leader,
                "decision_maker": self.decision_maker,
                "decision_date": self.decision_date,
                "plan_date": self.plan_date,
                "outcome_date": self.outcome_date,
                "background": _json_value(self.background),
                "objective": _json_value(self.objective),
                "difficulties": _json_value(self.difficulties),
                "uncertainties": _json_value(self.uncertainties),
                "company_advantages": _json_value(self.company_advantages),
                "personnel_advantages": _json_value(self.personnel_advantages),
                "purpose": _json_value(self.purpose),
                "technical_indicators": [item.to_dict() for item in self.technical_indicators],
                "actual_results": _json_value(self.actual_results),
                "innovation_points": _json_value(self.innovation_points),
                "social_benefits": _json_value(self.social_benefits),
                "economic_benefits": _json_value(self.economic_benefits),
                "application_results": _json_value(self.application_results),
                "topics": [item.to_dict() for item in self.topics],
                "schedule": [item.to_dict() for item in self.schedule],
                "personnel": [item.to_dict() for item in self.personnel],
                "budget_items": [item.to_dict() for item in self.budget_items],
                "intellectual_property": [item.to_dict() for item in self.intellectual_property],
                "supplements": supplements,
                "word_supplements": [item for item in supplements if item.get("channel", "word") == "word"],
                "funding_source": _json_value(self.funding_source),
                "actual_start_date": self.actual_start_date,
                "actual_end_date": self.actual_end_date,
                "objectives": _json_value(self.objectives),
                "research_content": _json_value(self.research_content),
                "budget_summary": _json_value(self.budget_summary),
                "budget": _json_value(self.budget),
                "expected_results": _json_value(self.expected_results),
                "result_ownership": _json_value(self.result_ownership),
                "result_images": [item.to_dict() for item in self.result_images],
                "source_manifest": _json_value(self.source_manifest),
                "unified_elements": _json_value(self.unified_elements),
                "facts": _json_value(self.facts),
                "projection_matrix": _json_value(self.projection_matrix),
                "consistency_checks": _json_value(self.consistency_checks),
                "unified_element_rows": self.unified_element_rows(rules),
                "consistency_rows": self.consistency_rows(rules),
            }
        )
        return result

    def unified_element_rows(self, rules: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """统一研发活动要素工作表行：规则文件中的固定要素枚举与输入合并。"""
        if rules is None:
            rules = load_rules()
        provided = {as_text(item.get("name")): item for item in self.unified_elements}
        rows = []
        for index, name in enumerate(rules.get("fixed_elements", {}).get("items", ()), start=1):
            item = provided.get(name, {})
            rows.append(
                {
                    "id": as_text(item.get("id", f"E{index:02d}")),
                    "name": name,
                    "value": item.get("value", ""),
                    "status": as_text(item.get("status", "待补信息")),
                    "source_id": as_text(item.get("source_id", "")),
                    "source_location": as_text(item.get("source_location", "")),
                    "placeholder": as_text(item.get("placeholder", "")),
                    "note": as_text(item.get("note", "")),
                }
            )
        return rows

    def consistency_rows(self, rules: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """一致性核对工作表行：规则文件中的固定核对项枚举与输入合并。"""
        if rules is None:
            rules = load_rules()
        provided = {as_text(item.get("item")): item for item in self.consistency_checks}
        rows = []
        for item_name in rules.get("fixed_consistency_items", {}).get("items", ()):
            item = provided.get(item_name, {})
            rows.append(
                {
                    "item": item_name,
                    "decision": as_text(item.get("decision", "")),
                    "plan": as_text(item.get("plan", "")),
                    "outcome": as_text(item.get("outcome", "")),
                    "source": as_text(item.get("source", "")),
                    "consistent": as_text(item.get("consistent", "")),
                    "reference": as_text(item.get("reference", "")),
                    "action": as_text(item.get("action", "")),
                }
            )
        return rows

    def derived_context(self) -> dict[str, Any]:
        """DOCX 渲染所需的派生值：摘要回退、归属回退和图片路径选择。

        渲染脚本只负责把 ``*_path`` 包装为 InlineImage，不得再做业务推导。
        """
        topics = []
        for topic in self.topics:
            value = topic.to_dict()
            image = value["images"][0] if value.get("images") else None
            value["image_path"] = image["path"] if image else ""
            value["caption"] = image.get("caption", "") if image else ""
            topics.append(value)
        result_item = self.result_images[0] if self.result_images else None
        return {
            "objectives": [as_text(self.objective)] if self.objectives is None else [as_text(item) for item in self.objectives],
            "research_content_summary": as_text(self.research_content)
            or "；".join(topic.research_content for topic in self.topics),
            "budget_summary": as_text(self.budget_summary or self.budget)
            or "；".join(f"{item.category}：{item.amount}" for item in self.budget_items),
            "expected_results": as_text(self.expected_results)
            or "；".join(topic.expected_effect for topic in self.topics),
            "result_ownership": as_text(self.result_ownership) or self.company_name,
            "result_image_path": result_item.path if result_item else "",
            "result_caption": result_item.caption if result_item else "",
            "topics": topics,
        }


def ensure_project(data: RDProjectData | Mapping[str, Any], rules: Mapping[str, Any] | None = None) -> RDProjectData:
    if isinstance(data, RDProjectData):
        return data
    return RDProjectData.from_dict(data, rules)


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize an R&D deduction facts JSON file.")
    parser.add_argument("--input", required=True, type=Path, help="raw facts JSON")
    parser.add_argument("--rules", type=Path, help="rules JSON; defaults to templates/rules.json")
    parser.add_argument("--output", required=True, type=Path, help="normalized projection JSON")
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        rules = load_rules(args.rules)
        project = RDProjectData.from_dict(raw, rules, validate_rules=False)
        projection = project.to_dict(rules)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(projection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"ok": True, "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
