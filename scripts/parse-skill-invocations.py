#!/usr/bin/env python3
# parse-skill-invocations.py — 从 SKILL.md 正文抽取调用依赖（skill/tool/mcp/shell）
#
# 规范：skills/skill-creator/references/invocation-markers.md v0.2
# 职责边界：只抽取。不匹配严格形态的标记静默不抽取；符合性判断留作者自查与 review。
#
# 用法：
#   parse-skill-invocations.py FILE...   解析并输出 JSON（单文件出对象，多文件出列表）
#   parse-skill-invocations.py --all     解析仓库 skills/*/SKILL.md

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent

USE_SKILL_RE = re.compile(r"<use-skill\s*>\s*([^<]+?)\s*</use-skill\s*>")
TOOL_RE = re.compile(r"<tool\s*>\s*([^<]+?)\s*</tool\s*>")
MCP_RE = re.compile(r'<mcp\s+server="([^"]+)"\s+tool="([^"]+)"\s*>([^<]*)</mcp\s*>')

FENCE_OPEN_RE = re.compile(r"^\s*(`{3,})([^`]*)$")
INLINE_CODE_RE = re.compile(r"``[^`\n]*``|`[^`\n]*`")
MARKER_RE = re.compile(r"^#\s*invocation(\s+optional)?\s*$")

PREFIX_SKIP = {"sudo", "env", "time", "command", "builtin", "nice", "nohup"}
PREFIX_FLAG_ARG = {
    "sudo": {"-u", "-g", "-h", "--user", "--group", "--host"},
    "env": {"-u", "--unset"},
}
BUILTINS = {
    "cd", "export", "echo", "printf", "set", "unset", "local", "return", "exit",
    "eval", "exec", "source", ".", "alias", "unalias", "read", "shift", "trap",
    "true", "false", ":", "wait", "umask", "pushd", "popd", "dirs", "declare",
    "typeset", "readonly", "let", "test", "[", "[[", "{", "}", "if", "then",
    "else", "elif", "fi", "for", "while", "until", "do", "done", "case", "esac",
    "select", "function", "getopts", "jobs", "fg", "bg", "kill", "hash", "type",
    "ulimit", "break", "continue", "logout", "suspend", "times",
}


def extract_fences(text):
    """抽出 fenced code 块（支持 3+ 反引号嵌套），返回 (抹掉块的文本, 块列表）。"""
    lines = text.split("\n")
    out, blocks = [], []
    i = 0
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        n, info, start = len(m.group(1)), m.group(2).strip(), i + 1
        close_re = re.compile(rf"^\s*`{{{n},}}\s*$")
        body, j = [], i + 1
        while j < len(lines) and not close_re.match(lines[j]):
            body.append(lines[j])
            j += 1
        blocks.append({"info": info, "body": body, "line": start})
        consumed = (j - i + 1) if j < len(lines) else (j - i)
        out.extend([""] * consumed)
        i = j + 1 if j < len(lines) else j
    return "\n".join(out), blocks


def first_binary(seg):
    """一条命令段的首个外部 binary；无则 None。"""
    tokens = seg.strip().split()
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
            continue
        if t in PREFIX_SKIP:
            arg_flags = PREFIX_FLAG_ARG.get(t, set())
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                if tokens[i] in arg_flags:
                    i += 1
                i += 1
            continue
        break
    if i >= len(tokens):
        return None
    t = tokens[i]
    if t in BUILTINS or t.startswith(("$", "-")):
        return None
    if t.startswith(("./", "../", "/")):
        return Path(t).name or None
    return t


def parse_shell_block(body):
    """binary 列表。续行反斜杠合并；| 右侧不算；&&/||/; 分段各算。"""
    logical, buf = [], ""
    for raw in body:
        line = raw.rstrip()
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        logical.append(buf)
        buf = ""
    if buf.strip():
        logical.append(buf)
    deps = []
    for line in logical:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        for seg in re.split(r"&&|\|\||;", s):
            b = first_binary(seg)
            if b:
                deps.append(b)
    return deps


def parse_file(path):
    text = Path(path).read_text(encoding="utf-8")
    cleaned, blocks = extract_fences(text)

    shell, shell_opt = [], []
    for blk in blocks:
        if blk["info"] not in ("bash", "sh"):
            continue
        marker = next((ln for ln in blk["body"] if ln.strip()), None)
        m = MARKER_RE.match(marker.strip()) if marker else None
        if not m:
            continue
        deps = parse_shell_block(blk["body"][blk["body"].index(marker) + 1:])
        (shell_opt if m.group(1) else shell).extend(deps)

    cleaned = INLINE_CODE_RE.sub("", cleaned)
    return {
        "file": str(path),
        "requires": {
            "skills": sorted({m.group(1).strip() for m in USE_SKILL_RE.finditer(cleaned)}),
            "tools": sorted({m.group(1).strip() for m in TOOL_RE.finditer(cleaned)}),
            "mcp": [{"server": s, "tool": t}
                    for s, t in sorted({(m.group(1), m.group(2)) for m in MCP_RE.finditer(cleaned)})],
            "shell": sorted(set(shell)),
            "shell-optional": sorted(set(shell_opt)),
        },
    }


def main():
    ap = argparse.ArgumentParser(description="从 SKILL.md 正文抽取调用依赖（invocation-markers v0.2）")
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--all", action="store_true", help="解析仓库 skills/*/SKILL.md")
    args = ap.parse_args()

    files = sorted(WORKSPACE.glob("skills/*/SKILL.md")) if args.all else args.files
    if not files:
        ap.error("未指定 SKILL.md（或用 --all）")

    results = []
    for f in files:
        try:
            results.append(parse_file(f))
        except OSError as e:
            print(f"error: {f}: {e}", file=sys.stderr)
            sys.exit(2)

    print(json.dumps(results[0] if len(results) == 1 else results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
