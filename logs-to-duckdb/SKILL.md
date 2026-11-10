---
name: logs-to-duckdb
description: 将文本应用日志（log4j2/logback 等，.log/.log.gz 轮转文件）先分析识别行格式、再清洗写入 DuckDB 并执行常用诊断查询。当用户提供应用/服务日志、要求排查 ERROR 堆积/异常堆栈/按 requestId 或租户追踪日志、或需要对日志做 SQL 分析时使用；格式未知或内置档案不匹配时，先用 detect 脚本分析，再按内置 profile 或自定义命名组正则入库。
---

# 应用日志入 DuckDB 分析

## 工作流（按顺序执行）

原始日志只读。数据库与需续写的分析状态默认放 `<主工作区>/.agent-artifacts/<任务>/<唯一运行标识>/`，Git 用登记的主 checkout，非 Git 用项目目录；首次创建前在该工作区 `.gitignore` 加入 `/.agent-artifacts/` 并用 `git check-ignore` 核验，非 Git 跳过。以下脚本相对本 skill 定位，输入与输出传绝对路径；增量续导显式指定既有数据库，新分析另建运行目录。仅可复算的副本放本会话临时目录，清理只限本次创建的专属目录，不删除历史数据库或日志原件。

1. **分析日志格式（必做，勿跳过）**：`python3 scripts/detect_log_format.py --dir <日志目录>`
   - 不同应用/环境的日志行格式不同（时间戳形态、level 位置、线程表示、有无 host/tenant），写死的正则会静默漏行；
   - 输出各内置 profile 的匹配率与推荐 profile；匹配率不足时给出未命中样例行，据此写自定义正则（见步骤 3）。
2. **确认格式**：推荐 profile 匹配率 ≥ 阈值（默认 90%）→ 直接用；目录内文件格式不一致（如 `app-*.log` 与 `err-*.log` 不同）→ 分子目录分别处理；都不匹配 → 取未命中样例行写自定义正则。格式档案与命名组约定见 [references/formats.md](references/formats.md)。
3. **入库**（二选一）：
   ```bash
   python3 scripts/logs_to_duckdb.py --dir <目录> --db <输出.duckdb> --profile <名> [--reset]
   python3 scripts/logs_to_duckdb.py --dir <目录> --db <输出.duckdb> --regex '<命名组正则>' [--ts-format '%...']
   ```
   支持增量续导（`imported_files` 表记录进度）；同格式换 profile/正则微调时自动按文件清旧重导，**列结构变化会被预检拦下**（须 `--reset` 或换 `--db` 文件）。`.log.gz` 直接可读。
4. **抽查**：`SELECT level, COUNT(*) FROM log_entry GROUP BY 1` 看 level 分布是否合理；`SELECT COUNT(*) WHERE ts_ms IS NULL` 看时间戳解析失败数；再 `head` 原文对照几行确认字段没串位。
5. **查询分析**：常用查询见 [references/queries.md](references/queries.md)。

## 关键经验

- **先分析后写入是硬纪律**：正则静默不匹配时不会报错，只会少行/错列，事后很难发现；detect 的匹配率就是这道闸。
- **续行归属**：不匹配起始行的内容（堆栈帧、多行 JSON）归入上一条的 `stack` 列，`exception_type` 从堆栈头提取——按线程看 ERROR 时堆栈就在同一行，不用回原文。
- **列结构随 profile 变**：`ey-log4j2` 有 `host/tenant/thread/logger/method/line` 六列，`log4j2-bracket` 只有 `thread/logger`；换格式进同一库时脚本自动按文件重导，不要手工拼不同格式的目录。
- **时区**：带偏移的时间戳按偏移解析；无偏移的按导入机器本地时区解释，跨时区机器重导后 `ts_ms` 口径会变，分析前确认。
- **性能**：纯 executemany 批量写入，无 pandas 依赖；百万行级日志按 BATCH=50000 分批，单文件秒级到十几秒。

## 产出建议

报告给用户时包含：格式识别结论（用了哪个 profile/自定义正则、匹配率）、入库行数与时间范围、level 分布、ERROR/异常类型 TOP 与时间线、以及按租户/线程/requestId 的追踪入口。
