#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 gc.csv 写入 DuckDB 数据库 gc.duckdb。

类型约定(DuckDB 原生类型, 无需注册转换器):
- timestamp -> TIMESTAMPTZ, 原生时区时间戳, Python 读回即 aware datetime
- gc_id     -> BIGINT
- *_mb / duration_ms / user_s / sys_s / real_s / uptime_s -> DOUBLE
- 空值      -> NULL (不是空字符串)

时区说明: 数据以时间瞬值(UTC)存储, 与时区无关; 分析连接用
  SET TimeZone='Asia/Shanghai'  (或日志实际时区)
控制显示/分桶的时区。

用法: python3 csv_to_duckdb.py [gc.csv] [gc.duckdb]
"""
import csv
import os
import re
import sys
from datetime import datetime

import duckdb

ISO_TZ_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})([+-]\d{4})$")


def iso_to_aware(ts: str) -> datetime:
    """2026-10-29T17:32:02.998+0800 -> aware datetime (DuckDB 自动存为时间瞬值)"""
    m = ISO_TZ_RE.match(ts.strip())
    if not m:
        raise ValueError(f"无法解析时间戳: {ts!r}")
    date, h, mi, s, ms, off = m.groups()
    return datetime.fromisoformat(f"{date}T{h}:{mi}:{s}.{ms}{off[:3]}:{off[3:]}")


def to_float(v):
    return float(v) if v not in (None, "") else None


def main(csv_path, db_path):
    con = duckdb.connect(db_path)
    try:
        con.execute("DROP TABLE IF EXISTS gc")
        con.execute("""
            CREATE TABLE gc (
                file        VARCHAR NOT NULL,
                timestamp   TIMESTAMPTZ NOT NULL,
                uptime_s    DOUBLE NOT NULL,
                gc_id       BIGINT NOT NULL,
                event       VARCHAR NOT NULL,
                cause       VARCHAR,
                before_mb   DOUBLE,
                after_mb    DOUBLE,
                heap_mb     DOUBLE,
                duration_ms DOUBLE NOT NULL,
                user_s      DOUBLE,
                sys_s       DOUBLE,
                real_s      DOUBLE,
                is_pause    VARCHAR NOT NULL CHECK (is_pause IN ('Y','N'))
            )
        """)
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = [
                (
                    r["file"],
                    iso_to_aware(r["timestamp"]),
                    float(r["uptime_s"]),
                    int(r["gc_id"]),
                    r["event"],
                    r["cause"] or None,
                    to_float(r["before_mb"]),
                    to_float(r["after_mb"]),
                    to_float(r["heap_mb"]),
                    float(r["duration_ms"]),
                    to_float(r["user_s"]),
                    to_float(r["sys_s"]),
                    to_float(r["real_s"]),
                    r["is_pause"],
                )
                for r in reader
            ]
        con.executemany(
            """INSERT INTO gc
               (file, timestamp, uptime_s, gc_id, event, cause,
                before_mb, after_mb, heap_mb, duration_ms,
                user_s, sys_s, real_s, is_pause)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        n = con.execute("SELECT COUNT(*) FROM gc").fetchone()[0]
        print(f"写入完成: {n} 行 -> {db_path}")
    finally:
        con.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法: python3 csv_to_duckdb.py <gc.csv路径> [输出db路径]")
    csv_path = sys.argv[1]
    db_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.getcwd(), "gc.duckdb")
    main(csv_path, db_path)
