#!/usr/bin/env python3
"""Pin a review package for a fresh-context reviewer.

create: snapshot in-scope working-tree files (SHA-256), write review.diff
        against an exact baseline (including untracked files), and emit a
        dispatch scaffold with the machine-pinned fields filled in.
verify: recompute hashes against snapshot.json and report drift.

Stdlib only. Requires git on PATH.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import datetime
from pathlib import Path

SCHEMA_VERSION = 1


def run_git(repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",  # target repos may hold non-UTF-8 text (GBK/Latin-1); never crash on decode
    )
    if check and proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def resolve_commit(repo: Path, ref: str) -> str:
    return run_git(repo, ["rev-parse", "--verify", f"{ref}^{{commit}}"]).stdout.strip()


def in_scope(rel: str, scopes: list[str]) -> bool:
    if not scopes:
        return True
    for scope in scopes:
        scope = scope.rstrip("/")
        if rel == scope or rel.startswith(scope + "/"):
            return True
    return False


def collect_files(repo: Path, baseline: str, scopes: list[str]) -> list[dict]:
    # -z: NUL-separated raw paths, no core.quotepath octal escaping of non-ASCII names
    tracked = run_git(repo, ["diff", "--name-only", "-z", baseline, "--"]).stdout.split("\0")
    untracked = run_git(repo, ["ls-files", "--others", "--exclude-standard", "-z"]).stdout.split("\0")
    tracked_set = {p for p in tracked if p}
    untracked_set = {p for p in untracked if p}
    entries: list[dict] = []
    for rel in sorted(tracked_set | untracked_set):
        if not in_scope(rel, scopes):
            continue
        target = repo / rel
        if not target.is_file():
            entries.append({"path": rel, "status": "deleted", "sha256": None})
            continue
        status = "untracked" if rel in untracked_set else "modified-or-new"
        entries.append({"path": rel, "status": status, "sha256": sha256_file(target)})
    return entries


def scope_sha256(entries: list[dict]) -> str:
    lines = [f"{e['path']}:{e['sha256'] or 'DELETED'}" for e in entries]
    return sha256_bytes("\n".join(sorted(lines)).encode("utf-8"))


def build_diff(repo: Path, baseline: str, entries: list[dict]) -> str:
    tracked_paths = [e["path"] for e in entries if e["status"] != "untracked"]
    parts: list[str] = []
    if tracked_paths:
        parts.append(run_git(repo, ["-c", "core.quotepath=false", "diff", "--binary", "--full-index", baseline, "--", *tracked_paths]).stdout)
    for e in entries:
        if e["status"] != "untracked":
            continue
        proc = run_git(repo, ["-c", "core.quotepath=false", "diff", "--no-index", "--", os.devnull, e["path"]], check=False)
        if proc.returncode not in (0, 1):  # 1 = differences found, expected
            raise SystemExit(f"git diff --no-index failed for {e['path']}: {proc.stderr.strip()}")
        parts.append(proc.stdout)
    return "".join(parts)


def write_scaffold(out: Path, snapshot_path: Path, diff_path: Path, snapshot: dict, diff_sha256: str) -> Path:
    script = Path(__file__).resolve()
    scaffold = f"""你是新鲜上下文的独立评审者，按 code-review 纪律评审，不是实现者。

## 目标与验收标准
[REQUIRED: 填写目标与验收标准原文或引用位置]

## 精确范围（已钉死，不是浮动 HEAD）
- 仓库：{snapshot['repo']}
- 精确基线：{snapshot['baseline']}
- 派遣时 HEAD：{snapshot['head']}
- 内容快照：{snapshot_path}（scopeSha256={snapshot['scopeSha256']}）
- scoped diff：{diff_path}（diffSha256={diff_sha256}）
- 复核快照无漂移：`python3 {script} verify --snapshot {snapshot_path}`

## 权威断言与既有证据
[REQUIRED: 变更所涉 spec/design 路径（含章节）与验证记录位置；没有则写明无]

## 前轮评审记录
[REQUIRED: 第 2 轮起填前轮报告路径与哈希；首轮填「无」]

## 默认边界
不改生产代码、测试或上下文文档；不 commit/push；不再委派子代理；不操作共享服务与无关容器。
[OPTIONAL: 项目特定边界，如禁止 install/pull 镜像]

## 产出
逐维度「已查 + 结论 + 证据」，报告开头给三面摘要（完整性/正确性/一致性），发现分级与裁决按 code-review 第 3 步；完整报告写入本目录 review-report.md，独立核验记录追加到 [REQUIRED: issue 验证记录路径；无 issue 则写「报告即记录」]。
"""
    path = out / "dispatch-scaffold.md"
    path.write_text(scaffold, encoding="utf-8")
    return path


def cmd_create(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    baseline = resolve_commit(repo, args.baseline)
    head = resolve_commit(repo, "HEAD")
    entries = collect_files(repo, baseline, args.path or [])
    if not entries:
        print("no in-scope files changed against baseline", file=sys.stderr)
        return 2
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "schemaVersion": SCHEMA_VERSION,
        "repo": str(repo),
        "baseline": baseline,
        "head": head,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scopes": args.path or [],
        "scopeSha256": scope_sha256(entries),
        "files": entries,
    }
    snapshot_path = out / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    diff_text = build_diff(repo, baseline, entries)
    diff_path = out / "review.diff"
    diff_path.write_text(diff_text, encoding="utf-8")
    diff_digest = sha256_bytes(diff_text.encode("utf-8"))
    scaffold_path = write_scaffold(out, snapshot_path, diff_path, snapshot, diff_digest)
    print(json.dumps({
        "snapshot": str(snapshot_path),
        "diff": str(diff_path),
        "diffSha256": diff_digest,
        "scaffold": str(scaffold_path),
        "files": len(entries),
        "scopeSha256": snapshot["scopeSha256"],
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    snapshot_path = Path(args.snapshot).resolve()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    repo = Path(snapshot["repo"])
    # Re-collect within the recorded scopes so post-dispatch additions are caught too.
    current_entries = collect_files(repo, snapshot["baseline"], snapshot.get("scopes", []))
    expected = {e["path"]: e["sha256"] for e in snapshot["files"]}
    current = {e["path"]: e["sha256"] for e in current_entries}
    added = sorted(set(current) - set(expected))
    removed = sorted(set(expected) - set(current))
    changed = sorted(p for p in set(expected) & set(current) if expected[p] != current[p])
    drift = added + removed + changed
    drifted = bool(drift) or scope_sha256(current_entries) != snapshot["scopeSha256"]
    result = "stale" if drifted else "current"
    print(json.dumps({"snapshot": str(snapshot_path), "result": result,
                      "added": added, "removed": removed, "changed": changed},
                     indent=2, ensure_ascii=False))
    return 1 if drifted else 0


def main_with(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_create = sub.add_parser("create", help="pin snapshot + diff + dispatch scaffold")
    p_create.add_argument("--repo", default=".", help="repository root (default: cwd)")
    p_create.add_argument("--baseline", required=True, help="exact baseline commit")
    p_create.add_argument("--path", action="append", help="scope path (repeatable); default: all changes vs baseline")
    p_create.add_argument("--out", required=True, help="output directory for the review package")
    p_create.set_defaults(func=cmd_create)
    p_verify = sub.add_parser("verify", help="recompute hashes and report drift")
    p_verify.add_argument("--snapshot", required=True, help="path to snapshot.json")
    p_verify.set_defaults(func=cmd_verify)
    args = parser.parse_args(argv)
    return args.func(args)


def main() -> int:
    return main_with(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
