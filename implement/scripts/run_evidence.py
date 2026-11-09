#!/usr/bin/env python3
"""Run one verification command and save content-bound evidence as JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ExecutionInterrupted(Exception):
    def __init__(self, signal_number: int):
        self.signal_number = signal_number


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _path_from_arg(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        candidate = Path(os.path.abspath(path))
    else:
        candidate = Path(os.path.abspath(root / path))
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"input path must be inside root: {value}") from exc
    return candidate


def _relative(path: Path, root: Path) -> str:
    return Path(path).resolve(strict=False).relative_to(Path(root).resolve()).as_posix()


def _is_excluded(relative: str, excludes: set[str]) -> bool:
    return any(relative == item or relative.startswith(item.rstrip("/") + "/") for item in excludes)


def _git_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise ValueError(f"default input scope requires a Git repository: {message}")
    return sorted({os.fsdecode(item) for item in result.stdout.split(b"\0") if item})


def _head(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _scope_files(root: Path, mode: str, paths: list[str], excludes: set[str]) -> list[str]:
    if mode == "git":
        candidates = _git_files(root)
    else:
        found: set[str] = set()
        for raw in paths:
            entry = _path_from_arg(raw, root)
            relative = _relative(entry, root)
            if entry.is_dir() and not entry.is_symlink():
                for child in entry.rglob("*"):
                    if child.is_dir() and not child.is_symlink():
                        continue
                    found.add(_relative(child, root))
            else:
                found.add(relative)
        candidates = sorted(found)
    return [
        item
        for item in candidates
        if item != ".git" and not item.startswith(".git/") and not _is_excluded(item, excludes)
    ]


def _fingerprint(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"state": "missing"}
    if path.is_symlink():
        return {"state": "present", "kind": "symlink", "target": os.readlink(path)}
    if path.is_file():
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            return {"state": "unreadable", "error": f"{type(exc).__name__}: {exc}"}
        return {"state": "present", "kind": "file", "size": metadata.st_size, "sha256": digest.hexdigest()}
    return {"state": "present", "kind": "other", "mode": metadata.st_mode}


def _snapshot(root: Path, mode: str, paths: list[str], excludes: set[str]) -> dict[str, Any]:
    names = _scope_files(root, mode, paths, excludes)
    return {
        "head": _head(root),
        "files": {name: _fingerprint(root / name) for name in names},
    }


def _changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    left = before.get("files", {})
    right = after.get("files", {})
    return sorted(name for name in set(left) | set(right) if left.get(name) != right.get(name))


def _stop_child(process: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
    def signal_tree(signal_number: int) -> None:
        try:
            if os.name == "posix":
                # The session can outlive its leader when a descendant still owns
                # stdout or stderr, so signal the group even after poll() succeeds.
                os.killpg(process.pid, signal_number)
            elif process.poll() is None:
                process.send_signal(signal_number)
        except ProcessLookupError:
            pass

    signal_tree(signal.SIGTERM)
    try:
        return process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        signal_tree(signal.SIGKILL)
        try:
            return process.communicate(timeout=1)
        except subprocess.TimeoutExpired as exc:
            # A descendant may have escaped the process group and kept a pipe
            # open. Do not let evidence collection wait forever for that pipe.
            stdout = exc.output or b""
            stderr = exc.stderr or b""
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            return stdout, stderr


def _decode(value: bytes | None) -> str:
    return (value or b"").decode("utf-8", "replace")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.replace(temporary, path)


def _artifact_record(value: str, root: Path) -> dict[str, Any]:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    path = Path(os.path.abspath(path))
    try:
        display = _relative(path, root)
    except ValueError:
        display = str(path)
    return {"path": display, **_fingerprint(path)}


def run_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    root = Path(args.root).expanduser().resolve()
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve(strict=False)
    cwd = Path(args.cwd).expanduser() if args.cwd else root
    if not cwd.is_absolute():
        cwd = root / cwd
    cwd = cwd.resolve(strict=False)
    argv = list(args.command)
    if argv and argv[0] == "--":
        argv.pop(0)
    if not argv:
        raise ValueError("provide a command after --")
    if args.timeout is not None and args.timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    output_exclude: set[str] = set()
    try:
        output_exclude.add(_relative(output, root))
    except ValueError:
        pass
    artifact_paths = [_path_from_arg(value, root) for value in args.artifact]
    output_exclude.update(_relative(path, root) for path in artifact_paths)
    extra_excludes = {_relative(_path_from_arg(value, root), root) for value in args.exclude_input}
    excludes = output_exclude | extra_excludes
    mode = "explicit" if args.input else "git"
    input_paths = args.input
    if mode == "explicit":
        for value in input_paths:
            _path_from_arg(value, root)

    started = _utc_now()
    start_monotonic = time.monotonic()
    try:
        before = _snapshot(root, mode, input_paths, excludes)
    except (OSError, ValueError) as exc:
        before = {"head": _head(root), "files": {}, "error": f"{type(exc).__name__}: {exc}"}

    run_result = "launch-failed"
    exit_code: int | None = None
    stdout = b""
    stderr = b""
    process: subprocess.Popen[bytes] | None = None
    old_handlers: dict[int, Any] = {}

    def interrupt_handler(signum: int, _frame: Any) -> None:
        raise ExecutionInterrupted(signum)

    for signal_number in (signal.SIGINT, signal.SIGTERM):
        try:
            old_handlers[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, interrupt_handler)
        except ValueError:
            pass

    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=os.name == "posix",
        )
        try:
            stdout, stderr = process.communicate(timeout=args.timeout)
            exit_code = process.returncode
            run_result = "passed" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            stdout, stderr = _stop_child(process)
            exit_code = process.returncode
            run_result = "timed-out"
        except ExecutionInterrupted as exc:
            stdout, stderr = _stop_child(process)
            exit_code = process.returncode
            run_result = "interrupted"
            interrupted_by = exc.signal_number
        except KeyboardInterrupt:
            stdout, stderr = _stop_child(process)
            exit_code = process.returncode
            run_result = "interrupted"
            interrupted_by = signal.SIGINT
    except OSError as exc:
        stderr = f"{type(exc).__name__}: {exc}".encode("utf-8", "replace")
    finally:
        for signal_number, handler in old_handlers.items():
            signal.signal(signal_number, handler)

    ended = _utc_now()
    try:
        after = _snapshot(root, mode, input_paths, excludes)
    except (OSError, ValueError) as exc:
        after = {"head": _head(root), "files": {}, "error": f"{type(exc).__name__}: {exc}"}
    changed_inputs = _changes(before, after)
    freshness = "unknown" if "error" in before or "error" in after else ("stale" if changed_inputs else "current")
    artifacts = [_artifact_record(value, root) for value in args.artifact]
    artifact_states = {item["state"] for item in artifacts}
    artifact_freshness = "missing" if "missing" in artifact_states else "unknown" if "unreadable" in artifact_states else "current"
    evidence: dict[str, Any] = {
        "schemaVersion": 1,
        "runId": str(uuid.uuid4()),
        "startedAtUtc": started,
        "endedAtUtc": ended,
        "durationSeconds": round(time.monotonic() - start_monotonic, 3),
        "command": {"argv": argv, "cwd": str(cwd)},
        "criteria": args.criterion,
        "timeoutSeconds": args.timeout,
        "runResult": run_result,
        "exitCode": exit_code,
        "stdout": _decode(stdout),
        "stderr": _decode(stderr),
        "inputScope": {"mode": mode, "paths": input_paths, "excluded": sorted(excludes)},
        "inputsBefore": before,
        "inputsAfter": after,
        "changedInputs": changed_inputs,
        "inputFreshness": freshness,
        "artifacts": artifacts,
        "artifactFreshness": artifact_freshness,
    }
    if run_result == "interrupted":
        evidence["interruptedBySignal"] = int(interrupted_by)
    _write_json(output, evidence)
    if run_result == "timed-out":
        return evidence, 124
    if run_result == "interrupted":
        return evidence, 128 + int(interrupted_by)
    return evidence, exit_code if run_result in {"passed", "failed"} and exit_code is not None else 127


def verify_evidence(root_arg: str, evidence_arg: str) -> tuple[dict[str, Any], int]:
    root = Path(root_arg).expanduser().resolve()
    evidence_path = Path(evidence_arg).expanduser()
    if not evidence_path.is_absolute():
        evidence_path = root / evidence_path
    record = json.loads(evidence_path.read_text(encoding="utf-8"))
    scope = record["inputScope"]
    excludes = set(scope.get("excluded", []))
    initial_freshness = record.get("inputFreshness", "unknown")
    try:
        current_inputs = _snapshot(root, scope["mode"], list(scope.get("paths", [])), excludes)
        expected_inputs = record["inputsAfter"]
        changed = _changes(expected_inputs, current_inputs)
        current_input_status = "stale" if changed else "current"
        if initial_freshness == "stale" or current_input_status == "stale":
            input_status = "stale"
        elif initial_freshness == "current":
            input_status = "current"
        else:
            input_status = "unknown"
    except (OSError, ValueError) as exc:
        changed = []
        current_inputs = {"error": f"{type(exc).__name__}: {exc}"}
        current_input_status = "unknown"
        input_status = "unknown"
    artifact_results: list[dict[str, Any]] = []
    for artifact in record.get("artifacts", []):
        artifact_path = Path(artifact["path"])
        if not artifact_path.is_absolute():
            artifact_path = root / artifact_path
        current = _fingerprint(artifact_path)
        artifact_results.append({"path": artifact["path"], "expected": artifact, "current": current, "matches": current == {key: value for key, value in artifact.items() if key != "path"}})
    artifacts_match = all(item["matches"] for item in artifact_results)
    status = "stale" if input_status == "stale" or not artifacts_match else input_status
    result = {
        "status": status,
        "initialInputFreshness": initial_freshness,
        "currentInputStatus": current_input_status,
        "inputStatus": input_status,
        "changedInputs": changed,
        "currentInputs": current_inputs,
        "artifactsMatch": artifacts_match,
        "artifacts": artifact_results,
    }
    return result, 0 if status == "current" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    run = subparsers.add_parser("run", help="run a command and write a JSON evidence file")
    run.add_argument("--root", type=Path, default=Path.cwd())
    run.add_argument("--cwd", type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--criterion", action="append", default=[])
    run.add_argument("--input", action="append", default=[], help="file or directory in the input scope; repeatable")
    run.add_argument("--exclude-input", action="append", default=[])
    run.add_argument("--artifact", action="append", default=[])
    run.add_argument("--timeout", type=float)
    run.add_argument("command", nargs=argparse.REMAINDER)
    verify = subparsers.add_parser("verify", help="compare recorded inputs and artifacts with current files")
    verify.add_argument("--root", type=Path, default=Path.cwd())
    verify.add_argument("evidence", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.action == "run":
            evidence, code = run_command(args)
            print(json.dumps({"runResult": evidence["runResult"], "inputFreshness": evidence["inputFreshness"], "evidence": str(args.output)}, ensure_ascii=False))
            return code
        result, code = verify_evidence(str(args.root), str(args.evidence))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"run_evidence: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
