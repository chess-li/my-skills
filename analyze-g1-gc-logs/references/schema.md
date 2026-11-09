# G1 GC 日志格式与数据库 Schema 速查

## 日志行结构

```
[2026-10-29T17:32:02.998+0800][89494.901s][info ][gc          ] GC(15550) Pause Young (Normal) (GCLocker Initiated GC) 911M->646M(1174M) 10.168ms
└─ 绝对时间(带时区)          └─ uptime秒  └─级别 └─ tag    └ GC编号 └─ 消息体
```

- **tag 决定行用途**：`gc`（汇总行，解析目标）、`gc,cpu`（CPU 时间，按 GC 编号合并）、`gc,start`（开始行，忽略）、`gc,phases`/`gc,heap`/`gc,age`/`gc,task`/`gc,metaspace`（细节，忽略）、`safepoint`（安全点，可选分析）。
- **轮转文件**：`gc.log` 为当前，`gc.log.0` 更早，数字越大越旧；解析顺序 `gc.log.N → ... → gc.log.0 → gc.log`。

## 汇总行（tag=gc）的两种形态

Pause 行（有堆占用与 STW 耗时）：

```
GC(15550) Pause Young (Normal) (GCLocker Initiated GC) 911M->646M(1174M) 10.168ms
          └─ Young 子类型     └─ 触发原因            └前→后(总堆)  └耗时
GC(15547) Pause Remark 822M->822M(1180M) 29.204ms
GC(1043)  Pause Full (G1 Compaction Pause) 4093M->3768M(4096M) 1767.174ms
```

并发周期行（仅耗时，无堆占用；start 行无耗时，跳过）：

```
GC(15555) Concurrent Mark Cycle 914.384ms
GC(15568) Concurrent Undo Cycle 4.057ms
```

## event / cause 取值（来自真实日志统计）

| event | is_pause | 说明 |
|---|---|---|
| Young (Normal) | Y | 普通年轻代回收 |
| Young (Concurrent Start) | Y | 附带启动并发标记 |
| Young (Prepare Mixed) | Y | 混合回收准备 |
| Young (Mixed) | Y | 混合回收（含老年代分区） |
| Remark / Cleanup | Y | 并发标记的再标记/清理 STW 段 |
| Full (G1 Compaction Pause) | Y | Full GC，堆接近占满时触发，秒级 |
| Concurrent Mark Cycle | N | 并发标记周期总耗时（含内部 STW） |
| Concurrent Undo Cycle | N | 并发撤销周期 |

常见 cause：`G1 Evacuation Pause`（常规）、`GCLocker Initiated GC`（JNI 临界区）、`G1 Humongous Allocation`（大对象）、`G1 Preventive Collection`、`Metadata GC Threshold`。

## gc 表结构（gc.duckdb）

| 列 | 类型 | 说明 |
|---|---|---|
| file | VARCHAR | 来源轮转文件，区分进程重启段 |
| timestamp | TIMESTAMPTZ | 原生时区时间戳，Python 读回为 aware datetime；存储为时间瞬值，显示时区由连接 `TimeZone` 设置决定 |
| uptime_s | DOUBLE | 进程内运行秒数，仅进程内可比 |
| gc_id | BIGINT | GC 编号，仅进程内递增 |
| event / cause | VARCHAR | 见上表 |
| before_mb / after_mb / heap_mb | DOUBLE | 统一换算 MB；并发周期行为 NULL |
| duration_ms | DOUBLE | STW 或周期耗时 |
| user_s / sys_s / real_s | DOUBLE | GC 线程 CPU 时间，并发周期可能为 NULL |
| is_pause | VARCHAR | Y=STW 停顿，N=并发 |

DuckDB 表自带隐式 `rowid`，不需要自增主键列；也不需要手动建索引（自动 zonemap 足够）。

## 抽样检查 CSV 的要点

- Young 行 cause 必须非空；
- duration_ms 数量级应在 0.01–100 ms（Full GC 除外，秒级）；
- `before_mb - after_mb` 通常 ≥ 0；例外：`cause='G1 Preventive Collection'` 时 after 可能略大于 before（预防式回收期间仍有分配继续，真实日志原文即如此），少量负数属正常；若其他 cause 出现负数才是正则误匹配；
- 并发周期行三列 MB 为 NULL 属正常。
