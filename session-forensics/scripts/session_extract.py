#!/usr/bin/env python3
"""session_extract.py — agent 历史会话库只读提取（harness 适配器架构）。

子命令：
  list      列出会话（--since/--until YYYY-MM-DD，--directory 子串，--main-only）
  users     按序输出某会话的用户消息全文
  text      按序输出某会话的 assistant 可见文本（--max 每条截断，默认 1200）
  reasoning 按序输出某会话的 reasoning 部件（--max 同上；加密或不可读的只计数）
  tools     某会话的工具调用计数
  stats     聚合统计：会话数、消息类型计数、模型或版本分布

harness 选择：--harness opencode|codex；默认 auto——opencode 库在则 opencode，
不在而 codex 在则 codex，两家并存时 stderr 提示显式指定。
opencode 用 --db 覆盖库路径；codex 用 --root 覆盖 ~/.codex。

适配器即 drift 防护：存储格式与预期不符时大声失败并指向对应 reference，
不静默返回错误数据。新 harness：先核实格式落 references/<harness>-*.md，再加适配器。
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
CODEX_ROOT = Path.home() / ".codex"


def day_ms(date_str, end_of_day=False):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    if end_of_day:
        d += timedelta(days=1)
    return int(d.timestamp() * 1000)


# ---------------------------------------------------------------- opencode

class OpenCodeAdapter:
    """~/.local/share/opencode/opencode.db。结构依据 references/opencode-schema.md。"""

    name = "opencode"
    msg_label = "消息"
    REQUIRED = {
        "session_v2": {"id", "directory", "parent_id", "title", "model",
                       "time_created"},
        "session_message": {"session_id", "type", "seq", "data"},
    }

    def __init__(self, db):
        path = Path(db).expanduser()
        if not path.exists():
            raise SystemExit(f"库不存在: {path}")
        self.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self._guard_schema(path)

    def _guard_schema(self, path):
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table, cols in self.REQUIRED.items():
            if table not in tables:
                raise SystemExit(
                    f"{path} 缺表 {table}：schema 与适配器预期不符，"
                    "请 .schema 实查并更新 references/opencode-schema.md")
            have = {r[1] for r in self.conn.execute(
                f"PRAGMA table_info({table})")}
            missing = cols - have
            if missing:
                raise SystemExit(
                    f"{path} 表 {table} 缺列 {sorted(missing)}：schema 漂移，"
                    "请 .schema 实查并更新 references/opencode-schema.md")

    def sessions(self, since=None, until=None, directory=None,
                 main_only=False):
        sql = ("SELECT id, datetime(time_created/1000,'unixepoch','localtime'),"
               " directory, title, parent_id FROM session_v2 WHERE 1=1")
        args = []
        if since:
            sql += " AND time_created >= ?"
            args.append(day_ms(since))
        if until:
            sql += " AND time_created < ?"
            args.append(day_ms(until, end_of_day=True))
        if directory:
            sql += " AND directory LIKE ?"
            args.append(f"%{directory}%")
        if main_only:
            sql += " AND parent_id IS NULL"
        sql += " ORDER BY time_created"
        for sid, created, d, title, parent in self.conn.execute(sql, args):
            yield {"id": sid, "created": created, "directory": d,
                   "title": title or "", "parent": parent}

    def assert_session(self, session_id):
        row = self.conn.execute(
            "SELECT 1 FROM session_v2 WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise SystemExit(f"会话 {session_id} 不存在（id 须完整精确）")

    def _raw_messages(self, session_id, msg_type):
        sql = ("SELECT data FROM session_message WHERE session_id=? AND type=?"
               " ORDER BY seq")
        for r in self.conn.execute(sql, (session_id, msg_type)):
            yield json.loads(r[0])

    def user_texts(self, session_id):
        for msg in self._raw_messages(session_id, "user"):
            text = (msg.get("text") or "").strip()
            if text:
                yield text

    def _parts(self, session_id, part_type):
        for msg in self._raw_messages(session_id, "assistant"):
            for part in msg.get("content", []):
                if part.get("type") == part_type:
                    yield part

    def assistant_texts(self, session_id):
        for part in self._parts(session_id, "text"):
            text = (part.get("text") or "").strip()
            if text:
                yield text

    def reasoning(self, session_id):
        """产出 (text 或 None,)；None = 存在但不可读。"""
        for part in self._parts(session_id, "reasoning"):
            yield (part.get("text") or "").strip() or None

    def tool_names(self, session_id):
        for part in self._parts(session_id, "tool"):
            yield part.get("name") or "?"

    def stats_extra(self, session_ids):
        marks = ",".join("?" * len(session_ids))
        rows = self.conn.execute(
            f"SELECT model, COUNT(*) FROM session_v2 WHERE id IN ({marks}) "
            "GROUP BY model", session_ids).fetchall()
        out = {}
        for m, n in rows:
            try:
                m = json.loads(m).get("id", m)
            except (TypeError, json.JSONDecodeError):
                pass
            out[f"模型:{m}"] = n
        return out

    def message_type_counts(self, session_ids):
        marks = ",".join("?" * len(session_ids))
        rows = self.conn.execute(
            f"SELECT type, COUNT(*) FROM session_message "
            f"WHERE session_id IN ({marks}) GROUP BY type",
            session_ids).fetchall()
        return {t: n for t, n in rows}


# ---------------------------------------------------------------- codex

class CodexAdapter:
    """~/.codex/sessions/**/rollout-*.jsonl[.zst] 与 archived_sessions/。
    格式依据 references/codex-rollout.md。jsonl 无 schema 可守：
    行解析失败跳过，payload 结构不符计入 bad_lines，尾部 stderr 报告。"""

    name = "codex"
    msg_label = "payload"
    FILE_RE = re.compile(
        r"rollout-(\d{4}-\d{2}-\d{2})T\d{2}-\d{2}-\d{2}-([0-9a-f-]{36})")

    def __init__(self, root):
        self.root = Path(root).expanduser()
        if not self.root.exists():
            raise SystemExit(f"codex 根不存在: {self.root}")
        self.bad_lines = 0
        self.unmatched_files = 0
        self._file_cache = None

    def _files(self):
        """全部 rollout 文件；候选文件（.jsonl/.jsonl.zst）文件名不匹配
        命名方案时计数报障——文件名层 drift 不静默。"""
        if self._file_cache is not None:
            yield from self._file_cache
            return
        matched = []
        for base in (self.root / "sessions", self.root / "archived_sessions"):
            if not base.exists():
                continue
            for pattern in ("*.jsonl", "*.jsonl.zst"):
                for path in sorted(base.rglob(pattern)):
                    if self.FILE_RE.search(path.name):
                        matched.append(path)
                    else:
                        self.unmatched_files += 1
        if not matched and self.unmatched_files:
            raise SystemExit(
                f"{self.root} 下 {self.unmatched_files} 个候选文件全部不匹配"
                " rollout 命名方案：格式漂移，请实查真实文件并更新"
                " references/codex-rollout.md")
        self._file_cache = matched
        yield from matched

    def _open(self, path):
        if str(path).endswith(".zst"):
            try:
                import compression.zstd as zstd
            except ImportError:
                raise SystemExit("读取 .zst 需要 Python 3.14+ compression.zstd")
            return zstd.open(path, "rt")
        return open(path, "rt", encoding="utf-8", errors="replace")

    def _records(self, path):
        with self._open(path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    self.bad_lines += 1
                    continue
                if isinstance(rec, dict):
                    yield rec

    def _file_date_id(self, path):
        m = self.FILE_RE.search(Path(path).name)
        return (m.group(1), m.group(2)) if m else (None, None)

    def sessions(self, since=None, until=None, directory=None,
                 main_only=False):
        seen = set()
        rows = []
        for path in self._files():
            date, sid = self._file_date_id(path)
            if not sid:
                continue
            if since and date < since:
                continue
            if until and date > until:
                continue
            cwd, originator = "", ""
            for rec in self._records(path):
                if rec.get("type") == "session_meta":
                    meta = rec.get("payload", {})
                    cwd = meta.get("cwd", "")
                    originator = meta.get("originator", "")
                    sid = meta.get("session_id", sid)
                    break
            if directory and directory not in cwd:
                continue
            if sid in seen:  # 同会话多次 resume 各有一份 rollout 文件
                continue
            seen.add(sid)
            rows.append({"id": sid, "created": date, "directory": cwd,
                         "title": originator, "parent": None})
        rows.sort(key=lambda r: r["created"])
        return rows

    def assert_session(self, session_id):
        self._find(session_id)

    def _find(self, session_id):
        """同一会话的全部 rollout 文件（resume 续写），按文件名时间序。
        按文件名中的会话 uuid 精确匹配；前缀/子串命中他会话即拒绝。"""
        paths = [p for p in self._files()
                 if self._file_date_id(p)[1] == session_id]
        if not paths:
            near = [self._file_date_id(p)[1] for p in self._files()
                    if Path(p).name.find(session_id) >= 0]
            hint = f"；前缀/子串命中 {sorted(set(near))}，会话 id 须完整精确" if near else ""
            raise SystemExit(f"找不到会话 {session_id} 的 rollout 文件{hint}")
        return sorted(paths, key=lambda p: Path(p).name)

    def _items(self, session_id):
        seq = 0
        for path in self._find(session_id):
            for rec in self._records(path):
                if rec.get("type") != "response_item":
                    continue
                payload = rec.get("payload", {})
                if isinstance(payload, dict):
                    seq += 1
                    yield payload

    def user_texts(self, session_id):
        for p in self._items(session_id):
            if p.get("type") == "message" and p.get("role") == "user":
                text = "".join(c.get("text", "") for c in p.get("content", [])
                               if c.get("type") == "input_text").strip()
                if text:
                    yield text

    def assistant_texts(self, session_id):
        for p in self._items(session_id):
            if p.get("type") == "message" and p.get("role") == "assistant":
                text = "".join(c.get("text", "") for c in p.get("content", [])
                               if c.get("type") == "output_text").strip()
                if text:
                    yield text

    def reasoning(self, session_id):
        """Codex reasoning 加密：summary 有文本则产出，否则 None（只计数）。"""
        for p in self._items(session_id):
            if p.get("type") == "reasoning":
                text = "".join(s.get("text", "") for s in p.get("summary", [])
                               if isinstance(s, dict)).strip()
                yield text or None

    def tool_names(self, session_id):
        for p in self._items(session_id):
            if p.get("type") in ("function_call", "custom_tool_call"):
                yield p.get("name") or "?"

    def stats_extra(self, session_ids):
        # session_meta 有 model_provider 等字段，是否稳定可用未核实，不编造分布
        return {}

    def message_type_counts(self, session_ids):
        counts = {}
        for sid in session_ids:
            for p in self._items(sid):
                t = p.get("type") or "?"
                counts[t] = counts.get(t, 0) + 1
        return counts


# ---------------------------------------------------------------- 子命令

def pick_adapter(args):
    if args.harness == "opencode":
        return OpenCodeAdapter(args.db)
    if args.harness == "codex":
        return CodexAdapter(args.root)
    if OPENCODE_DB.exists():
        if CODEX_ROOT.exists():
            print("-- auto 选中 opencode；codex 存储也在场，"
                  "查它用 --harness codex", file=sys.stderr)
        return OpenCodeAdapter(args.db)
    if CODEX_ROOT.exists():
        return CodexAdapter(args.root)
    raise SystemExit("未发现已知 harness 的会话存储"
                     f"（{OPENCODE_DB} 与 {CODEX_ROOT} 均不存在）")


def cmd_list(adapter, **filters):
    rows = list(adapter.sessions(**filters))
    for s in rows:
        print(f"{s['id']}\t{s['created']}\t{s['directory']}\t{s['title']}")
    print(f"-- {len(rows)} 个会话", file=sys.stderr)


def cmd_users(adapter, session_id):
    n = 0
    for text in adapter.user_texts(session_id):
        n += 1
        print(f"--- [{n}] ---")
        print(text)
    print(f"-- {n} 条用户消息", file=sys.stderr)


def _dump(adapter, session_id, source, label, max_chars):
    n = 0
    for text in source(session_id):
        n += 1
        print(f"--- [{n}] ---")
        print(text[:max_chars])
    print(f"-- {n} 条 {label}", file=sys.stderr)


def cmd_text(adapter, session_id, max_chars=1200):
    _dump(adapter, session_id, adapter.assistant_texts, "text", max_chars)


def cmd_reasoning(adapter, session_id, max_chars=1200):
    total, readable = 0, 0
    for text in adapter.reasoning(session_id):
        total += 1
        if text is None:
            continue
        readable += 1
        print(f"--- [{readable}] ---")
        print(text[:max_chars])
    note = f"-- {total} 条 reasoning"
    if readable < total:
        note += f"，{total - readable} 条加密或不可读"
    print(note, file=sys.stderr)


def cmd_tools(adapter, session_id):
    counts = {}
    for name in adapter.tool_names(session_id):
        counts[name] = counts.get(name, 0) + 1
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"{n}\t{name}")
    print(f"-- 共 {sum(counts.values())} 次调用", file=sys.stderr)


def cmd_stats(adapter, **filters):
    session_ids = [s["id"] for s in adapter.sessions(**filters)]
    print(f"会话数\t{len(session_ids)}")
    if not session_ids:
        return
    for t, n in sorted(adapter.message_type_counts(session_ids).items()):
        print(f"{adapter.msg_label}:{t}\t{n}")
    for k, n in sorted(adapter.stats_extra(session_ids).items(),
                       key=lambda kv: -kv[1]):
        print(f"{k}\t{n}")


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--harness", choices=("auto", "opencode", "codex"),
                   default="auto")
    p.add_argument("--db", default=str(OPENCODE_DB), help="opencode 库路径")
    p.add_argument("--root", default=str(CODEX_ROOT), help="codex 根目录")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_time_args(sp):
        sp.add_argument("--since", help="起始日 YYYY-MM-DD（含）")
        sp.add_argument("--until", help="截止日 YYYY-MM-DD（含）")
        sp.add_argument("--directory", help="目录子串过滤")
        sp.add_argument("--main-only", action="store_true",
                        help="只算主会话（parent_id IS NULL）")

    sp = sub.add_parser("list", help="列出会话")
    add_time_args(sp)
    for name in ("users", "text", "reasoning", "tools"):
        sp = sub.add_parser(name, help=f"{name} 提取")
        sp.add_argument("session_id")
        if name in ("text", "reasoning"):
            sp.add_argument("--max", type=int, default=1200,
                            help="每条截断字符数")
    sp = sub.add_parser("stats", help="聚合统计")
    add_time_args(sp)

    args = p.parse_args()
    adapter = pick_adapter(args)
    filters = {"since": getattr(args, "since", None),
               "until": getattr(args, "until", None),
               "directory": getattr(args, "directory", None),
               "main_only": getattr(args, "main_only", False)}
    if filters["main_only"] and adapter.name == "codex":
        print("-- codex 无父子会话概念，--main-only 不适用已忽略",
              file=sys.stderr)
    if args.cmd == "list":
        cmd_list(adapter, **filters)
    elif args.cmd == "stats":
        cmd_stats(adapter, **filters)
    else:
        adapter.assert_session(args.session_id)
        if args.cmd == "users":
            cmd_users(adapter, args.session_id)
        elif args.cmd == "text":
            cmd_text(adapter, args.session_id, args.max)
        elif args.cmd == "reasoning":
            cmd_reasoning(adapter, args.session_id, args.max)
        elif args.cmd == "tools":
            cmd_tools(adapter, args.session_id)
    if getattr(adapter, "bad_lines", 0):
        print(f"-- {adapter.bad_lines} 行解析失败已跳过", file=sys.stderr)
    if getattr(adapter, "unmatched_files", 0):
        print(f"-- {adapter.unmatched_files} 个候选文件名不匹配命名方案"
              "（疑似格式漂移，见 references/codex-rollout.md）",
              file=sys.stderr)


if __name__ == "__main__":
    main()
