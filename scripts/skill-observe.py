#!/usr/bin/env python3
# skill-observe.py — Codex hook 观测脚本（机制层）
#
# 设计来源：.agents/skills/skill-iteration-review/references/harness.md
# 职责边界：只写原始事件行（JSONL），语义归因归 skill-iteration-review 取证时完成。
# 铁律：永不向 stdout 输出（避免注入上下文改变模型行为），永不非零退出（hook 失败会干扰会话）。
#
# 事件：session.start / session.end / prompt.submit / skill.file（op=read|write）
# 日志落点：工作区根目录 skill-事件日志.jsonl（可用 SKILL_OBSERVE_LOG 覆盖，供测试用）。

import json
import os
import re
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)
LOG_PATH = os.environ.get("SKILL_OBSERVE_LOG") or os.path.join(WORKSPACE, "skill-事件日志.jsonl")

INSTALLED_ROOT = os.path.join(os.path.expanduser("~"), ".agents", "skills")
SOURCE_ROOT = os.path.join(WORKSPACE, "skills")

MAX_SNIPPET = 500    # 命令片段截断
MAX_PROMPT = 4000    # prompt 原文截断

# 形如 …/skills/<name>/SKILL.md 的路径（含相对路径），不含反引号/引号/空白
SKILL_PATH_RE = re.compile(r"[^\s\"'`(]*skills/([^/\s\"'`(]+)/SKILL\.md")
# Bash 命令里的写入迹象（粗判据；原始命令随行保留，取证时可重判）
WRITE_HINT_RE = re.compile(r"sed\s+-i|\btee\b|\b(mv|cp|rm)\s|>>?")


def emit(obj):
    try:
        obj["ts"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except OSError:
        pass


def scope_of(path):
    ap = os.path.abspath(os.path.expanduser(path))
    if ap.startswith(INSTALLED_ROOT + os.sep):
        return "installed"
    if ap.startswith(SOURCE_ROOT + os.sep):
        return "source"
    return "other"


def base(event, data):
    obj = {"event": event}
    for k, out in (("session_id", "session"), ("turn_id", "turn"), ("model", "model"), ("cwd", "cwd")):
        v = data.get(k)
        if v:
            obj[out] = v
    return obj


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    # 快路径：工具事件与 skill 文件无关时直接退出，不解析 JSON
    if '"PostToolUse"' in raw or '"PreToolUse"' in raw:
        if "SKILL.md" not in raw:
            return
    try:
        data = json.loads(raw)
    except ValueError:
        return
    if not isinstance(data, dict):
        return

    event = data.get("hook_event_name")

    if event == "SessionStart":
        obj = base("session.start", data)
        obj["source"] = data.get("source")
        emit(obj)

    elif event == "SessionEnd":
        obj = base("session.end", data)
        obj["reason"] = data.get("reason")
        emit(obj)

    elif event == "UserPromptSubmit":
        obj = base("prompt.submit", data)
        prompt = data.get("prompt")
        if isinstance(prompt, str):
            obj["prompt"] = prompt[:MAX_PROMPT]
        emit(obj)

    elif event == "PostToolUse":
        tool = data.get("tool_name")
        inp = data.get("tool_input")
        text = ""
        if isinstance(inp, dict):
            text = str(inp.get("command") or "")
        if not text:
            return
        seen = set()
        for m in SKILL_PATH_RE.finditer(text):
            path, name = m.group(0), m.group(1)
            if (path, name) in seen:
                continue
            seen.add((path, name))
            if tool == "apply_patch":
                op = "write"
            else:
                op = "write" if WRITE_HINT_RE.search(text) else "read"
            obj = base("skill.file", data)
            obj.update({
                "skill": name,
                "path": path,
                "scope": scope_of(path),
                "op": op,
                "tool": tool,
                "command": text[:MAX_SNIPPET],
            })
            emit(obj)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
