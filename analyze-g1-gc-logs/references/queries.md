# 常用查询案例（全部针对 gc.duckdb）

连接方式见 SKILL.md「查询方式」一节（记得 `SET TimeZone`）。
以下 SQL 均可用 `con.execute(sql).fetchall()` 直接执行。

> **时区说明**：`timestamp` 是 TIMESTAMPTZ，存的是时间瞬值。`date_trunc` / `strftime` 等分桶函数按**连接设置的 `TimeZone`** 取值——不设就是 UTC。下文统一假设已 `SET TimeZone='Asia/Shanghai'`（按日志实际时区调整）。

## 1. 事件类型分布与平均/最大耗时

```sql
SELECT event,
       COUNT(*)                          AS n,
       ROUND(AVG(duration_ms), 2)        AS avg_ms,
       ROUND(MAX(duration_ms), 2)        AS max_ms,
       ROUND(SUM(duration_ms)/1000, 1)   AS total_s
FROM gc
GROUP BY event
ORDER BY n DESC;
```

## 2. STW 停顿总量与占比（并发周期不计入）

```sql
SELECT
  ROUND(SUM(CASE WHEN is_pause='Y' THEN duration_ms ELSE 0 END)/1000, 1) AS stw_total_s,
  ROUND(SUM(CASE WHEN is_pause='Y' THEN duration_ms ELSE 0 END) /
        SUM(duration_ms) * 100, 1)                                     AS stw_pct_of_all_gc_time,
  COUNT(*) FILTER (WHERE is_pause='Y')                                 AS stw_count
FROM gc;
```

## 3. 每小时停顿耗时与次数（找停顿高峰期）

```sql
SELECT date_trunc('hour', timestamp)      AS hour_local,  -- 时区由 SET TimeZone 决定
       COUNT(*)                            AS pauses,
       ROUND(SUM(duration_ms)/1000, 1)     AS stw_s,
       ROUND(AVG(duration_ms), 2)          AS avg_ms,
       ROUND(MAX(duration_ms), 2)          AS max_ms
FROM gc
WHERE is_pause = 'Y'
GROUP BY hour_local
ORDER BY stw_s DESC
LIMIT 12;
```

## 4. Full GC 时间线与触发时堆水位（第一优先排查）

判断标准：`event='Full (G1 Compaction Pause)'`；若 `before_mb / heap_mb > 0.95`，说明堆被占满才触发，属内存不足或泄漏。

```sql
SELECT timestamp, file,
       before_mb, after_mb, heap_mb,
       ROUND(before_mb / heap_mb * 100, 1) AS pct_before,
       duration_ms
FROM gc
WHERE event = 'Full (G1 Compaction Pause)'
ORDER BY timestamp
LIMIT 50;
```

每小时次数：

```sql
SELECT date_trunc('hour', timestamp) AS hour_local, COUNT(*) AS full_gc_n
FROM gc WHERE event = 'Full (G1 Compaction Pause)'
GROUP BY hour_local ORDER BY hour_local;
```

## 5. 最耗时的 N 次停顿

```sql
SELECT timestamp, event, cause, duration_ms, before_mb, after_mb, heap_mb
FROM gc
WHERE is_pause = 'Y'
ORDER BY duration_ms DESC
LIMIT 20;
```

## 6. Young GC 触发原因分布（定位分配压力来源）

```sql
SELECT cause, COUNT(*) AS n,
       ROUND(AVG(duration_ms), 2) AS avg_ms
FROM gc
WHERE event LIKE 'Young%'
GROUP BY cause
ORDER BY n DESC;
```

- `G1 Humongous Allocation` 占比高 → 大对象（≥ region/2）多，考虑调大 region 或排查超大对象分配。专项排查见下。
- `GCLocker Initiated GC` 频繁 → JNI 临界区过多，查 DirectByteBuffer/原生库调用。
- `G1 Preventive Collection` 频繁 → 晋升失败压力大，考虑调大堆或老年代空间。

## 6b. Humongous Allocation 专项排查

humongous 对象（≥ region/2）直接进老年代，频繁触发说明应用有大对象分配路径（大数组、DirectByteBuffer、批量结果集）。

```sql
-- 汇总：按进程段 × 事件类型
SELECT file, event, COUNT(*) AS n,
       ROUND(AVG(duration_ms),2) AS avg_ms,
       ROUND(MAX(duration_ms),2) AS max_ms
FROM gc
WHERE cause = 'G1 Humongous Allocation'
GROUP BY file, event
ORDER BY n DESC;

-- 时间分布：每小时次数（时区由 SET TimeZone 决定）
SELECT date_trunc('hour', timestamp) AS hour_local, COUNT(*) AS n
FROM gc
WHERE cause = 'G1 Humongous Allocation'
GROUP BY hour_local
ORDER BY n DESC;
```

解读要点：若几乎全部落在 `Young (Concurrent Start)`，说明 humongous 压力与并发标记周期伴生，老年代在同步增长；若集中在堆被占满前的时间段，humongous 分配是 Full GC 的直接推手（本案例实测即如此）。

## 7. 堆占用趋势（每小时 GC 后水位均值）

```sql
SELECT date_trunc('hour', timestamp) AS hour_local,
       ROUND(AVG(after_mb), 1)  AS avg_after_mb,
       ROUND(MAX(after_mb), 1)  AS max_after_mb,
       ROUND(AVG(heap_mb), 1)   AS heap_mb
FROM gc
WHERE after_mb IS NOT NULL
GROUP BY hour_local
ORDER BY hour_local;
```

`max_after_mb` 持续贴近 `heap_mb` 是泄漏/不足的典型曲线。

## 8. 单进程段内分析（uptime/gc_id 只在同 file 内有效）

```sql
-- 例：某进程段内 Young GC 的平均间隔（秒）
SELECT file,
       COUNT(*) AS young_n,
       (MAX(uptime_s) - MIN(uptime_s)) / (COUNT(*) - 1) AS avg_interval_s
FROM gc
WHERE event LIKE 'Young%' AND file = 'gc.log.3'
GROUP BY file;
```

## 9. GC CPU 开销（user/real 比值看线程效率）

```sql
SELECT event,
       ROUND(AVG(user_s / NULLIF(real_s, 0)), 2) AS cpu_threads_used,
       COUNT(*) AS n
FROM gc
WHERE user_s IS NOT NULL AND real_s > 0 AND is_pause = 'Y'
GROUP BY event
ORDER BY n DESC;
```

`user/real` 接近并行线程数说明 GC 线程高效；接近 1 说明并行度没吃满。

## 10. 时间范围过滤（datetime 对象参数）

```python
from datetime import datetime, timezone, timedelta
t0 = datetime(2026, 10, 29, 0, 0, 0, tzinfo=timezone(timedelta(hours=8)))
rows = con.execute(
    "SELECT COUNT(*) FROM gc WHERE timestamp >= ?", [t0]
).fetchone()
```

aware datetime 参数直接传入即可（DuckDB 原生支持）；也可写字符串字面量，但带偏移字面量要先 `SET TimeZone` 才有确定语义，推荐传 datetime 对象。
