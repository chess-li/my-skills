import argparse
import io
import json
import sqlite3
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

import session_extract as se


def make_opencode_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE session_v2 (id TEXT PRIMARY KEY, directory TEXT, "
        "title TEXT, model TEXT, time_created INTEGER, parent_id TEXT)")
    conn.execute(
        "CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, "
        "type TEXT, seq INTEGER, data TEXT)")
    t1 = int(se.day_ms("2026-10-01"))
    t2 = int(se.day_ms("2026-10-10"))
    conn.executemany(
        "INSERT INTO session_v2 VALUES (?,?,?,?,?,?)",
        [("ses_a", "/repo/x", "甲会话", "m1", t1, None),
         ("ses_b", "/repo/y", None, "m2", t2, None),
         ("ses_c", "/repo/x", "子代理", "m1", t2, "ses_a")])
    msgs = [
        ("m1", "ses_a", "user", 1, {"text": "第一句话"}),
        ("m2", "ses_a", "user", 2, {"text": ""}),
        ("m3", "ses_a", "user", 3, {"text": "第二句话"}),
        ("m4", "ses_a", "assistant", 4, {"content": [
            {"type": "reasoning", "text": "想一下"},
            {"type": "reasoning", "text": ""},
            {"type": "text", "text": "可见答复"},
            {"type": "tool", "name": "shell"},
            {"type": "tool", "name": "shell"},
            {"type": "tool", "name": "read"}]}),
        ("m5", "ses_a", "idle", 5, {}),
        ("m6", "ses_b", "user", 1, {"text": "另一会话"}),
    ]
    conn.executemany(
        "INSERT INTO session_message VALUES (?,?,?,?,?)",
        [(i, s, t, q, json.dumps(d)) for i, s, t, q, d in msgs])
    conn.commit()
    conn.close()


def make_codex_root(root):
    day = Path(root) / "sessions" / "2026" / "10" / "03"
    day.mkdir(parents=True)
    records = [
        {"type": "session_meta", "payload": {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "cwd": "/repo/codex-proj", "originator": "codex_cli"}},
        {"type": "response_item", "payload": {"type": "message",
            "role": "user", "content": [
                {"type": "input_text", "text": "查一下这个 bug"}]}},
        {"type": "response_item", "payload": {"type": "reasoning",
            "summary": [], "encrypted_content": "gAAAA..."}},
        {"type": "response_item", "payload": {"type": "message",
            "role": "assistant", "content": [
                {"type": "output_text", "text": "先复现"}]}},
        {"type": "response_item", "payload": {"type": "function_call",
            "name": "exec", "input": "..."}},
        {"type": "response_item", "payload": {"type": "custom_tool_call",
            "name": "apply_patch", "input": "..."}},
    ]
    path = day / "rollout-2026-10-03T06-03-26-11111111-1111-1111-1111-111111111111.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    # 同会话 resume 产生第二份 rollout 文件（带续写 id 后缀），含增量消息
    resumed = day / ("rollout-2026-10-03T07-00-00-"
                     "11111111-1111-1111-1111-111111111111_"
                     "22222222-2222-2222-2222-222222222222.jsonl")
    resumed.write_text(json.dumps(
        {"type": "response_item", "payload": {"type": "message",
         "role": "assistant", "content": [
             {"type": "output_text", "text": "续写答复"}]}}))
    return "11111111-1111-1111-1111-111111111111"


