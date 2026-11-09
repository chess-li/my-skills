---
name: analyze-g1-gc-logs
description: 分析 JVM G1 GC 日志（gc.log / gc.log.N 轮转文件）：解析为 CSV 中间产物、写入带原生时区时间戳的 DuckDB 数据库并执行常用诊断查询。当用户提供 HotSpot G1 GC 日志、要求排查 GC 停顿/Full GC/内存泄漏、或需要对 gc.csv/gc.duckdb 做 GC 分析时使用。
---

# G1 GC 日志分析

## 工作流（按顺序执行）

1. **确认日志形态**：`ls` 日志目录，确认是 G1 GC 日志（行形如 `[2026-10-29T17:32:02.998+0800][89494.901s][info ][gc          ] GC(15550) ...`，tag 含 `gc,phases`/`gc,heap`/`safepoint` 等）。若tag为 `gc` 且出现 `Pause Young`/`Concurrent Mark Cycle` 即 G1。其他收集器（CMS/ZGC/Shenandoah）格式不同，本 skill 的正则不匹配，需先告知用户。
2. **解析**：`python3 scripts/parse_gc_log.py <日志目录> [输出.csv]` — 自动按轮转时间顺序（gc.log.N 数字越大越旧）合并所有文件。
3. **抽样检查 CSV**：CSV 只是数据清洗中间产物，用 `head` 或 pandas 抽查几行确认解析正确（event/cause 拆分、MB 换算、耗时数量级），不要拿 CSV 做分析。
4. **入库**：`python3 scripts/csv_to_duckdb.py <csv路径> [输出.duckdb]` — 生成分析用 DuckDB。
5. **查询分析**：所有分析查询都打在 DuckDB 上。常用查询见 [references/queries.md](references/queries.md)，日志行格式与表结构细节见 [references/schema.md](references/schema.md)。

## 查询方式

```python
import duckdb
con = duckdb.connect("gc.duckdb")
con.execute("SET TimeZone='Asia/Shanghai'")  # 换成日志的实际时区; 控制显示与分桶时区
# SELECT timestamp 直接得到带时区的 datetime 对象, 无需任何转换器注册
```

注意：`SET TimeZone` 只影响当前连接，每个新连接都要重新设置。分析脚本多的话先封装一个 `get_con(path)`。

## 关键经验（踩坑记录，必读）

- **进程会重启**：同一批轮转日志通常对应多个 JVM 进程，每个文件里 `gc_id` 和 `uptime_s` 都从 0 开始。跨文件分析只能用 `timestamp`，绝不能用 uptime 或 gc_id 排序/连接。用 `file` 列区分进程段。
- **timestamp 类型**：DuckDB 原生 `TIMESTAMPTZ` 列，Python 读写都是 aware datetime，比 SQLite 的文本方案省心。数据库存的是时间瞬值（与时区无关），显示/分桶时区由连接的 `TimeZone` 设置决定；不设则默认 UTC。
- **数字必须落库为数字**：`*_mb`、`duration_ms`、`user_s` 等列是 DOUBLE，`gc_id` 是 BIGINT；空值存 NULL 而不是空字符串，否则 AVG/SUM 全废。
- **并发周期只有耗时**：`Concurrent Mark Cycle` / `Concurrent Undo Cycle` 行没有堆占用数字，`before_mb/after_mb/heap_mb` 为 NULL 是正常的，不是解析 bug。
- **Full GC 识别**：G1 的 Full GC 事件是 `event='Full (G1 Compaction Pause)'`，典型特征是 `before_mb ≈ heap_mb`（堆几乎占满才触发压缩），单次耗时秒级，是停顿分析的第一优先排查对象。
- **停顿口径**：`is_pause='Y'` 才是 STW 停顿；并发周期（含 Concurrent Mark Cycle）不阻塞业务线程，算停顿占比时必须排除。
- **DuckDB 不需要手动建索引**：3 万行级别的表 DuckDB 自动 zonemap 就够，`CREATE INDEX` 只会拖慢写入。

## 产出建议

分析结论报告给用户时包含：时间范围与进程段数（按 file 分组）、停顿总时长与占比、Full GC 次数/时间线/触发时的堆水位、以及优化建议方向（调堆、调 IHOP、排查大对象/Humongous 分配等）。
