# 常用查询（全部针对 log_entry 表）

`ts_ms` 是 epoch 毫秒（BIGINT）；`log_time` 是时间戳原文。DuckDB 下两者都可用，按时间过滤用 `ts_ms` 最稳。

## 1. 入库概览与解析健康度

```sql
SELECT COUNT(*) AS n,
       COUNT(*) FILTER (WHERE ts_ms IS NULL)      AS ts_null,      -- 时间戳解析失败数
       COUNT(*) FILTER (WHERE level = '?')        AS placeholder,  -- 首行截断占位
       COUNT(*) FILTER (WHERE stack IS NOT NULL)  AS with_stack,
       MIN(log_time), MAX(log_time)
FROM log_entry;
```

`ts_null` 占比高说明时间戳格式没吃全，补 `--ts-format` 后 `--reset` 重导。

## 2. level 分布与每小时日志量

```sql
SELECT level, COUNT(*) AS n FROM log_entry GROUP BY level ORDER BY n DESC;

SELECT ts_ms // 3600000 AS hour_epoch, COUNT(*) AS n
FROM log_entry GROUP BY 1 ORDER BY 1;   -- 或按导入库时区换算显示
```

## 3. ERROR 时间线与异常类型 TOP

```sql
SELECT log_time, file, thread, logger, message
FROM log_entry WHERE level = 'ERROR' ORDER BY ts_ms LIMIT 100;

SELECT exception_type, COUNT(*) AS n
FROM log_entry WHERE exception_type IS NOT NULL
GROUP BY exception_type ORDER BY n DESC;
```

## 4. 按请求/租户/线程追踪（列名随 profile 而定）

```sql
-- ey-log4j2 有 tenant 列；通用做法是按 message 里的 requestId 过滤
SELECT log_time, level, thread, message
FROM log_entry
WHERE message LIKE '%<requestId>%'
ORDER BY ts_ms;
```

## 5. 堆栈全文检索

```sql
SELECT file, log_time, exception_type,
       regexp_extract(stack, 'Caused by: ([^\r\n]+)', 1) AS root_cause
FROM log_entry
WHERE stack LIKE '%NoSuchMethodError%';
```

## 6. 慢请求粗筛（message 含耗时的场景）

```sql
SELECT log_time, message
FROM log_entry
WHERE CAST(regexp_extract(message, '(?:cost|spent|took)[ =](\d+)ms', 1) AS INTEGER) > 5000;
```

正则提取失败返回空串，CAST 后参与比较的行为依赖值，建议先 `WHERE regexp_extract(...) <> ''` 子查询兜底。
