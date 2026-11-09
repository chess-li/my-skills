#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 G1 GC 日志（gc.log / gc.log.N）解析成 gc.csv。

用法: python3 parse_gc_log.py [日志目录] [输出csv]
默认: 同目录下 gc日志/ -> gc.csv
"""
import csv
import os
import re
import sys

# 行首: [2026-10-29T17:32:02.998+0800][89494.901s][info ][gc          ] GC(15550) ...
LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\[(?P<uptime>[\d.]+)s\]\[[^\]]*\]\[(?P<tag>[^\]]+)\]\s*"
    r"GC\((?P<gcid>\d+)\)\s*(?P<msg>.*)$"
)

# Pause 行: Pause Young (Normal) (G1 Evacuation Pause) 911M->646M(1174M) 10.168ms
#           Pause Remark 822M->822M(1180M) 29.204ms
PAUSE_RE = re.compile(
    r"^Pause\s+(?P<body>.*?)\s+"
    r"(?P<before>[\d.]+[KMG])->(?P<after>[\d.]+[KMG])\((?P<heap>[\d.]+[KMG])\)\s*"
    r"(?P<dur>[\d.]+)ms$"
)

# 并发周期行: Concurrent Mark Cycle [960.830ms] / Concurrent Undo Cycle [4.057ms]
CONCURRENT_RE = re.compile(r"^(?P<kind>Concurrent (?:Mark|Undo) Cycle)(?:\s+(?P<dur>[\d.]+)ms)?$")

# CPU 行: User=0.03s Sys=0.00s Real=0.01s
CPU_RE = re.compile(r"User=(?P<user>[\d.]+)s\s+Sys=(?P<sys>[\d.]+)s\s+Real=(?P<real>[\d.]+)s")


def size_to_mb(s):
    """'911M' / '1024K' / '2G' -> MB 浮点数"""
    if not s:
        return None
    m = re.match(r"([\d.]+)([KMG])", s)
    if not m:
        return None
    v, unit = float(m.group(1)), m.group(2)
    return round(v / {"K": 1024.0, "M": 1.0, "G": 1024.0}[unit], 2)


def parse_files(paths, out_csv):
    # cpu 信息按 gc_id 暂存，等 pause 行出现后合并
    cpu_pending = {}
    rows = []
    n_skip = 0

    for path in paths:
        fname = os.path.basename(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = LINE_RE.match(line.rstrip("\n"))
                if not m:
                    continue
                tag = m.group("tag").strip()
                gcid = int(m.group("gcid"))
                msg = m.group("msg").strip()
                base = None

                if tag == "gc,cpu":
                    c = CPU_RE.search(msg)
                    if c:
                        cpu_pending[gcid] = {
                            "user_s": c.group("user"),
                            "sys_s": c.group("sys"),
                            "real_s": c.group("real"),
                        }
                    continue

                if tag != "gc":
                    continue

                pm = PAUSE_RE.match(msg)
                if pm:
                    body = pm.group("body")
                    parts = body.split(") (")
                    # 'Young (Normal) (G1 Evacuation Pause' -> kind=Young, sub=Normal, cause=...
                    if parts[0].startswith("Young ("):
                        sub = parts[0][len("Young ("):]
                        cause = parts[1].rstrip(")") if len(parts) > 1 else ""
                        event = f"Young ({sub})"
                    else:  # Pause Remark / Pause Cleanup / Pause Full
                        event = parts[0].strip()
                        cause = parts[1].rstrip(")") if len(parts) > 1 else ""
                    base = {
                        "event": event,
                        "cause": cause,
                        "before_mb": size_to_mb(pm.group("before")),
                        "after_mb": size_to_mb(pm.group("after")),
                        "heap_mb": size_to_mb(pm.group("heap")),
                        "duration_ms": pm.group("dur"),
                        "is_pause": "Y",
                    }
                else:
                    cm = CONCURRENT_RE.match(msg)
                    if cm and cm.group("dur"):  # 只取有耗时的汇总行，跳过 start 行
                        base = {
                            "event": cm.group("kind"),
                            "cause": "",
                            "before_mb": "", "after_mb": "", "heap_mb": "",
                            "duration_ms": cm.group("dur"),
                            "is_pause": "N",
                        }

                if base is None:
                    n_skip += 1
                    continue

                base.update({
                    "file": fname,
                    "timestamp": m.group("ts"),
                    "uptime_s": m.group("uptime"),
                    "gc_id": gcid,
                })
                base.update(cpu_pending.pop(gcid, {"user_s": "", "sys_s": "", "real_s": ""}))
                # 进程多次重启, 每个文件 uptime 各自从 0 开始; 文件按时间先后处理,
                # 文件内日志天然按时间排列, 因此保留插入顺序, 不按 uptime 全局排序
                rows.append(base)

    fields = ["file", "timestamp", "uptime_s", "gc_id", "event", "cause",
              "before_mb", "after_mb", "heap_mb", "duration_ms",
              "user_s", "sys_s", "real_s", "is_pause"]
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"解析完成: {len(rows)} 条 GC 事件 -> {out_csv} (跳过 {n_skip} 行未识别汇总行)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法: python3 parse_gc_log.py <gc日志目录> [输出csv路径]")
    log_dir = sys.argv[1]
    out_csv = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.getcwd(), "gc.csv")

    # 日志轮转顺序: 数字越大越旧, 按时间先后处理
    names = [n for n in os.listdir(log_dir) if re.fullmatch(r"gc\.log(\.\d+)?", n)]
    names.sort(key=lambda n: int(n.split(".")[-1]) if n.split(".")[-1].isdigit() else -1, reverse=True)
    paths = [os.path.join(log_dir, n) for n in names]
    print("处理顺序:", names)
    parse_files(paths, out_csv)