def run(fn, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        fn(*args, **kwargs)
    return out.getvalue(), err.getvalue()


class TestOpenCodeAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "t.db")
        make_opencode_db(self.db)
        self.a = se.OpenCodeAdapter(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_guard_rejects_drift(self):
        bad = str(Path(self.tmp.name) / "bad.db")
        sqlite3.connect(bad).execute(
            "CREATE TABLE session_v2 (id TEXT)").connection.close()
        with self.assertRaises(SystemExit):
            se.OpenCodeAdapter(bad)

    def test_sessions_filters(self):
        rows = list(self.a.sessions(since="2026-10-05"))
        self.assertEqual([r["id"] for r in rows], ["ses_b", "ses_c"])
        rows = list(self.a.sessions(directory="/repo/x", main_only=True))
        self.assertEqual([r["id"] for r in rows], ["ses_a"])

    def test_user_texts_skip_empty(self):
        self.assertEqual(list(self.a.user_texts("ses_a")),
                         ["第一句话", "第二句话"])

    def test_text_reasoning_tools(self):
        self.assertEqual(list(self.a.assistant_texts("ses_a")), ["可见答复"])
        self.assertEqual(list(self.a.reasoning("ses_a")), ["想一下", None])
        self.assertEqual(list(self.a.tool_names("ses_a")),
                         ["shell", "shell", "read"])

    def test_stats(self):
        out, _ = run(se.cmd_stats, self.a)
        self.assertIn("会话数\t3", out)
        self.assertIn("消息:user\t4", out)
        self.assertIn("模型:m1\t2", out)

    def test_reasoning_cmd_reports_unreadable(self):
        _, err = run(se.cmd_reasoning, self.a, "ses_a")
        self.assertIn("2 条 reasoning", err)
        self.assertIn("1 条加密或不可读", err)

    def test_missing_session_fails_loudly(self):
        with self.assertRaises(SystemExit) as ctx:
            self.a.assert_session("ses_不存在")
        self.assertIn("不存在", str(ctx.exception))


class TestCodexAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.sid = make_codex_root(self.tmp.name)
        self.a = se.CodexAdapter(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sessions_dedupe_resumed_files(self):
        rows = list(self.a.sessions())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], self.sid)
        self.assertEqual(rows[0]["directory"], "/repo/codex-proj")
        rows = list(self.a.sessions(since="2026-10-04"))
        self.assertEqual(rows, [])

    def test_messages_merge_resumed_files(self):
        self.assertEqual(list(self.a.user_texts(self.sid)), ["查一下这个 bug"])
        texts = list(self.a.assistant_texts(self.sid))
        self.assertEqual(texts, ["先复现", "续写答复"])

    def test_reasoning_encrypted_counts_only(self):
        self.assertEqual(list(self.a.reasoning(self.sid)), [None])
        _, err = run(se.cmd_reasoning, self.a, self.sid)
        self.assertIn("1 条加密或不可读", err)

    def test_tools_both_call_types(self):
        self.assertEqual(sorted(self.a.tool_names(self.sid)),
                         ["apply_patch", "exec"])

    def test_stats_counts_payload_types(self):
        out, _ = run(se.cmd_stats, self.a)
        self.assertIn("会话数\t1", out)
        self.assertIn("payload:message\t3", out)

    def test_missing_session_fails_loudly(self):
        with self.assertRaises(SystemExit):
            list(self.a.user_texts("00000000-0000-0000-0000-000000000000"))

    def test_prefix_id_rejected_not_merged(self):
        # 前缀命中多个会话时必须拒绝，不静默合并证据流
        with self.assertRaises(SystemExit) as ctx:
            self.a.assert_session(self.sid[:8])
        self.assertIn("完整精确", str(ctx.exception))

    def test_unmatched_filename_drift_fails_loudly(self):
        rogue_root = Path(self.tmp.name) / "drift-root"
        rogue_sub = rogue_root / "archived_sessions"
        rogue_sub.mkdir(parents=True)
        (rogue_sub / "session-2026-10-09.jsonl").write_text("{}")
        a2 = se.CodexAdapter(str(rogue_root))
        with self.assertRaises(SystemExit) as ctx:
            list(a2._files())
        self.assertIn("格式漂移", str(ctx.exception))
        # 正常根 + 一个漂移文件：可运行但计数报障
        rogue_sub.rename(Path(self.tmp.name) / "archived_sessions")
        rows = list(self.a.sessions())
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.a.unmatched_files, 1)

    def test_zst_read_path(self):
        try:
            import compression.zstd as zstd_mod
        except ImportError:
            self.skipTest("python 无 compression.zstd")
        day = Path(self.tmp.name) / "sessions" / "2026" / "10" / "04"
        day.mkdir(parents=True, exist_ok=True)
        records = [{"type": "session_meta", "payload": {
            "session_id": "33333333-3333-3333-3333-333333333333",
            "cwd": "/repo/z", "originator": "codex_cli"}}]
        with zstd_mod.open(
                day / "rollout-2026-10-04T01-00-00-33333333-3333-3333-3333-333333333333.jsonl.zst",
                "wt") as f:
            f.write("\n".join(json.dumps(r) for r in records))
        rows = list(self.a.sessions(since="2026-10-04"))
        self.assertEqual([r["id"] for r in rows],
                         ["33333333-3333-3333-3333-333333333333"])


class TestPickAdapter(unittest.TestCase):
    def test_auto_prefers_opencode_and_notes_codex_presence(self):
        from unittest import mock
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        make_opencode_db(str(db))
        codex_root = Path(tmp.name) / "codex"
        codex_root.mkdir()
        args = argparse.Namespace(harness="auto", db=str(db),
                                  root=str(codex_root))
        with mock.patch.object(se, "OPENCODE_DB", db), \
                mock.patch.object(se, "CODEX_ROOT", codex_root):
            _, err = run(se.pick_adapter, args)
        self.assertIn("--harness codex", err)

    def test_auto_fails_when_nothing_exists(self):
        from unittest import mock
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        missing = Path(tmp.name) / "none"
        args = argparse.Namespace(harness="auto", db=str(missing),
                                  root=str(missing))
        with mock.patch.object(se, "OPENCODE_DB", missing), \
                mock.patch.object(se, "CODEX_ROOT", missing):
            with self.assertRaises(SystemExit):
                se.pick_adapter(args)


if __name__ == "__main__":
    unittest.main()
