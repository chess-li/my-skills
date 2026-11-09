# 日志格式档案与自定义正则约定

## 目录

- [内置 profile](#内置-profile)
- [命名组约定](#命名组约定)
- [自定义正则写法](#自定义正则写法)
- [实测踩坑](#实测踩坑)

## 内置 profile

| profile | 行形态 | 出处 |
|---|---|---|
| `ey-log4j2` | `2026-10-28 00:00:00.012 host/tenantId 线程名 LEVEL  Class.method:Line - msg` | EY 线上 log4j2（2026-10 北控项目实测） |
| `log4j2-bracket` | `2026-10-29 17:32:02,998 [thread] INFO  c.e.s.Foo - msg` | 常见 log4j2/logback 控制台输出 |
| `iso-offset` | `2026-10-29T17:32:02.998+08:00 INFO  [thread] c.e.s.Foo - msg` | ISO8601 带时区偏移 |

正则原文与字段拆分见 `scripts/profiles.py`（单源，改档案只动那里）。

入库列 = 固定列 `file, level, log_time, ts_ms` + 该 profile 的可选组列 + `message, exception_type, stack`。
即 `ey-log4j2` 产生 `host/tenant/thread/logger/method/line` 六列，`log4j2-bracket` 只产生 `thread/logger` 两列——**不同 profile 的表结构不同**。同一库换格式重导：列结构不变时按文件自动清旧重导（`imported_files.profile` 记录每个文件上次用的 profile）；列结构变了预检直接拒绝（提示 `--reset` 或换 `--db` 文件），不会先删旧行再失败。

## 命名组约定

- **必需组**：`ts`（时间戳原文，存为 `log_time` 并解析出 `ts_ms` epoch 毫秒）、`level`、`message`。
- **可选组**：名字即列名，常用 `host/tenant/thread/logger/method/line`；组名 `line` 的列自动建为 INTEGER，其余 VARCHAR。
- 时间戳解析：先 `datetime.fromisoformat`（可吃 ISO 带偏移），再按格式清单 strptime；无时戳偏移的按**导入机器本地时区**解释。自定义格式用 `--ts-format '%Y/%m/%d %H:%M:%S'` 追加。

## 自定义正则写法

detect 阶段匹配率不足时，取 detect 输出的未命中样例行改写：

```bash
python3 scripts/logs_to_duckdb.py --dir <目录> --db logs.duckdb \
  --regex '^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \[(?P<thread>[^\]]+)\] (?P<level>INFO|WARN|ERROR) (?P<message>.*)$' \
  --ts-format '%Y/%m/%d %H:%M:%S'
```

- 命名组 `(?P<name>...)` 不可省略；缺必需组时脚本非零退出并提示缺哪个；
- 消息体必须贪婪吃到行尾 `(?P<message>.*)$`，否则续行判断会错乱；
- 写完先在小目录上跑，用 `SELECT level, COUNT(*)` 与 `SELECT * WHERE ts_ms IS NULL` 抽查解析成功率。

## 实测踩坑

- **别照搬仓库里的 log4j2.xml**：xml 里的 pattern 与线上真实日志不符（线上线程名无方括号、无 trace_id），以实际日志行为准——这正是先跑 detect 的原因。
- **行号可为 `-1`**：SLF4J 桥接（如 `call:-1`），正则用 `(-?\d+)`（`ey-log4j2` 已含）。
- **LEVEL 按宽度补空格**（`%-5level`），正则在 LEVEL 后允许 ` +`。
- **线程名可含空格、逗号**（如 `xxl-job, EmbedServer bizThreadPool-1657257523`），`ey-log4j2` 用非贪婪 `.*?` 到 LEVEL 为止，勿用 `\S+`。
- **续行归属**：不匹配起始行的内容（异常堆栈、多行 JSON）全部归入上一条的 `stack`，不另立行；文件首行就是续行（截断的轮转文件）时建 `level='?'` 的占位行，内容不丢。
- **exception_type 误报防护**：只认 `*Exception/*Error/*Throwable` 行头或 `Caused by:`，多行 JSON 里的同名单词不会误报。
- **混合格式目录**（如 `app-*.log` 与 `err-*.log` 格式不同）：按前缀分子目录分别 detect + 入库到不同数据库文件；同一库同一表结构是硬前提。
