#!/usr/bin/env python3
"""Run one real harness against an existing skill corpus and compare candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


CASE_RE = re.compile(
    r"^- \*\*(?P<id>[A-Za-z0-9_-]+)\*\*(?:（(?P<source>[^）]+)）)?[：:]`(?P<prompt>[^`]*)`"
)
ID_RE = re.compile(r"^- \*\*([A-Za-z0-9_-]+)\*\*")
OBSERVATIONS = {"passed", "failed", "not-observed"}


def _case_id(line: str) -> str | None:
    match = ID_RE.match(line)
    return match.group(1) if match else None


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        digest.update(b"missing")
        return digest.hexdigest()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_dir() and not path.is_symlink():
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8", "surrogateescape"))
        digest.update(b"\0")
        if path.is_file() and not path.is_symlink():
            digest.update(path.read_bytes())
        elif path.is_symlink():
            digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
        digest.update(b"\0")
    return digest.hexdigest()


def _parse_cases(corpus: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for line in corpus.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- **"):
            continue
        match = CASE_RE.match(line)
        if match is None or not match.group("source"):
            case_id = match.group("id") if match else _case_id(line)
            if not case_id:
                raise ValueError("unrecognized corpus format")
            raise ValueError(f"case {case_id} has no source marker")
        cases.append(
            {
                "id": match.group("id"),
                "source": match.group("source"),
                "prompt": match.group("prompt"),
            }
        )
    if not cases:
        raise ValueError("unrecognized corpus format")
    return cases


def _argv(value: str | None, label: str) -> list[str]:
    if not value:
        raise ValueError(f"{label} is required")
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) and item for item in parsed):
        raise ValueError(f"{label} must be a non-empty JSON string array")
    return parsed


def _candidates(values: list[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path:
            raise ValueError(f"candidate must be name=path: {value}")
        if name in found:
            raise ValueError(f"duplicate candidate: {name}")
        found[name] = Path(raw_path).expanduser()
    if not found:
        raise ValueError("at least one candidate is required")
    return found


def _trigger(path: Path) -> tuple[str, str | None]:
    if not path.is_file():
        return "unknown", None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "unknown", None
    if not isinstance(value, dict):
        return "unknown", None
    loaded = value.get("loadedSkillPath")
    if isinstance(loaded, str) and loaded:
        return "observed", loaded
    loaded_skills = value.get("loadedSkills")
    if isinstance(loaded_skills, list) and loaded_skills and isinstance(loaded_skills[0], str) and loaded_skills[0]:
        return "observed", loaded_skills[0]
    return "unknown", None


def _run_process(argv: list[str], stdin: str, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            input=stdin.encode("utf-8"),
            cwd=cwd,
            env=env,
            capture_output=True,
            shell=False,
            check=False,
        )
    except OSError as exc:
        return {
            "runStatus": "environment-blocked",
            "exitCode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }
    return {
        "runStatus": "completed" if completed.returncode == 0 else "task-failed",
        "exitCode": completed.returncode,
        "stdout": completed.stdout.decode("utf-8", "replace"),
        "stderr": completed.stderr.decode("utf-8", "replace"),
    }


def _observation(argv: list[str] | None, payload: dict[str, Any], cwd: Path) -> str:
    if not argv:
        return "not-observed"
    completed = _run_process(argv, json.dumps(payload, ensure_ascii=False), cwd, os.environ.copy())
    if completed["runStatus"] == "environment-blocked":
        return "environment-blocked"
    try:
        value = json.loads(completed["stdout"])
    except json.JSONDecodeError:
        return "not-observed"
    observation = value.get("observation") if isinstance(value, dict) else None
    if observation in OBSERVATIONS:
        return str(observation)
    return "not-observed"


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    cases = _parse_cases(args.corpus)
    by_id = {item["id"]: item for item in cases}
    selected = list(args.case) or [item["id"] for item in cases]
    missing = [item for item in selected if item not in by_id]
    if missing:
        raise ValueError(f"case {missing[0]} was not found")
    candidates = _candidates(args.candidate)
    if args.baseline not in candidates:
        raise ValueError("baseline must name one provided candidate")
    harness = _argv(args.harness_argv_json, "harness argv")
    judge = _argv(args.judge_argv_json, "judge argv") if args.judge_argv_json else None
    criteria = args.criteria.read_text(encoding="utf-8") if args.criteria else None
    names = list(candidates)
    order = names[:]
    if args.blind_seed is not None:
        random.Random(args.blind_seed).shuffle(order)
    labels = {name: chr(ord("A") + index) for index, name in enumerate(order)}
    hashes = {name: _tree_hash(path) for name, path in candidates.items()}

    report_candidates: dict[str, Any] = {
        name: {"contentHash": hashes[name], "label": labels[name], "runs": []} for name in names
    }
    report = {
        "schemaVersion": 1,
        "baseline": args.baseline,
        "model": args.model,
        "harnessArgv": harness,
        "coverage": {"selected": selected, "ran": []},
        "candidates": report_candidates,
        "blindMap": {label: name for name, label in labels.items()},
    }
    ran: list[str] = []
    with tempfile.TemporaryDirectory() as temp_name:
        work = Path(temp_name)
        for case_id in selected:
            ran.append(case_id)
            case = by_id[case_id]
            for name in names:
                label = labels[name]
                isolated = work / f"{label}-{case_id}"
                source = candidates[name]
                if source.is_dir():
                    shutil.copytree(source, isolated)
                else:
                    isolated.mkdir(parents=True, exist_ok=True)
                trace = work / "traces" / f"{label}-{case_id}.json"
                trace.parent.mkdir(parents=True, exist_ok=True)
                env = os.environ.copy()
                env["SKILL_EVAL_CANDIDATE_DIR"] = str(isolated)
                env["SKILL_EVAL_CASE_ID"] = case_id
                env["SKILL_EVAL_MODEL"] = args.model
                env["SKILL_EVAL_TRACE"] = str(trace)
                if source.is_dir():
                    completed = _run_process(harness, case["prompt"], isolated, env)
                else:
                    completed = {
                        "runStatus": "environment-blocked",
                        "exitCode": None,
                        "stdout": "",
                        "stderr": f"candidate tree is missing: {source}",
                    }
                trigger_status, trigger_path = _trigger(trace)
                durable_trace = None
                if trace.is_file():
                    durable = args.output.parent / f"{args.output.stem}.traces" / f"{label}-{case_id}.json"
                    durable.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(trace, durable)
                    durable_trace = str(durable)
                if completed["runStatus"] == "environment-blocked" or judge is None:
                    observation = "not-observed"
                else:
                    judge_payload = {
                        "caseId": case_id,
                        "label": label,
                        "output": completed["stdout"],
                    }
                    if criteria is not None:
                        judge_payload["criteria"] = criteria
                    observation = _observation(judge, judge_payload, work)
                report_candidates[name]["runs"].append(
                    {
                        "caseId": case_id,
                        "source": case["source"],
                        "input": case["prompt"],
                        "model": args.model,
                        "harnessArgv": harness,
                        "contentHash": hashes[name],
                        "runStatus": completed["runStatus"],
                        "exitCode": completed["exitCode"],
                        "stdout": completed["stdout"],
                        "stderr": completed["stderr"],
                        "triggerStatus": trigger_status,
                        "triggerPath": trigger_path,
                        "traceFile": durable_trace,
                        "observationStatus": observation,
                    }
                )
            report["coverage"]["ran"] = list(ran)
            _write_report(args.output, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--model", required=True)
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--criteria", type=Path)
    parser.add_argument("--blind-seed", type=int)
    parser.add_argument("--harness-argv-json")
    parser.add_argument("--judge-argv-json")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        report = evaluate(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"run_skill_eval: {exc}", file=sys.stderr)
        return 2
    _write_report(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
