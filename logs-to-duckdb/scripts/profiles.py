#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内置日志格式档案（单源）。detect_log_format.py 与 logs_to_duckdb.py 共用。

每个 profile 一条命名组正则。命名组约定：
- 必需: ts（时间戳原文）、level、message
- 可选: host、tenant、thread、logger、method、line 等，命名组名即列名
- 组名 line 的列建为 INTEGER，其余可选组建为 VARCHAR
"""
import re

LEVEL = r"(?:TRACE|DEBUG|INFO|WARN|ERROR|FATAL)"

PROFILES = {
    # EY 线上 log4j2 格式（实测）:
    #   2026-10-28 00:00:00.012 ecs-host/tenantId xxl-job, EmbedServer bizThreadPool-1 INFO  com.foo.Bar.method:244 - msg
    # 线程名无方括号、可含空格逗号；行号可为 -1（SLF4J 桥接）
    "ey-log4j2": {
        "regex": (
            r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) "
            r"(?P<host>[^\s/]+)/(?P<tenant>\S+) "
            r"(?P<thread>.*?) "
            r"(?P<level>" + LEVEL + r") +"
            r"(?P<logger>.+)\.(?P<method>.+):(?P<line>-?\d+) - "
            r"(?P<message>.*)$"
        ),
        "ts_formats": [],
        "desc": "EY 线上 log4j2：yyyy-MM-dd HH:mm:ss.SSS host/tenant thread LEVEL Class.method:Line - msg",
    },
    # 常见 log4j2/logback 控制台格式（方括号线程、逗号毫秒）:
    #   2026-10-29 17:32:02,998 [http-nio-8080-exec-1] INFO  c.e.s.FooService.bar:12 - msg
    "log4j2-bracket": {
        "regex": (
            r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) "
            r"\[(?P<thread>[^\]]+)\] "
            r"(?P<level>" + LEVEL + r") +"
            r"(?P<logger>[\w.$]+?)(?::(?P<line>-?\d+))? - "
            r"(?P<message>.*)$"
        ),
        "ts_formats": ["%Y-%m-%d %H:%M:%S,%f"],
        "desc": "log4j2/logback 控制台：yyyy-MM-dd HH:mm:ss,SSS [thread] LEVEL logger - msg",
    },
    # ISO8601 带时区偏移:
    #   2026-10-29T17:32:02.998+08:00 INFO  [thread] c.e.s.Foo - msg
    "iso-offset": {
        "regex": (
            r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:?\d{2}) "
            r"(?P<level>" + LEVEL + r") +"
            r"(?:\[(?P<thread>[^\]]+)\] )?"
            r"(?P<logger>[\w.$]+) - "
            r"(?P<message>.*)$"
        ),
        "ts_formats": [],
        "desc": "ISO8601 带偏移：yyyy-MM-ddTHH:mm:ss.SSS+08:00 LEVEL [thread] logger - msg",
    },
}

REQUIRED_GROUPS = ("ts", "level", "message")
INT_COLUMNS = {"line"}


def compile_profile(name):
    """返回 (compiled_regex, ts_formats)。未知 profile 抛 ValueError。"""
    if name not in PROFILES:
        raise ValueError(
            f"未知 profile: {name}。内置: {', '.join(sorted(PROFILES))}；"
            "都不匹配时用 logs_to_duckdb.py --regex 传自定义命名组正则"
        )
    p = PROFILES[name]
    return re.compile(p["regex"]), list(p["ts_formats"])


def validate_groups(pattern):
    """校验命名组约定，返回排序后的可选组名列表（不含 ts/level/message）。"""
    names = set(pattern.groupindex)
    missing = [g for g in REQUIRED_GROUPS if g not in names]
    if missing:
        raise ValueError(
            f"正则缺少必需命名组: {', '.join(missing)}。"
            "必需组: ts(时间戳原文), level, message；可选组名即列名（如 thread/logger/host）"
        )
    return sorted(names - set(REQUIRED_GROUPS))
