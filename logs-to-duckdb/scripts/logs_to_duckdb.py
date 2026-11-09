#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按已确认的格式把应用日志解析写入 DuckDB（.log/.log.gz，增量续导）。

格式来源（二选一）:
  --profile <名>   内置档案（见 profiles.py / references/formats.md）
  --regex <正则>   自定义命名组正则；必需组 ts/level/message，可选组名即列名（line 列建为 INTEGER）

续行（异常堆栈/多行消息）归入 stack；exception_type 只认 *Exception/*Error/*Throwable 头或 Caused by:。

用法:
    python3 logs_to_duckdb.py --dir <日志目录> --db <输出.duckdb> --profile <名> [--reset]
    python3 logs_to_duckdb.py --dir <日志目录> --db <输出.duckdb> --regex '(?P<ts>...) ...' [--ts-format '%...']

时区: 带偏移的时间戳按偏移解析；无时戳偏移的按导入机器本地时区解释（与 epoch 毫秒一致）。
"""
import argparse
import gzip
import os
import re
import sys
import time
from datetime import datetime

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profiles import INT_COLUMNS, compile_profile, validate_groups  # noqa: E402

STACK_FRAME_RE = re.compile(r"^\s*at\s")
MORE_RE = re.compile(r"^\s*\.\.\. \d+ more")
CAUSED_BY_RE = re.compile(r"^Caused by:\s*(\S+)")
EX_HEAD_RE = re.compile(r"^[\w$]+(?:\.[\w$]+)*(?:Exception|Error|Throwable)(?::.*)?$")

BATCH = 50000

# 无时戳偏移时的候选解析格式（含 profile 自带 ts_formats，--ts-format 追加在后）
BASE_TS_FORMATS = [
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S,%f",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
]


def parse_ts_ms(raw, ts_formats):
    """时间戳原文 -> epoch 毫秒；解析失败返回 None（行照常入库，ts_ms 为 NULL）。"""
    if not raw:
        return None
    raw = raw.strip()
    dt = None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ts_formats:
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def extract_exception_type(stack_text):
    caused = CAUSED_BY_RE.findall(stack_text)
    if caused:
        return caused[-1]
    for ln in stack_text.splitlines():
        if STACK_FRAME_RE.match(ln) or MORE_RE.match(ln):
            continue
        ln = ln.strip()
        if ln and EX_HEAD_RE.match(ln):
            return ln.split(":", 1)[0].strip()
    return None


def open_log(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def build_ddl(extra_cols):
    """列序: file, level, log_time, ts_ms, <可选组...>, message, exception_type, stack"""
    def col_type(c):
        return "INTEGER" if c in INT_COLUMNS else "VARCHAR"
    cols = ["file VARCHAR", "level VARCHAR", "log_time VARCHAR", "ts_ms BIGINT"]
    cols += [f"{c} {col_type(c)}" for c in extra_cols]
    cols += ["message VARCHAR", "exception_type VARCHAR", "stack VARCHAR"]
    return ("CREATE TABLE IF NOT EXISTS log_entry (" + ", ".join(cols) + ");\n"
            "CREATE TABLE IF NOT EXISTS imported_files "
            "(file VARCHAR PRIMARY KEY, profile VARCHAR, rows BIGINT, imported_at TIMESTAMP);")


def import_file(con, path, fname, rx, extra_cols, ts_formats):
    """返回入库行数。named groups: ts/level/message 必需，extra_cols 为其余组名。"""
    groups = ["file", "level", "log_time", "ts_ms"] + extra_cols + ["message", "exception_type", "stack"]
    # cur 状态: meta dict + message 行列表 + stack 行列表
    cur = None
    n = 0
    buf = []

    def meta_of(m):
        g = m.groupdict()
        return {
            "file": fname,
            "level": g["level"].strip(),
            "log_time": g["ts"].strip(),
            "ts_ms": parse_ts_ms(g["ts"], ts_formats),
            **{c: g.get(c) for c in extra_cols},
            "_message": [g["message"]],
            "_stack": [],
        }

    def emit(meta):
        nonlocal n
        message = "\n".join(meta.pop("_message")).strip()
        stack = "\n".join(meta.pop("_stack")).strip()
        buf.append((
            *[meta[c] for c in groups[:4 + len(extra_cols)]],
            message,
            extract_exception_type(stack) if stack else None,
            stack or None,
        ))
        n += 1
        if n % BATCH == 0:
            flush()

    def flush():
        if not buf:
            return
        marks = ",".join("?" * len(groups))
        con.executemany(
            f"INSERT INTO log_entry ({', '.join(groups)}) VALUES ({marks})", buf)
        buf.clear()

    with open_log(path) as f:
        for line in f:
            line = line.rstrip("\n")
            m = rx.match(line)
            if m:
                if cur is not None:
                    emit(cur)
                cur = meta_of(m)
            else:
                if cur is not None:
                    cur["_stack"].append(line)
                else:  # 文件首行即续行（截断的轮转文件）：占位入库，不丢内容
                    cur = {"file": fname, "level": "?", "log_time": None, "ts_ms": None,
                           **{c: None for c in extra_cols},
                           "_message": [line], "_stack": []}
    if cur is not None:
        emit(cur)
    flush()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--profile", help="内置档案名（与 --regex 二选一）")
    ap.add_argument("--regex", help="自定义命名组正则（必需组 ts/level/message）")
    ap.add_argument("--ts-format", action="append", default=[],
                    help="追加时间戳 strptime 格式，可多次传入")
    ap.add_argument("--reset", action="store_true", help="清空已导入数据重来")
    args = ap.parse_args()

    if bool(args.profile) == bool(args.regex):
        sys.exit("必须且只能指定 --profile <名> 或 --regex <正则>；先用 detect_log_format.py 分析格式")

    if args.profile:
        rx, profile_ts_formats = compile_profile(args.profile)
        profile_name = args.profile
    else:
        try:
            rx = re.compile(args.regex)
        except re.error as e:
            sys.exit(f"正则编译失败: {e}")
        profile_ts_formats, profile_name = [], "custom"
    try:
        extra_cols = validate_groups(rx)
    except ValueError as e:
        sys.exit(str(e))
    ts_formats = BASE_TS_FORMATS + profile_ts_formats + args.ts_format

    con = duckdb.connect(args.db)
    try:
        # 预检: 已有 log_entry 的列结构必须与本次格式一致，否则先清库或换 db 文件，
        # 避免删了旧行又插不进新行（CREATE TABLE IF NOT EXISTS 不会补列）
        expected = ["file", "level", "log_time", "ts_ms"] + extra_cols + \
                   ["message", "exception_type", "stack"]
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'log_entry'").fetchone()[0]
        if exists and not args.reset:
            actual = [r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'log_entry' ORDER BY ordinal_position").fetchall()]
            if actual != expected:
                sys.exit(
                    f"已有 log_entry 表结构与本次格式不一致。\n"
                    f"  库中列: {actual}\n  本次需要: {expected}\n"
                    f"换格式重导请加 --reset 清空重来，或换一个 --db 文件。")
        con.execute(build_ddl(extra_cols))
        if args.reset:
            con.execute("DELETE FROM log_entry")
            con.execute("DELETE FROM imported_files")
            print("==> 已清空 log_entry / imported_files")

        files = sorted(f for f in os.listdir(args.dir) if f.endswith((".log", ".log.gz")))
        done = {r[0]: r[1] for r in con.execute(
            "SELECT file, profile FROM imported_files").fetchall()}
        todo, skipped = [], []
        for f in files:
            if f not in done:
                todo.append(f)
            elif done[f] != profile_name:
                con.execute("DELETE FROM log_entry WHERE file = ?", [f])
                con.execute("DELETE FROM imported_files WHERE file = ?", [f])
                todo.append(f)
                skipped.append(f"格式变更重导: {f}")
            else:
                skipped.append(f"已导入: {f}")
        print(f"==> 共 {len(files)} 个日志文件, 待导入 {len(todo)} 个, 数据库: {args.db}")
        for s in skipped:
            print(f"    跳过 {s}")

        total = 0
        for i, fname in enumerate(todo, 1):
            t0 = time.time()
            n = import_file(con, os.path.join(args.dir, fname), fname,
                            rx, extra_cols, ts_formats)
            total += n
            con.execute(
                "INSERT INTO imported_files VALUES (?, ?, ?, current_timestamp) "
                "ON CONFLICT (file) DO UPDATE SET "
                "profile=excluded.profile, rows=excluded.rows, imported_at=excluded.imported_at",
                [fname, profile_name, n])
            print(f"[{i}/{len(todo)}] {fname}: {n} 行, {time.time() - t0:.1f}s")
        print(f"==> 完成: 本次导入 {total} 行, 累计 "
              f"{con.execute('SELECT COUNT(*) FROM log_entry').fetchone()[0]} 行")
    finally:
        con.close()


if __name__ == "__main__":
    main()
