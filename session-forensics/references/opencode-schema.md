# OpenCode 会话库结构（2026-10-20 核实）

读取条件：处理 OpenCode 会话库时读本文件。schema 随 OpenCode 版本漂移：提取脚本内置守卫（缺表缺列即报障并指回本文件），报障时 `.schema` 实查后更新本文件。

## 库位置与打开方式

- 路径：`~/.local/share/opencode/opencode.db`(SQLite)。
- 只读打开：`sqlite3 "file:.../opencode.db?mode=ro"` 或脚本默认行为；该库是运行中库，写操作会污染取证对象。

## 只用两张表

- `session_v2`：会话。关键列：`id`、`directory`（工作目录）、`parent_id`（子代理会话指父会话）、`title`、`model`、`time_created`/`time_updated`（epoch 毫秒）。异常收尾判定列：`idle_outcome`、`time_idle`、`time_suspended`、`resume_attempts`。
- `session_message`：消息。关键列：`session_id`、`type`、`seq`（会话内序号）、`data`（JSON 全文）。

旧表 `session`/`message` 是迁移遗留，其 id 全集包含于 `session_v2`，忽略它们。

## data 的 JSON 路径

- `type='user'`：`data.text` 是用户原话；空 text 剔掉。`data.files`、`data.agents` 是附件引用。
- `type='assistant'`：`data.content[]` 数组，元素按 `type` 分：
  - `text`：可见答复，`.text` 取文；
  - `reasoning`：推理部件，`.text` 取文——「判断事件是否发生」在这里取证；
  - `tool`：工具调用，`.name` 取工具名。
- `type='idle'`：空心跳消息，无取证价值。
- `type='synthetic'`：系统续跑注入（如 "Continue if you have next steps…")，不是真人输入。
- 其余类型：`system`（系统注入）、`compaction`（压缩摘要，复盘长会话时它是上下文边界的标记）、`agent-switched`/`location-switched`/`model-switched`（生命周期事件，量小）。统计口径里这些都不是真人输入。

## 常用查询

提取用 `scripts/session_extract.py`（list/users/text/reasoning/tools/stats)。脚本覆盖不了的即席查询用 sqlite3，时间列是 epoch 毫秒：

```sql
datetime(time_created/1000,'unixepoch','localtime')
```

## 已知坑

- `users` 子命令只剔空消息；用户消息里仍可能混入 system-reminder 等注入形态，还原真人输入时须人工剔除（类型层的 system/synthetic 见上节）。
- 子代理会话量大且是主会话的执行细节；`list`/`stats` 默认含子代理会话，宏观统计加 `--main-only`（`parent_id IS NULL`）分出主会话，再决定是否下钻。
- 会话库只记本会话 harness；Codex 的 rollout jsonl 等其他 harness 的会话存储各找各的。
